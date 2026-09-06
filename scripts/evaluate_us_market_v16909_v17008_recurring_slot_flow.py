"""Evaluate consecutive-session recurring intraday slot-flow hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_common",
)
FAMILIES = (
    "prior_slot_return_repeat",
    "three_session_slot_persistence",
    "prior_slot_flow_repeat",
    "accelerating_slot_alpha",
    "stable_slot_alpha",
)


def attach_recurring_slot_history(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame = events.copy()
    frame["slot_forward_5m"] = frame["p2_open"] / frame["p1_open"] - 1.0
    calendar = pd.DataFrame({"session_date": sorted(frame["session_date"].unique())})
    for lag in (1, 2, 3):
        calendar[f"expected_lag{lag}_date"] = calendar["session_date"].shift(lag)
    frame = frame.merge(calendar, on="session_date", how="left", validate="many_to_one")
    frame = frame.sort_values(["symbol", "bar_idx", "session_date"])
    groups = frame.groupby(["symbol", "bar_idx"], sort=False)
    for lag in (1, 2, 3):
        frame[f"lag{lag}_date"] = groups["session_date"].shift(lag)
        frame[f"lag{lag}_slot_forward_5m"] = groups["slot_forward_5m"].shift(lag)
        frame[f"lag{lag}_volume_rank"] = groups["volume_rank"].shift(lag)
        valid = frame[f"lag{lag}_date"] == frame[f"expected_lag{lag}_date"]
        frame.loc[~valid, [f"lag{lag}_slot_forward_5m", f"lag{lag}_volume_rank"]] = pd.NA
    history = frame[[
        "lag1_slot_forward_5m", "lag2_slot_forward_5m", "lag3_slot_forward_5m"
    ]]
    frame["three_session_slot_mean"] = history.mean(axis=1, skipna=False)
    frame["three_session_slot_std"] = history.std(axis=1, skipna=False)
    frame["three_session_positive_count"] = (history > 0.0).sum(axis=1)
    frame["slot_alpha_acceleration"] = (
        frame["lag1_slot_forward_5m"] - frame["lag2_slot_forward_5m"]
    )
    return frame, {
        "attached_events": len(frame),
        "exact_lag1_events": int(frame["lag1_slot_forward_5m"].notna().sum()),
        "exact_three_session_events": int(frame["three_session_slot_mean"].notna().sum()),
        "method": "exact consecutive global sessions; no missing-bar carry-forward",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["lag1_slot_forward_5m"] > 0.003
    if family == FAMILIES[1]:
        return (frame["three_session_slot_mean"] > 0.001) & (frame["three_session_positive_count"] >= 2)
    if family == FAMILIES[2]:
        return (frame["lag1_slot_forward_5m"] > 0.001) & (frame["lag1_volume_rank"] > 0.80)
    if family == FAMILIES[3]:
        return (frame["lag1_slot_forward_5m"] > 0.001) & (frame["slot_alpha_acceleration"] > 0.001)
    if family == FAMILIES[4]:
        return (frame["three_session_slot_mean"] > 0.0008) & (frame["three_session_slot_std"] < 0.003)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family in (FAMILIES[0], FAMILIES[2]):
        return frame["lag1_slot_forward_5m"] + frame["lag1_volume_rank"] * 0.001
    if family in (FAMILIES[1], FAMILIES[4]):
        return frame["three_session_slot_mean"] - frame["three_session_slot_std"]
    if family == FAMILIES[3]:
        return frame["lag1_slot_forward_5m"] + frame["slot_alpha_acceleration"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16909,
            "PRIOR_COMPARISONS": 339_783,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_recurring_slot_history,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16909-v17008-recurring-intraday-slot-flow"
    result["recurring_slot_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16909-v17008 recurring intraday slot flow\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v16909-v17008-recurring-slot-flow.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
