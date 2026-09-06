"""Evaluate causal cross-sectional breadth and activity event signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "breadth_recovery_continuation",
    "breadth_deterioration_resilience",
    "broad_positive_volume_continuation",
    "broad_negative_stock_rebound",
    "concentrated_activity_continuation",
)


def attach_breadth(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    keys = ["session_date", "bar_idx"]
    stats = events.groupby(keys, as_index=False).agg(
        current_positive_breadth=("ret1", lambda values: float((values > 0).mean())),
        multibar_positive_breadth=("ret3", lambda values: float((values > 0).mean())),
        total_volume=("volume", "sum"),
    )
    top_volume = (events.sort_values(keys + ["volume"], ascending=[True, True, False])
                  .groupby(keys, sort=False).head(10).groupby(keys, as_index=False)["volume"].sum()
                  .rename(columns={"volume": "top_volume"}))
    stats = stats.merge(top_volume, on=keys, how="left", validate="one_to_one")
    stats["breadth_transition"] = (
        stats["current_positive_breadth"] - stats["multibar_positive_breadth"])
    stats["volume_concentration"] = stats["top_volume"] / stats["total_volume"]
    attached = events.merge(stats, on=keys, how="left", validate="many_to_one")
    return attached, {"breadth_events": len(attached),
                      "method": "causal current-vs-multibar breadth and top-10 volume share"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["breadth_transition"] > 0.10) & (frame["ret1"] > 0.002)
    if family == FAMILIES[1]:
        return ((frame["breadth_transition"] < -0.10) & (frame["ret1"] > 0.003)
                & (frame["ret3"] > 0.0))
    if family == FAMILIES[2]:
        return ((frame["current_positive_breadth"] > 0.60) & (frame["ret1"] > 0.003)
                & (frame["volume_to_prior"] > 1.0))
    if family == FAMILIES[3]:
        return ((frame["current_positive_breadth"] < 0.40) & (frame["ret3"] < -0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[4]:
        return ((frame["volume_concentration"] > 0.25) & (frame["volume_rank"] > 0.90)
                & (frame["ret1"] > 0.003))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["breadth_transition"] + frame["ret1_rank"]
    if family == FAMILIES[1]:
        return -frame["breadth_transition"] + frame["ret1_rank"]
    if family == FAMILIES[2]:
        return frame["current_positive_breadth"] + frame["ret1_rank"] + frame["volume_to_prior"]
    if family == FAMILIES[3]:
        return -frame["current_positive_breadth"] - frame["ret3"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return frame["volume_concentration"] + frame["volume_rank"] + frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15509, "PRIOR_COMPARISONS": 338_383,
        "attach_training_scales": attach_breadth, "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15509-v15608-breadth-activity-events"
    result["causal_breadth_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15509-v15608 breadth and activity events\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15509-v15608-breadth-activity.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
