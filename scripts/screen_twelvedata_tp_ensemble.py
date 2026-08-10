"""Freeze the exact twelve-variant v3 development selection."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import pandas as pd
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.tp_ensemble import (
    TpEnsembleParameters,
    evaluate_tp_ensemble,
    slice_tp_evaluation,
    tp_metrics,
)


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


def _passes(record: dict[str, Any], gates: dict[str, Any]) -> bool:
    combined = record["combined_oos"]
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
        and sum(float(value) > 0.0 for value in combined["folds"])
        >= int(gates["minimum_positive_combined_oos_folds"])
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    research = proposal["research_data"]
    cache_root = Path(research["train_file"]).parent.parent / "derived_daily_v2"
    checks = {
        Path(research["train_file"]): research["train_sha256"],
        Path(research["validation_file"]): research["validation_sha256"],
        Path(research["research_2025_file"]): research["research_2025_sha256"],
        cache_root / "train-features.parquet": research["train_feature_cache_sha256"],
        cache_root / "train-benchmark.parquet": research["train_benchmark_cache_sha256"],
        cache_root / "val-features.parquet": research["validation_feature_cache_sha256"],
        cache_root / "val-benchmark.parquet": research["validation_benchmark_cache_sha256"],
        cache_root / "test-2025-features.parquet": research["research_2025_feature_cache_sha256"],
        cache_root / "test-2025-benchmark.parquet": research[
            "research_2025_benchmark_cache_sha256"
        ],
    }
    for path, expected in checks.items():
        if _file_sha256(path) != expected:
            raise ValueError(f"v3 research evidence hash mismatch: {path}")
    specs = (
        (Path(research["train_file"]), "train"),
        (Path(research["validation_file"]), "2024"),
        (Path(research["research_2025_file"]), "2025"),
    )
    frames = []
    benchmarks = []
    periods = {}
    for path, period in specs:
        frame, benchmark = load_daily(path, split=period)
        frames.append(frame)
        benchmarks.append(benchmark)
        periods[period] = tuple(sorted(frame["session_date"].unique()))
    joined = pd.concat(frames, ignore_index=True)
    benchmark = pd.concat(benchmarks).sort_index()
    universe = tuple(proposal["universe"])
    cost = float(proposal["cost_contract"]["round_trip_cost_1_5x"])
    variants = tuple(
        TpEnsembleParameters(excess, range_floor, exit_minute)
        for excess, range_floor, exit_minute in itertools.product(
            proposal["stock_branch"]["minimum_return_over_spy_values"],
            proposal["stock_branch"]["minimum_opening_range_position_values"],
            proposal["spy_fallback_branch"]["exit_minute_values"],
        )
    )
    if len(variants) != 12 or len(set(variants)) != 12:
        raise ValueError("v3 proposal must produce exactly twelve variants")
    records = []
    for parameters in variants:
        evaluation = evaluate_tp_ensemble(
            joined,
            benchmark,
            tuple(path for path, _ in specs),
            parameters,
            universe=universe,
            round_trip_cost=cost,
        )
        record: dict[str, Any] = {
            "parameters": {
                "stock_excess_floor": parameters.stock_excess_floor,
                "stock_range_floor": parameters.stock_range_floor,
                "fallback_exit_minute": parameters.fallback_exit_minute,
            }
        }
        for period in ("train", "2024", "2025"):
            record[period] = tp_metrics(
                slice_tp_evaluation(evaluation, periods[period]), fold_count=4
            )
        combined_dates = periods["2024"] + periods["2025"]
        record["combined_oos"] = tp_metrics(
            slice_tp_evaluation(evaluation, combined_dates),
            fold_count=int(proposal["development_selection"]["combined_oos_fold_count"]),
        )
        record["minimum_segment_annualized_return"] = min(
            float(record[period]["annualized_return"]) for period in ("train", "2024", "2025")
        )
        record["variant_id"] = _variant_id(proposal["proposal_id"], record["parameters"])
        records.append(record)
    gates = proposal["development_selection"]
    survivors = [record for record in records if _passes(record, gates)]
    if len(survivors) < int(gates["minimum_family_survivors"]):
        raise RuntimeError("v3 has fewer than the required frozen family survivors")
    survivors.sort(
        key=lambda record: (
            -float(record["minimum_segment_annualized_return"]),
            -float(record["combined_oos"]["annualized_return"]),
            -float(record["combined_oos"]["information_ratio"]),
            str(record["variant_id"]),
        )
    )
    proposal_hash = _json_sha256(proposal)
    experiment_id = (
        "portfolio-"
        + _json_sha256(
            {
                "proposal_sha256": proposal_hash,
                "research_hashes": sorted(checks.values()),
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
        "winner_id": survivors[0]["variant_id"],
        "winner_parameters": survivors[0]["parameters"],
    }
    selection["selection_sha256"] = _json_sha256(selection)
    output_dir = args.root.resolve() / "artifacts" / "portfolio_research" / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "selection.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "selection_manifest": str(output),
                "survivors": len(survivors),
                "winner_id": selection["winner_id"],
                "winner_combined_annualized_return": survivors[0]["combined_oos"][
                    "annualized_return"
                ],
                "winner_combined_information_ratio": survivors[0]["combined_oos"][
                    "information_ratio"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
