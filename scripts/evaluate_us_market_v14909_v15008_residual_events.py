"""Evaluate causal cross-sectional residual event signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "residual_one_bar_downshock_reversal",
    "residual_three_bar_reclaim",
    "residual_one_bar_upshock_continuation",
    "relative_vwap_reclaim",
    "residual_volume_climax_reversal",
)


def attach_residuals(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    medians = events.groupby(["session_date", "bar_idx"], as_index=False).agg(
        market_ret1=("ret1", "median"),
        market_ret3=("ret3", "median"),
        market_vwap_dev=("vwap_dev", "median"),
    )
    attached = events.merge(medians, on=["session_date", "bar_idx"], how="left",
                            validate="many_to_one")
    attached["resid_ret1"] = attached["ret1"] - attached["market_ret1"]
    attached["resid_ret3"] = attached["ret3"] - attached["market_ret3"]
    attached["resid_vwap"] = attached["vwap_dev"] - attached["market_vwap_dev"]
    attached["resid_ret1_rank"] = attached.groupby(
        ["session_date", "bar_idx"], sort=False)["resid_ret1"].rank(pct=True)
    attached["resid_ret3_rank"] = attached.groupby(
        ["session_date", "bar_idx"], sort=False)["resid_ret3"].rank(pct=True)
    attached["resid_vwap_rank"] = attached.groupby(
        ["session_date", "bar_idx"], sort=False)["resid_vwap"].rank(pct=True)
    return attached, {"residualized_events": len(attached),
                      "method": "same-session-decision-bar cross-sectional median"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["resid_ret1"] < -0.010
    if family == FAMILIES[1]:
        return (frame["resid_ret3"] < -0.015) & (frame["resid_ret1"] > 0.0)
    if family == FAMILIES[2]:
        return frame["resid_ret1"] > 0.010
    if family == FAMILIES[3]:
        return (frame["resid_vwap"] < -0.008) & (frame["resid_ret1"] > 0.0)
    if family == FAMILIES[4]:
        return ((frame["resid_ret1"] < -0.008) & (frame["volume_rank"] >= 0.90)
                & (frame["range_pos"] <= 0.25))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return -frame["resid_ret1"]
    if family == FAMILIES[1]:
        return -frame["resid_ret3"] + frame["resid_ret1_rank"]
    if family == FAMILIES[2]:
        return frame["resid_ret1"]
    if family == FAMILIES[3]:
        return -frame["resid_vwap"] + frame["resid_ret1_rank"]
    if family == FAMILIES[4]:
        return -frame["resid_ret1"] + frame["volume_rank"] - frame["range_pos"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    BASE["FAMILIES"] = FAMILIES
    BASE["FIRST_VERSION"] = 14909
    BASE["PRIOR_COMPARISONS"] = 337_783
    BASE["attach_training_scales"] = attach_residuals
    BASE["event_mask"] = event_mask
    BASE["score"] = score
    result = BASE["run"](args)
    result["campaign_id"] = "v14909-v15008-cross-section-residual-events"
    result["causal_cross_section_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v14909-v15008 cross-section residual events\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v14909-v15008-residual-events.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
