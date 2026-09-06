"""Evaluate path-disagreement confirmations over non-overlapping sleeves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14609_v14708_sequential_sparse.py")), run_name="v14609_common")
FAMILIES = (
    "baseline_path_disagreement",
    "below_vwap_path_reclaim",
    "strong_current_recovery",
    "liquidity_dryup_reversal",
    "high_range_reclaim",
)


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    base = ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.0015)
            & (frame["range_pos"] > 0.50) & (frame["volume_to_prior"] < 1.0))
    if family == FAMILIES[0]:
        return base
    if family == FAMILIES[1]:
        return base & (frame["vwap_dev"] < -0.004)
    if family == FAMILIES[2]:
        return ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.003)
                & (frame["range_pos"] > 0.50))
    if family == FAMILIES[3]:
        return ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.001)
                & (frame["volume_to_prior"] < 0.6))
    if family == FAMILIES[4]:
        return ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.0015)
                & (frame["range_pos"] > 0.70))
    raise ValueError(family)


def event_score(frame: pd.DataFrame, family: str) -> pd.Series:
    base = -frame["ret3"] + frame["ret1_rank"] + frame["range_pos"]
    if family == FAMILIES[0]:
        return base - frame["volume_to_prior"]
    if family == FAMILIES[1]:
        return base - frame["vwap_dev"] - frame["volume_to_prior"]
    if family == FAMILIES[2]:
        return base + frame["ret1_rank"]
    if family == FAMILIES[3]:
        return base - frame["volume_to_prior"]
    if family == FAMILIES[4]:
        return base + frame["range_pos"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    sparse_namespace = evaluator_globals["SPARSE"]
    sparse_namespace["event_mask"] = event_mask
    sparse_namespace["event_score"] = event_score
    evaluator_globals.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 15209,
        "PRIOR_COMPARISONS": 338_083,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15209-v15308-path-disagreement-sleeves"
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15209-v15308 path-disagreement sleeves\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, schedule "
        f"{best['decision_schedule']}, hold {best['holding_minutes']}m)\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15209-v15308-path-disagreement-sleeves.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
