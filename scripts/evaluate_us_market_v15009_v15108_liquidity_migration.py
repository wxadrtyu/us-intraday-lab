"""Evaluate causal five-minute liquidity migration event signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "volume_acceleration_up_continuation",
    "volume_acceleration_down_reversal",
    "volume_decay_down_reclaim",
    "opening_liquidity_persistence",
    "opening_liquidity_exhaustion",
)


def attach_liquidity_fields(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    required = {"volume_to_prior", "volume_to_open", "lag1_volume", "opening_volume"}
    missing = required.difference(events.columns)
    if missing:
        raise RuntimeError(f"event cache missing preregistered liquidity fields: {sorted(missing)}")
    valid = events.dropna(subset=list(required)).copy()
    valid = valid.loc[(valid["lag1_volume"] > 0) & (valid["opening_volume"] > 0)]
    return valid, {"liquidity_events": len(valid),
                   "method": "causal current-to-prior and current-to-opening 5m volume ratios"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["volume_to_prior"] > 2.0) & (frame["ret1"] > 0.003)
    if family == FAMILIES[1]:
        return (frame["volume_to_prior"] > 2.0) & (frame["ret1"] < -0.005)
    if family == FAMILIES[2]:
        return ((frame["volume_to_prior"] < 0.5) & (frame["ret3"] < -0.010)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[3]:
        return ((frame["volume_to_open"] > 0.75) & (frame["ret3"] > 0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[4]:
        return ((frame["volume_to_open"] < 0.25) & (frame["ret3"] < -0.008)
                & (frame["ret1"] > 0.0))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["volume_to_prior"] + frame["ret1_rank"]
    if family == FAMILIES[1]:
        return frame["volume_to_prior"] - frame["ret1_rank"]
    if family == FAMILIES[2]:
        return -frame["ret3"] + frame["ret1_rank"] - frame["volume_to_prior"]
    if family == FAMILIES[3]:
        return frame["volume_to_open"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return -frame["ret3"] + frame["ret1_rank"] - frame["volume_to_open"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    cache = Path(args.data_root) / "research" / "cache" / "v14309_v14408_events.parquet"
    files = BASE["COMMON"]["discover_permitted_files"](Path(args.data_root))
    BASE["COMMON"]["materialize_events"](files, cache, True)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 15009,
        "PRIOR_COMPARISONS": 337_883,
        "attach_training_scales": attach_liquidity_fields,
        "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15009-v15108-liquidity-migration-events"
    result["causal_liquidity_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15009-v15108 liquidity migration events\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15009-v15108-liquidity-migration.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
