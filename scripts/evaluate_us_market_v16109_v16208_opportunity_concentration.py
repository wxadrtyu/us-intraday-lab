"""Evaluate training-frozen cross-sectional opportunity concentration gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "one_bar_reversal_opportunity",
    "three_bar_reversal_opportunity",
    "one_bar_momentum_opportunity",
    "vwap_dislocation_opportunity",
    "volume_weighted_reversal_opportunity",
)
SCORE_COLUMNS = dict(zip(FAMILIES, (
    "alpha_rev1", "alpha_rev3", "alpha_mom1", "alpha_vwap", "alpha_volume_rev"), strict=True))


def attach_opportunity_gates(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame = events.copy()
    frame["alpha_rev1"] = -frame["ret1"]
    frame["alpha_rev3"] = -frame["ret3"]
    frame["alpha_mom1"] = frame["ret1"]
    frame["alpha_vwap"] = -frame["vwap_dev"]
    frame["alpha_volume_rev"] = -frame["ret1"] * frame["volume_rank"]
    keys = ["session_date", "bar_idx"]
    evidence_cells = 0
    for family, column in SCORE_COLUMNS.items():
        rank_column = f"{family}_rank"
        spread_column = f"{family}_spread"
        gate_column = f"{family}_gate"
        frame[rank_column] = frame.groupby(keys, sort=False)[column].rank(pct=True)
        session_stats = frame.groupby(keys)[column].agg(
            score_median="median", score_q90=lambda values: values.quantile(0.90)).reset_index()
        session_stats[spread_column] = session_stats["score_q90"] - session_stats["score_median"]
        training_stats = session_stats.loc[(session_stats["session_date"] >= "2021-01-01")
                                           & (session_stats["session_date"] <= "2023-12-31")]
        gates = training_stats.groupby("bar_idx", as_index=False)[spread_column].quantile(0.90)
        gates = gates.rename(columns={spread_column: gate_column})
        session_stats = session_stats.merge(gates, on="bar_idx", how="left", validate="many_to_one")
        frame = frame.merge(session_stats[keys + [spread_column, gate_column]], on=keys,
                            how="left", validate="many_to_one")
        evidence_cells += len(gates)
    return frame, {"opportunity_events": len(frame), "training_gate_cells": evidence_cells,
                   "method": "training-only q90 threshold of session score-tail separation"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    return ((frame[f"{family}_spread"] > frame[f"{family}_gate"])
            & (frame[f"{family}_rank"] > 0.90))


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    return frame[SCORE_COLUMNS[family]]


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 16109, "PRIOR_COMPARISONS": 338_983,
        "TOP_COUNT_BY_DECISION": None, "attach_training_scales": attach_opportunity_gates,
        "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v16109-v16208-opportunity-concentration"
    result["opportunity_gate_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16109-v16208 opportunity concentration\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, "
        f"hold {best['holding_minutes']}m)\n"
        + "\n".join(f"- {name}: annualized {value['annualized_return']:.2%}, MDD "
                     f"{value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
                     for name, value in best["development_oos"].items())
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; all hard gates and historical supplement remain mandatory.\n",
        encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v16109-v16208-opportunity-concentration.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
