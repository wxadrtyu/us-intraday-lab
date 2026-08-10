"""Consume sealed 2026H1 exactly once for the frozen v3 ensemble."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.long_horizon.final_ledger import CampaignFinalLedger
from us_intraday_lab.portfolio_research import nearest_rank_percentile
from us_intraday_lab.tp_ensemble import (
    TpEnsembleParameters,
    evaluate_tp_ensemble,
    exclude_tp_symbol,
    slice_tp_evaluation,
    tp_metrics,
    tp_null_distributions,
    validate_period_sessions,
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


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parameters(record: dict[str, Any]) -> TpEnsembleParameters:
    values = record["parameters"]
    return TpEnsembleParameters(
        float(values["stock_excess_floor"]),
        float(values["stock_range_floor"]),
        int(values["fallback_exit_minute"]),  # type: ignore[arg-type]
    )


def _assert_metrics(observed: dict[str, object], expected: dict[str, Any], label: str) -> None:
    for field in (
        "annualized_return",
        "information_ratio",
        "max_drawdown",
        "profit_factor",
        "trades",
        "positive_symbol_concentration",
    ):
        if not math.isclose(
            float(observed[field]), float(expected[field]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(f"v3 development drift detected: {label}.{field}")
    observed_folds = tuple(observed["folds"])  # type: ignore[arg-type]
    expected_folds = tuple(expected["folds"])
    if len(observed_folds) != len(expected_folds) or any(
        not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(observed_folds, expected_folds, strict=True)
    ):
        raise ValueError(f"v3 development fold drift detected: {label}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--recovery-contract", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    selection_with_hash = json.loads(args.selection.read_text(encoding="utf-8"))
    retained_selection_hash = selection_with_hash["selection_sha256"]
    selection = dict(selection_with_hash)
    selection.pop("selection_sha256")
    if _json_sha256(selection) != retained_selection_hash:
        raise ValueError("v3 selection manifest hash mismatch")
    if _json_sha256(proposal) != selection["proposal_sha256"]:
        raise ValueError("v3 selection proposal hash mismatch")
    recovery = None
    recovery_hash = None
    dataset_id = proposal["sealed_final"]["dataset_id"]
    if args.recovery_contract is not None:
        recovery = json.loads(args.recovery_contract.read_text(encoding="utf-8"))
        recovery_hash = _json_sha256(recovery)
        error_path = root / recovery["failed_error_file"]
        failed_error_with_hash = json.loads(error_path.read_text(encoding="utf-8"))
        failed_hash = failed_error_with_hash.pop("evidence_sha256")
        if (
            recovery.get("schema_version") != "1.0.0"
            or recovery.get("proposal_sha256") != selection["proposal_sha256"]
            or recovery.get("selection_sha256") != retained_selection_hash
            or recovery.get("failed_dataset_id") != dataset_id
            or recovery.get("failed_evidence_sha256") != failed_hash
            or _json_sha256(failed_error_with_hash) != failed_hash
            or failed_error_with_hash.get("error_type") != "TypeError"
            or recovery.get("failure_stage") != "PRE_STRATEGY_EVALUATION_SCOPE_CHECK"
            or recovery.get("strategy_evaluations_before_failure") != 0
            or recovery.get("maximum_recovery_uses") != 1
        ):
            raise ValueError("v3 recovery contract is not bound to the pre-evaluation failure")
        dataset_id = recovery["recovery_dataset_id"]
        if dataset_id == recovery["failed_dataset_id"]:
            raise ValueError("v3 recovery must use an independently auditable ledger row")
    final_path = Path(proposal["sealed_final"]["local_file"])
    manifest_path = final_path.with_suffix(".manifest.json")
    acquisition = json.loads(manifest_path.read_text(encoding="utf-8"))
    sealed = proposal["sealed_final"]
    if (
        acquisition.get("schema_version") != "1.0.0"
        or acquisition.get("period") != sealed["period"]
        or acquisition.get("source_url") != sealed["source_url"]
        or acquisition.get("local_file") != final_path.resolve().as_posix()
        or acquisition.get("file_sha256") != sealed["file_sha256"]
        or acquisition.get("parent_file_sha256") != sealed["parent_file_sha256"]
        or acquisition.get("filter_contract") != sealed["filter_contract"]
        or acquisition.get("file_size_bytes") != final_path.stat().st_size
    ):
        raise ValueError("v3 sealed final acquisition scope mismatch")
    ledger = CampaignFinalLedger(root / "state" / "portfolio_final.sqlite3")
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "dataset_id": dataset_id,
                    "is_consumed": ledger.is_consumed(
                        dataset_id=dataset_id, split_id=proposal["proposal_id"]
                    ),
                    "proposal_sha256": selection["proposal_sha256"],
                    "recovery_contract_sha256": recovery_hash,
                    "selection_sha256": retained_selection_hash,
                },
                sort_keys=True,
            )
        )
        return
    token = ledger.reserve(
        dataset_id=dataset_id,
        split_id=proposal["proposal_id"],
        survivor_ids=tuple(selection["survivor_ids"]),
    )
    output_dir = root / "artifacts" / "portfolio_research" / selection["experiment_id"]
    try:
        final_hash = _file_sha256(final_path)
        if final_hash != sealed["file_sha256"]:
            raise ValueError("v3 sealed final file hash mismatch")
        research = proposal["research_data"]
        specs = (
            (Path(research["train_file"]), "train"),
            (Path(research["validation_file"]), "2024"),
            (Path(research["research_2025_file"]), "2025"),
            (final_path, "2026H1"),
        )
        frames = []
        benchmarks = []
        periods = {}
        for path, period in specs:
            frame, benchmark = load_daily(path, split=period)
            frames.append(frame)
            benchmarks.append(benchmark)
            periods[period] = tuple(sorted(frame["session_date"].unique()))
        final_dates = periods["2026H1"]
        validate_period_sessions(
            final_dates,
            start="2026-01-01",
            end_exclusive="2026-07-01",
            minimum_sessions=120,
        )
        joined = pd.concat(frames, ignore_index=True)
        benchmark = pd.concat(benchmarks).sort_index()
        raw_paths = tuple(path for path, _ in specs)
        universe = tuple(proposal["universe"])
        cost = float(proposal["cost_contract"]["round_trip_cost_1_5x"])
        evaluations = {}
        records_by_id = {record["variant_id"]: record for record in selection["survivors"]}
        for variant_id in selection["survivor_ids"]:
            evaluations[variant_id] = evaluate_tp_ensemble(
                joined,
                benchmark,
                raw_paths,
                _parameters(records_by_id[variant_id]),
                universe=universe,
                round_trip_cost=cost,
            )
        winner = records_by_id[selection["winner_id"]]
        evaluation = evaluations[selection["winner_id"]]
        for period in ("train", "2024", "2025"):
            observed = tp_metrics(slice_tp_evaluation(evaluation, periods[period]), fold_count=4)
            _assert_metrics(observed, winner[period], period)
        development_dates = periods["2024"] + periods["2025"]
        observed_development = tp_metrics(
            slice_tp_evaluation(evaluation, development_dates), fold_count=5
        )
        _assert_metrics(observed_development, winner["combined_oos"], "combined_oos")
        final_metrics = tp_metrics(slice_tp_evaluation(evaluation, final_dates), fold_count=4)
        combined_dates = development_dates + final_dates
        combined = slice_tp_evaluation(evaluation, combined_dates)
        gates = proposal["combined_oos_gates"]
        combined_metrics = tp_metrics(combined, fold_count=int(gates["walk_forward_fold_count"]))
        start_observations = []
        for offset in gates["start_date_offsets_sessions"]:
            metrics = tp_metrics(
                slice_tp_evaluation(combined, combined_dates[int(offset) :]), fold_count=4
            )
            start_observations.append(
                {
                    "offset_sessions": int(offset),
                    "total_return": metrics["total_return"],
                    "max_drawdown": metrics["max_drawdown"],
                }
            )
        leave_one_out = []
        for symbol in universe:
            metrics = tp_metrics(exclude_tp_symbol(combined, symbol), fold_count=4)
            leave_one_out.append(
                {
                    "symbol": symbol,
                    "total_return": metrics["total_return"],
                    "max_drawdown": metrics["max_drawdown"],
                }
            )
        neighbor_observations = []
        for variant_id in selection["survivor_ids"]:
            metrics = tp_metrics(
                slice_tp_evaluation(evaluations[variant_id], combined_dates), fold_count=5
            )
            neighbor_observations.append(
                {
                    "variant_id": variant_id,
                    "annualized_return": metrics["annualized_return"],
                    "max_drawdown": metrics["max_drawdown"],
                }
            )
        null_config = gates["null_test"]
        distributions = tp_null_distributions(
            combined,
            repetitions=int(null_config["repetitions"]),
            seed=int(null_config["seed"]),
        )
        observed_total = float(combined_metrics["total_return"])
        null_evidence = {}
        for method, values in distributions.items():
            threshold = nearest_rank_percentile(values, float(null_config["percentile"]))
            null_evidence[method] = {
                "percentile_threshold": threshold,
                "statistics": values,
                "passed": observed_total > threshold,
            }
        positive_folds = sum(float(value) > 0.0 for value in combined_metrics["folds"])
        profitable_starts = sum(float(item["total_return"]) > 0.0 for item in start_observations)
        profitable_leave_one = sum(float(item["total_return"]) > 0.0 for item in leave_one_out)
        stable_neighbors = sum(
            float(item["annualized_return"]) >= float(gates["minimum_cost_1_5x_annualized_return"])
            and float(item["max_drawdown"]) <= float(gates["maximum_drawdown"])
            for item in neighbor_observations
        )
        gate_results = {
            "annualized_return": float(combined_metrics["annualized_return"])
            >= float(gates["minimum_cost_1_5x_annualized_return"]),
            "information_ratio": float(combined_metrics["information_ratio"])
            >= float(gates["minimum_information_ratio"]),
            "max_drawdown": float(combined_metrics["max_drawdown"])
            <= float(gates["maximum_drawdown"]),
            "profit_factor": float(combined_metrics["profit_factor"])
            >= float(gates["minimum_profit_factor"]),
            "trades": int(combined_metrics["trades"]) >= int(gates["minimum_trades"]),
            "walk_forward": positive_folds / len(combined_metrics["folds"])
            >= float(gates["minimum_positive_walk_forward_fraction"]),
            "symbol_concentration": float(combined_metrics["positive_symbol_concentration"])
            <= float(gates["maximum_positive_symbol_concentration"]),
            "start_date": profitable_starts / len(start_observations)
            >= float(gates["minimum_profitable_start_date_fraction"])
            and all(
                float(item["max_drawdown"]) <= float(gates["maximum_drawdown"])
                for item in start_observations
            ),
            "leave_one_symbol_out": profitable_leave_one / len(leave_one_out)
            >= float(gates["minimum_profitable_leave_one_symbol_out_fraction"])
            and all(
                float(item["max_drawdown"]) <= float(gates["maximum_drawdown"])
                for item in leave_one_out
            ),
            "parameter_stability": stable_neighbors / len(neighbor_observations)
            >= float(gates["minimum_profitable_parameter_neighbor_fraction"]),
            "null_test": all(item["passed"] for item in null_evidence.values()),
        }
        evidence: dict[str, Any] = {
            "schema_version": "1.0.0",
            "experiment_id": selection["experiment_id"],
            "proposal_id": proposal["proposal_id"],
            "winner_id": selection["winner_id"],
            "selection_sha256": retained_selection_hash,
            "final_file_sha256": final_hash,
            "recovery_contract_sha256": recovery_hash,
            "development_reproduced": observed_development,
            "final_test": final_metrics,
            "combined_oos": combined_metrics,
            "start_date_observations": start_observations,
            "leave_one_symbol_out": leave_one_out,
            "parameter_neighbors": neighbor_observations,
            "null_test": null_evidence,
            "gate_results": gate_results,
            "all_passed": all(gate_results.values()),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        evidence_hash = _json_sha256(evidence)
        evidence["evidence_sha256"] = evidence_hash
        _write_json(output_dir / "final-evidence.json", evidence)
        ledger.consume(
            token=token,
            proposal_id=selection["winner_id"],
            evidence_sha256=evidence_hash,
        )
        print(
            json.dumps(
                {
                    "all_passed": evidence["all_passed"],
                    "annualized_return": combined_metrics["annualized_return"],
                    "information_ratio": combined_metrics["information_ratio"],
                    "max_drawdown": combined_metrics["max_drawdown"],
                    "trades": combined_metrics["trades"],
                    "failed_gates": sorted(
                        name for name, passed in gate_results.items() if not passed
                    ),
                    "evidence_sha256": evidence_hash,
                },
                sort_keys=True,
            )
        )
    except BaseException as exc:
        error = {
            "error_type": type(exc).__name__,
            "message": str(exc),
            "proposal_id": proposal["proposal_id"],
            "selection_sha256": retained_selection_hash,
            "winner_id": selection["winner_id"],
            "recovery_contract_sha256": recovery_hash,
        }
        error_hash = _json_sha256(error)
        error["evidence_sha256"] = error_hash
        error_name = (
            "final-recovery-error.json" if recovery_hash is not None else "final-error.json"
        )
        _write_json(output_dir / error_name, error)
        ledger.consume(
            token=token,
            proposal_id=selection["winner_id"],
            evidence_sha256=error_hash,
        )
        raise


if __name__ == "__main__":
    main()
