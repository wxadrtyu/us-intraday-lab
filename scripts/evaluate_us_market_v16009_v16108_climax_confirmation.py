"""Evaluate delayed causal confirmation after a volume-climax event."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "positive_price_confirmation",
    "liquidity_dryup_confirmation",
    "below_vwap_unrecovered",
    "range_reclaim_confirmation",
    "market_breadth_recovery",
)
PAIR_MAP = {2: (2, 5), 5: (2, 11), 11: (5, 11), 17: (11, 17), 23: (17, 23)}


def attach_climax_pairs(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    state = events.groupby(["session_date", "bar_idx"], as_index=False).agg(
        positive_breadth=("ret1", lambda values: float((values > 0).mean())))
    enriched = events.merge(state, on=["session_date", "bar_idx"], how="left",
                            validate="many_to_one")
    prior_columns = ["symbol", "session_date", "ret1", "ret3", "volume_rank", "range_pos",
                     "volume_to_prior", "vwap_dev"]
    parts: list[pd.DataFrame] = []
    for label, (prior_bar, current_bar) in PAIR_MAP.items():
        prior = enriched.loc[enriched["bar_idx"] == prior_bar, prior_columns].rename(
            columns={column: f"prior_{column}" for column in prior_columns[2:]})
        current = enriched.loc[enriched["bar_idx"] == current_bar].copy()
        current = current.merge(prior, on=["symbol", "session_date"], how="inner",
                                validate="one_to_one")
        current["actual_bar_idx"] = current_bar
        current["bar_idx"] = label
        parts.append(current)
    attached = pd.concat(parts, ignore_index=True)
    return attached, {"confirmation_events": len(attached),
                      "method": "five preregistered prior-climax to later-confirmation pairs"}


def prior_climax(frame: pd.DataFrame) -> pd.Series:
    return ((frame["prior_ret1"] < -0.010) & (frame["prior_volume_rank"] >= 0.90)
            & (frame["prior_range_pos"] <= 0.25))


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    base = prior_climax(frame)
    if family == FAMILIES[0]:
        return base & (frame["ret1"] > 0.001)
    if family == FAMILIES[1]:
        return base & (frame["volume_to_prior"] < 0.75) & (frame["ret1"] > 0.0)
    if family == FAMILIES[2]:
        return base & (frame["vwap_dev"] < 0.0) & (frame["ret1"] > 0.0)
    if family == FAMILIES[3]:
        return base & (frame["range_pos"] > 0.60) & (frame["ret1"] > 0.0)
    if family == FAMILIES[4]:
        return base & (frame["positive_breadth"] > 0.55) & (frame["ret1"] > 0.0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    value = -frame["prior_ret1"] + frame["ret1_rank"]
    if family == FAMILIES[1]:
        value = value - frame["volume_to_prior"]
    if family == FAMILIES[2]:
        value = value - frame["vwap_dev"]
    if family == FAMILIES[3]:
        value = value + frame["range_pos"]
    if family == FAMILIES[4]:
        value = value + frame["positive_breadth"]
    return value


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 16009, "PRIOR_COMPARISONS": 338_883,
        "TOP_COUNT_BY_DECISION": None, "attach_training_scales": attach_climax_pairs,
        "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v16009-v16108-climax-delayed-confirmation"
    result["confirmation_evidence"] = result.pop("training_only_scale_evidence")
    for item in result["results_by_development_rank"]:
        item["transition_pair"] = list(PAIR_MAP[item["decision_bar"]])
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16009-v16108 climax delayed confirmation\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v16009-v16108-climax-confirmation.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
