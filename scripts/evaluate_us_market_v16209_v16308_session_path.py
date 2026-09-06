"""Evaluate opening-to-current session-path momentum hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "session_return_momentum",
    "efficient_session_momentum",
    "volume_confirmed_session_momentum",
    "compressed_range_session_momentum",
    "broad_market_session_momentum",
)


def attach_session_context(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame = events.copy()
    keys = ["session_date", "bar_idx"]
    frame["session_return_rank"] = frame.groupby(keys, sort=False)["session_return"].rank(pct=True)
    state = frame.groupby(keys, as_index=False).agg(
        market_session_return=("session_return", "median"))
    frame = frame.merge(state, on=keys, how="left", validate="many_to_one")
    return frame, {"session_path_events": len(frame),
                   "method": "causal opening-to-current displacement and current cross-section rank"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["session_return_rank"] > 0.90
    if family == FAMILIES[1]:
        return ((frame["session_return_rank"] > 0.90)
                & (frame["directional_efficiency"] > 0.70))
    if family == FAMILIES[2]:
        return ((frame["session_return"] > 0.005) & (frame["volume_to_prior"] > 1.0)
                & (frame["session_return_rank"] > 0.80))
    if family == FAMILIES[3]:
        return ((frame["session_return"] > 0.005) & (frame["running_range"] < 0.020)
                & (frame["session_return_rank"] > 0.80))
    if family == FAMILIES[4]:
        return ((frame["market_session_return"] > 0.0)
                & (frame["session_return_rank"] > 0.90))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    value = frame["session_return"]
    if family == FAMILIES[1]:
        value = value + frame["directional_efficiency"]
    if family == FAMILIES[2]:
        value = value + frame["volume_to_prior"]
    if family == FAMILIES[3]:
        value = value - frame["running_range"]
    if family == FAMILIES[4]:
        value = value + frame["market_session_return"]
    return value


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 16209, "PRIOR_COMPARISONS": 339_083,
        "TOP_COUNT_BY_DECISION": None, "attach_training_scales": attach_session_context,
        "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v16209-v16308-session-path-momentum"
    result["session_path_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16209-v16308 session-path momentum\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v16209-v16308-session-path.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
