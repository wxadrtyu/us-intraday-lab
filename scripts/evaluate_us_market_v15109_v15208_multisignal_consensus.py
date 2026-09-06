"""Evaluate preregistered price/liquidity/VWAP consensus events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "downshock_volume_climax_reversal",
    "downtrend_reclaim_with_volume_decay",
    "up_impulse_volume_range_continuation",
    "below_vwap_reclaim_with_participation",
    "path_disagreement_reversal",
)


def attach_consensus_fields(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    required = {"volume_to_prior", "volume_to_open"}
    missing = required.difference(events.columns)
    if missing:
        raise RuntimeError(f"event cache missing consensus fields: {sorted(missing)}")
    valid = events.dropna(subset=list(required)).copy()
    return valid, {"consensus_events": len(valid),
                   "method": "fixed causal agreement across price, volume, VWAP and range"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return ((frame["ret1"] < -0.005) & (frame["volume_to_prior"] > 1.5)
                & (frame["range_pos"] < 0.25))
    if family == FAMILIES[1]:
        return ((frame["ret3"] < -0.010) & (frame["ret1"] > 0.0)
                & (frame["volume_to_prior"] < 0.8))
    if family == FAMILIES[2]:
        return ((frame["ret3"] > 0.010) & (frame["ret1"] > 0.0)
                & (frame["volume_to_prior"] > 1.25) & (frame["range_pos"] > 0.80))
    if family == FAMILIES[3]:
        return ((frame["vwap_dev"] < -0.006) & (frame["ret1"] > 0.001)
                & (frame["volume_rank"] > 0.70))
    if family == FAMILIES[4]:
        return ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.0015)
                & (frame["range_pos"] > 0.50) & (frame["volume_to_prior"] < 1.0))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return -frame["ret1"] + frame["volume_to_prior"] - frame["range_pos"]
    if family == FAMILIES[1]:
        return -frame["ret3"] + frame["ret1_rank"] - frame["volume_to_prior"]
    if family == FAMILIES[2]:
        return frame["ret3"] + frame["volume_to_prior"] + frame["range_pos"]
    if family == FAMILIES[3]:
        return -frame["vwap_dev"] + frame["ret1_rank"] + frame["volume_rank"]
    if family == FAMILIES[4]:
        return -frame["ret3"] + frame["ret1_rank"] + frame["range_pos"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 15109,
        "PRIOR_COMPARISONS": 337_983,
        "attach_training_scales": attach_consensus_fields,
        "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15109-v15208-multisignal-consensus"
    result["causal_consensus_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15109-v15208 multisignal consensus\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15109-v15208-multisignal-consensus.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
