"""Evaluate training-frozen broad-ETF lead-lag catch-up hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import numpy as np
import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_common",
)
BENCHMARKS = ("SPY", "QQQ", "IWM")
FAMILIES = (
    "spy_positive_catchup",
    "qqq_positive_catchup",
    "iwm_positive_catchup",
    "benchmark_consensus_catchup",
    "factor_shock_lag",
)


def estimate_beta(training: pd.DataFrame, factor: str) -> pd.DataFrame:
    tag = factor.rsplit("_", 1)[-1]
    frame = training[["symbol", "bar_idx", "session_return", factor]].dropna().copy()
    frame["cross"] = frame["session_return"] * frame[factor]
    frame["factor_square"] = frame[factor] ** 2
    cells = frame.groupby(["symbol", "bar_idx"], as_index=False).agg(
        observations=("session_return", "size"),
        mean_symbol_return=("session_return", "mean"),
        mean_factor_return=(factor, "mean"),
        mean_cross=("cross", "mean"),
        mean_factor_square=("factor_square", "mean"),
    )
    covariance = cells["mean_cross"] - cells["mean_symbol_return"] * cells["mean_factor_return"]
    variance = cells["mean_factor_square"] - cells["mean_factor_return"] ** 2
    cells[f"beta_{tag}"] = covariance / variance.replace(0.0, np.nan)
    return cells.loc[
        (cells["observations"] >= 100) & cells[f"beta_{tag}"].between(-1.0, 4.0),
        ["symbol", "bar_idx", f"beta_{tag}"],
    ]


def attach_benchmark_structure(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    benchmark = events.loc[events["symbol"].isin(BENCHMARKS), [
        "symbol", "session_date", "bar_idx", "session_return", "ret1"
    ]].copy()
    wide = benchmark.pivot(index=["session_date", "bar_idx"], columns="symbol")
    wide.columns = [f"{field}_{symbol.lower()}" for field, symbol in wide.columns]
    wide = wide.reset_index()
    required = [
        "session_return_spy", "session_return_qqq", "session_return_iwm",
        "ret1_spy", "ret1_qqq", "ret1_iwm",
    ]
    wide = wide.dropna(subset=required)
    attached = events.merge(wide, on=["session_date", "bar_idx"], how="inner", validate="many_to_one")
    training = attached.loc[
        (attached["session_date"] >= "2021-01-01")
        & (attached["session_date"] <= "2023-12-31")
    ]
    beta_cells = None
    for factor in ("session_return_spy", "session_return_qqq", "session_return_iwm"):
        cells = estimate_beta(training, factor)
        beta_cells = cells if beta_cells is None else beta_cells.merge(
            cells, on=["symbol", "bar_idx"], how="inner", validate="one_to_one"
        )
    if beta_cells is None:
        raise RuntimeError("no frozen benchmark beta cells")
    attached = attached.merge(beta_cells, on=["symbol", "bar_idx"], how="inner", validate="many_to_one")
    attached["expected_spy"] = attached["beta_spy"] * attached["session_return_spy"]
    attached["expected_qqq"] = attached["beta_qqq"] * attached["session_return_qqq"]
    attached["expected_iwm"] = attached["beta_iwm"] * attached["session_return_iwm"]
    attached["gap_spy"] = attached["expected_spy"] - attached["session_return"]
    attached["gap_qqq"] = attached["expected_qqq"] - attached["session_return"]
    attached["gap_iwm"] = attached["expected_iwm"] - attached["session_return"]
    attached["expected_consensus"] = attached[["expected_spy", "expected_qqq", "expected_iwm"]].median(axis=1)
    attached["gap_consensus"] = attached["expected_consensus"] - attached["session_return"]
    attached["expected_ret1_consensus"] = (
        attached["beta_spy"] * attached["ret1_spy"]
        + attached["beta_qqq"] * attached["ret1_qqq"]
        + attached["beta_iwm"] * attached["ret1_iwm"]
    ) / 3.0
    attached["ret1_factor_gap"] = attached["expected_ret1_consensus"] - attached["ret1"]
    return attached, {
        "attached_events": len(attached),
        "frozen_beta_cells": len(beta_cells),
        "method": "2021-2023 frozen univariate ETF betas and causal completed-bar ETF returns",
    }


def non_benchmark(frame: pd.DataFrame) -> pd.Series:
    return ~frame["symbol"].isin(BENCHMARKS)


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    eligible = non_benchmark(frame)
    if family == FAMILIES[0]:
        return eligible & (frame["session_return_spy"] > 0.002) & (frame["beta_spy"] > 0.5) & (frame["gap_spy"] > 0.003)
    if family == FAMILIES[1]:
        return eligible & (frame["session_return_qqq"] > 0.003) & (frame["beta_qqq"] > 0.7) & (frame["gap_qqq"] > 0.004)
    if family == FAMILIES[2]:
        return eligible & (frame["session_return_iwm"] > 0.003) & (frame["beta_iwm"] > 0.7) & (frame["gap_iwm"] > 0.004)
    if family == FAMILIES[3]:
        return (
            eligible
            & (frame[["session_return_spy", "session_return_qqq", "session_return_iwm"]].min(axis=1) > 0.0)
            & (frame["expected_consensus"] > 0.003)
            & (frame["gap_consensus"] > 0.004)
        )
    if family == FAMILIES[4]:
        return eligible & (frame["expected_ret1_consensus"] > 0.002) & (frame["ret1_factor_gap"] > 0.003)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["gap_spy"]
    if family == FAMILIES[1]:
        return frame["gap_qqq"]
    if family == FAMILIES[2]:
        return frame["gap_iwm"]
    if family == FAMILIES[3]:
        return frame["gap_consensus"]
    if family == FAMILIES[4]:
        return frame["ret1_factor_gap"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16409,
            "PRIOR_COMPARISONS": 339_283,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_benchmark_structure,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16409-v16508-benchmark-lead-lag-catchup"
    result["benchmark_lead_lag_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16409-v16508 benchmark lead-lag catch-up\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; all hard gates and historical supplement remain mandatory.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v16409-v16508-benchmark-lead-lag.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
