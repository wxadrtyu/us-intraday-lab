"""Reproduce and freeze the exact 36-variant v4 development selection."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import pandas as pd
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.dual_sleeve import (
    DualSleeveParameters,
    dual_sleeve_metrics,
    dual_sleeve_null_distributions,
    evaluate_dual_sleeve,
    exclude_dual_sleeve_symbol,
    prepare_dual_sleeve,
    slice_dual_sleeve,
)
from us_intraday_lab.portfolio_research import nearest_rank_percentile


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _variant_id(proposal_id: str, parameters: object) -> str:
    return f"{proposal_id}-{_json_sha256(parameters)[:12]}"


def _parameters(parameters: DualSleeveParameters) -> dict[str, float | int]:
    return {
        "stock_excess_floor": parameters.stock_excess_floor,
        "stock_range_floor": parameters.stock_range_floor,
        "spy_current_floor": parameters.spy_current_floor,
        "spy_exit_minute": parameters.spy_exit_minute,
    }


def _passes(record: dict[str, Any], gates: dict[str, Any]) -> bool:
    combined = record["combined_oos"]
    folds = tuple(float(value) for value in combined["folds"])
    return (
        float(record["train"]["annualized_return"])
        >= float(gates["minimum_train_annualized_return"])
        and float(record["2024"]["annualized_return"]) > 0.0
        and float(record["2025"]["annualized_return"]) > 0.0
        and float(combined["annualized_return"])
        >= float(gates["minimum_combined_oos_annualized_return"])
        and float(combined["information_ratio"])
        >= float(gates["minimum_combined_oos_information_ratio"])
        and float(combined["max_drawdown"]) <= float(gates["maximum_combined_oos_drawdown"])
        and float(combined["profit_factor"]) >= float(gates["minimum_combined_oos_profit_factor"])
        and int(combined["trades"]) >= int(gates["minimum_combined_oos_trades"])
        and float(combined["positive_symbol_concentration"])
        <= float(gates["maximum_positive_symbol_concentration"])
        and sum(value > 0.0 for value in folds) / len(folds)
        >= float(gates["minimum_positive_fold_fraction"])
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    research = proposal["research_data"]
    specs = tuple(
        (
            Path(research[key]["local_file"]),
            period,
            str(research[key]["file_sha256"]),
        )
        for key, period in (
            ("train", "train"),
            ("validation_2024", "2024"),
            ("research_2025", "2025"),
        )
    )
    for path, _, expected in specs:
        if _file_sha256(path) != expected:
            raise ValueError(f"v4 research evidence hash mismatch: {path}")
    frames = []
    benchmarks = []
    periods = {}
    for path, period, _ in specs:
        frame, benchmark = load_daily(path, split=period)
        frames.append(frame)
        benchmarks.append(benchmark)
        periods[period] = tuple(sorted(frame["session_date"].unique()))
    joined = pd.concat(frames, ignore_index=True)
    benchmark = pd.concat(benchmarks).sort_index()
    universe = tuple(proposal["universe"])
    prepared = prepare_dual_sleeve(
        joined,
        benchmark,
        tuple(path for path, _, _ in specs),
        universe=universe,
        round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
    )
    stock = proposal["stock_sleeve"]
    spy = proposal["spy_sleeve"]
    variants = tuple(
        DualSleeveParameters(excess, range_floor, current_floor, exit_minute)
        for excess, range_floor, current_floor, exit_minute in itertools.product(
            stock["minimum_return_over_spy_values"],
            stock["minimum_opening_range_position_values"],
            spy["minimum_current_return_values"],
            spy["scheduled_exit_minute_values"],
        )
    )
    if len(variants) != 36 or len(set(variants)) != 36:
        raise ValueError("v4 proposal must produce exactly thirty-six variants")
    gates = proposal["hard_gates"]
    combined_dates = periods["2024"] + periods["2025"]
    records = []
    evaluations = {}
    for parameters in variants:
        evaluation = evaluate_dual_sleeve(prepared, parameters)
        parameter_record = _parameters(parameters)
        variant_id = _variant_id(proposal["proposal_id"], parameter_record)
        evaluations[variant_id] = evaluation
        record: dict[str, Any] = {
            "variant_id": variant_id,
            "parameters": parameter_record,
        }
        for period in ("train", "2024", "2025"):
            record[period] = dual_sleeve_metrics(
                slice_dual_sleeve(prepared, evaluation, periods[period]), fold_count=4
            )
        record["combined_oos"] = dual_sleeve_metrics(
            slice_dual_sleeve(prepared, evaluation, combined_dates),
            fold_count=int(gates["combined_oos_fold_count"]),
        )
        record["minimum_segment_annualized_return"] = min(
            float(record[period]["annualized_return"]) for period in ("train", "2024", "2025")
        )
        records.append(record)
    survivors = [record for record in records if _passes(record, gates)]
    if len(survivors) < int(gates["minimum_family_survivors"]):
        raise RuntimeError("v4 has fewer than the required frozen family survivors")
    survivors.sort(
        key=lambda record: (
            -float(record["minimum_segment_annualized_return"]),
            -float(record["combined_oos"]["annualized_return"]),
            -float(record["combined_oos"]["information_ratio"]),
            str(record["variant_id"]),
        )
    )
    winner = survivors[0]
    winner_evaluation = evaluations[winner["variant_id"]]
    combined = slice_dual_sleeve(prepared, winner_evaluation, combined_dates)
    start_dates = []
    for offset in (0, 20, 40, 60):
        observation = dual_sleeve_metrics(
            slice_dual_sleeve(prepared, combined, combined.sessions[offset:]), fold_count=4
        )
        start_dates.append({"offset_sessions": offset, **observation})
    start_date_passed = all(
        float(value["annualized_return"]) >= float(gates["minimum_combined_oos_annualized_return"])
        and float(value["information_ratio"])
        >= float(gates["minimum_combined_oos_information_ratio"])
        and float(value["max_drawdown"]) <= float(gates["maximum_combined_oos_drawdown"])
        for value in start_dates
    )
    leave_one_out = []
    for symbol in universe:
        observation = dual_sleeve_metrics(
            exclude_dual_sleeve_symbol(prepared, combined, symbol), fold_count=4
        )
        leave_one_out.append({"symbol": symbol, **observation})
    leave_one_out_passed = all(
        float(value["total_return"]) > 0.0
        and float(value["max_drawdown"]) <= float(gates["maximum_combined_oos_drawdown"])
        for value in leave_one_out
    )
    null_values = dual_sleeve_null_distributions(
        prepared,
        combined,
        repetitions=int(gates["null_test_repetitions"]),
        seed=20260810,
    )
    observed_return = float(dual_sleeve_metrics(combined, fold_count=4)["total_return"])
    null_test = {}
    for name, values in null_values.items():
        threshold = nearest_rank_percentile(values, float(gates["null_test_percentile"]))
        null_test[name] = {
            "observed_total_return": observed_return,
            "percentile_threshold": threshold,
            "passed": observed_return > threshold,
            "statistics": values,
        }
    gate_results = {
        "core": _passes(winner, gates),
        "start_date": start_date_passed,
        "leave_one_symbol_out": leave_one_out_passed,
        "parameter_stability": len(survivors) >= int(gates["minimum_family_survivors"]),
        "null_test": all(bool(value["passed"]) for value in null_test.values()),
    }
    proposal_hash = _json_sha256(proposal)
    experiment_id = (
        "portfolio-"
        + _json_sha256(
            {
                "proposal_sha256": proposal_hash,
                "research_hashes": sorted(expected for _, _, expected in specs),
            }
        )[:32]
    )
    selection: dict[str, Any] = {
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": proposal_hash,
        "variant_count": len(records),
        "survivor_ids": sorted(record["variant_id"] for record in survivors),
        "survivors": survivors,
        "winner_id": winner["variant_id"],
        "winner_parameters": winner["parameters"],
        "start_date_observations": start_dates,
        "leave_one_symbol_out": leave_one_out,
        "null_test": null_test,
        "gate_results": gate_results,
        "all_development_gates_passed": all(gate_results.values()),
        "promotion_status": "WAITING_FOR_NEW_FORWARD_INTERVAL",
    }
    selection["selection_sha256"] = _json_sha256(selection)
    output = (
        args.root.resolve() / "artifacts" / "portfolio_research" / experiment_id / "selection.json"
    )
    _write_json(output, selection)
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "selection_manifest": str(output),
                "survivors": len(survivors),
                "winner_id": winner["variant_id"],
                "winner_combined_annualized_return": winner["combined_oos"]["annualized_return"],
                "winner_combined_information_ratio": winner["combined_oos"]["information_ratio"],
                "all_development_gates_passed": all(gate_results.values()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
