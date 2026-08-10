"""Consume the sealed 2025 final exactly once for the frozen portfolio winner."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.long_horizon.final_ledger import CampaignFinalLedger
from us_intraday_lab.portfolio_research import (
    PortfolioEvaluation,
    annual_drawdown_profit_factor,
    evaluate_frozen_portfolio,
    exclude_symbol,
    information_ratio,
    nearest_rank_percentile,
    null_distributions,
    slice_evaluation,
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


def _folds(returns: pd.Series, count: int) -> tuple[float, ...]:
    boundaries = np.linspace(0, len(returns), count + 1, dtype=int)
    return tuple(
        annual_drawdown_profit_factor(returns.iloc[boundaries[index] : boundaries[index + 1]])[0]
        for index in range(count)
    )


def _metrics(evaluation: PortfolioEvaluation, *, fold_count: int) -> dict[str, Any]:
    returns = pd.Series(evaluation.session_returns, index=evaluation.sessions, dtype=float)
    benchmark = pd.Series(evaluation.benchmark_returns, index=evaluation.sessions, dtype=float)
    annual, drawdown, profit_factor = annual_drawdown_profit_factor(returns)
    positive_pnl = evaluation.components.sum().clip(lower=0.0)
    concentration = (
        float(positive_pnl.max() / positive_pnl.sum()) if float(positive_pnl.sum()) > 0.0 else 1.0
    )
    return {
        "sessions": len(returns),
        "start": str(returns.index.min()),
        "end": str(returns.index.max()),
        "total_return": float((1.0 + returns).prod() - 1.0),
        "annualized_return": annual,
        "benchmark_total_return": float((1.0 + benchmark).prod() - 1.0),
        "benchmark_annualized_return": annual_drawdown_profit_factor(benchmark)[0],
        "information_ratio": information_ratio(returns, benchmark),
        "max_drawdown": drawdown,
        "profit_factor": profit_factor,
        "trades": evaluation.trade_count,
        "positive_symbol_concentration": concentration,
        "pnl_by_symbol": {
            str(symbol): float(value) for symbol, value in evaluation.components.sum().items()
        },
        "folds": _folds(returns, fold_count),
    }


def _assert_validation_reproduced(observed: dict[str, Any], retained: dict[str, Any]) -> None:
    pairs = {
        "annualized_return": "validation_annual",
        "information_ratio": "validation_ir",
        "max_drawdown": "validation_drawdown",
        "profit_factor": "validation_profit_factor",
        "trades": "validation_trades",
        "positive_symbol_concentration": "validation_concentration",
    }
    for observed_name, retained_name in pairs.items():
        expected = retained[retained_name]
        actual = observed[observed_name]
        if observed_name == "max_drawdown":
            expected = abs(float(expected))
        if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"validation drift detected: {observed_name}")
    if len(observed["folds"]) != len(retained["folds"]) or any(
        not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in zip(observed["folds"], retained["folds"], strict=True)
    ):
        raise ValueError("validation fold drift detected")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    retained_selection_hash = selection.pop("selection_sha256")
    if _json_sha256(selection) != retained_selection_hash:
        raise ValueError("selection manifest hash mismatch")
    if _json_sha256(proposal) != selection["proposal_sha256"]:
        raise ValueError("selection proposal hash mismatch")
    winner = next(
        record
        for record in selection["survivors"]
        if record["variant_id"] == selection["winner_id"]
    )
    final_path = Path(proposal["sealed_final"]["local_file"])
    manifest_path = final_path.with_suffix(".manifest.json")
    if not final_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("sealed final file and acquisition manifest are required")
    acquisition = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        acquisition.get("schema_version") != "1.0.0"
        or acquisition.get("source_url") != proposal["sealed_final"]["source_url"]
        or acquisition.get("period") != proposal["sealed_final"]["period"]
        or acquisition.get("local_file") != final_path.resolve().as_posix()
        or acquisition.get("file_size_bytes") != final_path.stat().st_size
        or acquisition.get("file_sha256") != proposal["sealed_final"]["file_sha256"]
        or acquisition.get("parent_file_sha256") != proposal["sealed_final"]["parent_file_sha256"]
    ):
        raise ValueError("sealed final acquisition scope mismatch")
    ledger = CampaignFinalLedger(root / "state" / "portfolio_final.sqlite3")
    token = ledger.reserve(
        dataset_id=proposal["sealed_final"]["dataset_id"],
        split_id=proposal["proposal_id"],
        survivor_ids=tuple(selection["survivor_ids"]),
    )
    output_dir = root / "artifacts" / "portfolio_research" / selection["experiment_id"]
    try:
        final_sha256 = _file_sha256(final_path)
        if final_sha256 != acquisition.get("file_sha256"):
            raise ValueError("sealed final file hash mismatch")
        train, _ = load_daily(Path(proposal["research_data"]["train_file"]), split="train")
        validation, _ = load_daily(
            Path(proposal["research_data"]["validation_file"]), split="validation"
        )
        final, _ = load_daily(final_path, split="final_test")
        final_dates = tuple(sorted(final["session_date"].unique()))
        if len(final_dates) < 240 or {pd.Timestamp(value).year for value in final_dates} != {2025}:
            raise ValueError("sealed final must exactly represent the 2025 session set")
        joined = pd.concat([train, validation, final], ignore_index=True)
        full = evaluate_frozen_portfolio(
            joined,
            winner["parameters"],
            round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
        )
        validation_dates = tuple(sorted(validation["session_date"].unique()))
        validation_evaluation = slice_evaluation(full, validation_dates)
        final_evaluation = slice_evaluation(full, final_dates)
        combined_dates = validation_dates + final_dates
        combined = slice_evaluation(full, combined_dates)
        validation_metrics = _metrics(validation_evaluation, fold_count=4)
        _assert_validation_reproduced(validation_metrics, winner)
        final_metrics = _metrics(final_evaluation, fold_count=4)
        gates = proposal["combined_oos_gates"]
        combined_metrics = _metrics(combined, fold_count=int(gates["walk_forward_fold_count"]))
        start_observations = []
        for offset in gates["start_date_offsets_sessions"]:
            suffix_dates = combined_dates[int(offset) :]
            suffix = slice_evaluation(combined, suffix_dates)
            suffix_metrics = _metrics(suffix, fold_count=4)
            start_observations.append(
                {
                    "offset_sessions": int(offset),
                    "total_return": suffix_metrics["total_return"],
                    "max_drawdown": suffix_metrics["max_drawdown"],
                }
            )
        symbols = tuple(str(symbol) for symbol in combined.components.columns)
        leave_one_out = []
        for symbol in symbols:
            reduced = exclude_symbol(
                combined,
                symbol,
                round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
            )
            reduced_metrics = _metrics(reduced, fold_count=4)
            leave_one_out.append(
                {
                    "symbol": symbol,
                    "total_return": reduced_metrics["total_return"],
                    "max_drawdown": reduced_metrics["max_drawdown"],
                }
            )
        null_config = gates["null_test"]
        expected_null_methods = {"SESSION_SIGNAL_PERMUTATION", "SESSION_CIRCULAR_SHIFT"}
        if set(null_config["methods"]) != expected_null_methods:
            raise ValueError("frozen null-test methods drifted")
        distributions = null_distributions(
            combined,
            repetitions=int(null_config["repetitions"]),
            seed=int(null_config["seed"]),
            round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
        )
        observed_total = float(combined_metrics["total_return"])
        null_evidence = {
            method: {
                "percentile_threshold": nearest_rank_percentile(
                    values, float(null_config["percentile"])
                ),
                "statistics": values,
                "passed": observed_total
                > nearest_rank_percentile(values, float(null_config["percentile"])),
            }
            for method, values in distributions.items()
        }
        positive_folds = sum(float(value) > 0.0 for value in combined_metrics["folds"])
        profitable_starts = sum(float(item["total_return"]) > 0.0 for item in start_observations)
        profitable_leave_one_out = sum(float(item["total_return"]) > 0.0 for item in leave_one_out)
        gate_results = {
            "annualized_return": combined_metrics["annualized_return"]
            >= float(gates["minimum_cost_1_5x_annualized_return"]),
            "information_ratio": combined_metrics["information_ratio"]
            >= float(gates["minimum_information_ratio"]),
            "max_drawdown": combined_metrics["max_drawdown"] <= float(gates["maximum_drawdown"]),
            "profit_factor": combined_metrics["profit_factor"]
            >= float(gates["minimum_profit_factor"]),
            "trades": combined_metrics["trades"] >= int(gates["minimum_trades"]),
            "walk_forward": positive_folds / len(combined_metrics["folds"])
            >= float(gates["minimum_positive_walk_forward_fraction"]),
            "symbol_concentration": combined_metrics["positive_symbol_concentration"]
            <= float(gates["maximum_positive_symbol_concentration"]),
            "start_date": profitable_starts / len(start_observations)
            >= float(gates["minimum_profitable_start_date_fraction"])
            and all(
                float(item["max_drawdown"]) <= float(gates["maximum_drawdown"])
                for item in start_observations
            ),
            "leave_one_symbol_out": profitable_leave_one_out / len(leave_one_out)
            >= float(gates["minimum_profitable_leave_one_symbol_out_fraction"])
            and all(
                float(item["max_drawdown"]) <= float(gates["maximum_drawdown"])
                for item in leave_one_out
            ),
            "null_test": all(item["passed"] for item in null_evidence.values()),
        }
        evidence: dict[str, Any] = {
            "schema_version": "1.0.0",
            "experiment_id": selection["experiment_id"],
            "proposal_id": proposal["proposal_id"],
            "winner_id": selection["winner_id"],
            "selection_sha256": retained_selection_hash,
            "final_file_sha256": final_sha256,
            "validation": validation_metrics,
            "final_test": final_metrics,
            "combined_oos": combined_metrics,
            "start_date_observations": start_observations,
            "leave_one_symbol_out": leave_one_out,
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
                    "evidence_sha256": evidence_hash,
                    "failed_gates": sorted(
                        name for name, passed in gate_results.items() if not passed
                    ),
                    "information_ratio": combined_metrics["information_ratio"],
                    "trades": combined_metrics["trades"],
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
        }
        error_hash = _json_sha256(error)
        error["evidence_sha256"] = error_hash
        _write_json(output_dir / "final-error.json", error)
        ledger.consume(
            token=token,
            proposal_id=selection["winner_id"],
            evidence_sha256=error_hash,
        )
        raise


if __name__ == "__main__":
    main()
