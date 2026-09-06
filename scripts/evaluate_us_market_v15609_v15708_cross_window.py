"""Evaluate causal confirmation across two completed decision windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "persistent_positive_path",
    "improving_positive_with_volume",
    "positive_path_pullback_resume",
    "persistent_down_then_reclaim",
    "prior_volume_lead_confirmation",
)
PAIR_MAP = {2: (2, 5), 5: (2, 11), 11: (5, 11), 17: (11, 17), 23: (17, 23)}


def attach_transition_pairs(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    parts: list[pd.DataFrame] = []
    previous_columns = ["symbol", "session_date", "ret1", "ret3", "volume_to_prior",
                        "vwap_dev", "range_pos"]
    for synthetic_bar, (previous_bar, current_bar) in PAIR_MAP.items():
        previous = events.loc[events["bar_idx"] == previous_bar, previous_columns].rename(
            columns={column: f"previous_{column}" for column in previous_columns[2:]})
        current = events.loc[events["bar_idx"] == current_bar].copy()
        current = current.merge(previous, on=["symbol", "session_date"], how="inner",
                                validate="one_to_one")
        current["actual_bar_idx"] = current_bar
        current["bar_idx"] = synthetic_bar
        parts.append(current)
    attached = pd.concat(parts, ignore_index=True)
    return attached, {"transition_events": len(attached),
                      "method": "five preregistered prior-current completed-window pairs"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return ((frame["previous_ret1"] > 0.0) & (frame["ret1"] > 0.0)
                & (frame["ret3"] > 0.0))
    if family == FAMILIES[1]:
        return ((frame["ret1"] > frame["previous_ret1"] + 0.002)
                & (frame["ret1"] > 0.0) & (frame["volume_to_prior"] > 1.0))
    if family == FAMILIES[2]:
        return ((frame["previous_ret3"] > 0.008) & frame["ret1"].between(-0.005, 0.0))
    if family == FAMILIES[3]:
        return ((frame["previous_ret1"] < 0.0) & (frame["ret3"] < 0.0)
                & (frame["ret1"] > 0.0015))
    if family == FAMILIES[4]:
        return ((frame["previous_volume_to_prior"] > 1.5) & (frame["ret1"] > 0.003)
                & (frame["ret3"] > 0.0))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["previous_ret1"] + frame["ret1"] + frame["ret3"]
    if family == FAMILIES[1]:
        return frame["ret1"] - frame["previous_ret1"] + frame["volume_to_prior"]
    if family == FAMILIES[2]:
        return frame["previous_ret3"] - frame["ret1"]
    if family == FAMILIES[3]:
        return -frame["previous_ret1"] - frame["ret3"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return frame["previous_volume_to_prior"] + frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15609, "PRIOR_COMPARISONS": 338_483,
        "attach_training_scales": attach_transition_pairs, "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15609-v15708-cross-window-confirmation"
    result["causal_transition_evidence"] = result.pop("training_only_scale_evidence")
    for item in result["results_by_development_rank"]:
        item["transition_pair"] = list(PAIR_MAP[item["decision_bar"]])
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15609-v15708 cross-window confirmation\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, pair {best['transition_pair']}, "
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15609-v15708-cross-window.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
