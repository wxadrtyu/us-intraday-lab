"""Evaluate causal range compression and directional-efficiency events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "compressed_bar_volume_breakout",
    "compressed_session_range_breakout",
    "efficient_up_move_continuation",
    "inefficient_down_excursion_reversal",
    "range_expansion_downshock_reversal",
)


def attach_efficiency_fields(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    required = {"bar_range", "running_range", "session_return", "directional_efficiency",
                "volume_to_prior"}
    missing = required.difference(events.columns)
    if missing:
        raise RuntimeError(f"event cache missing efficiency fields: {sorted(missing)}")
    valid = events.dropna(subset=list(required)).copy()
    return valid, {"efficiency_events": len(valid),
                   "method": "causal displacement divided by observed running high-low range"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return ((frame["bar_range"] < 0.004) & (frame["volume_to_prior"] > 1.5)
                & (frame["ret1"] > 0.002))
    if family == FAMILIES[1]:
        return ((frame["running_range"] < 0.015) & (frame["volume_to_prior"] > 1.5)
                & (frame["ret1"] > 0.002))
    if family == FAMILIES[2]:
        return ((frame["directional_efficiency"] > 0.8) & (frame["session_return"] > 0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[3]:
        return ((frame["directional_efficiency"] < 0.35) & (frame["session_return"] < -0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[4]:
        return ((frame["bar_range"] > 0.010) & (frame["ret1"] < -0.005)
                & (frame["volume_to_prior"] > 1.25))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family in FAMILIES[:2]:
        return frame["volume_to_prior"] + frame["ret1_rank"] - frame["bar_range"]
    if family == FAMILIES[2]:
        return frame["directional_efficiency"] + frame["session_return"]
    if family == FAMILIES[3]:
        return -frame["session_return"] + frame["ret1_rank"] - frame["directional_efficiency"]
    if family == FAMILIES[4]:
        return frame["bar_range"] + frame["volume_to_prior"] - frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    cache = Path(args.data_root) / "research" / "cache" / "v14309_v14408_events.parquet"
    files = BASE["COMMON"]["discover_permitted_files"](Path(args.data_root))
    BASE["COMMON"]["materialize_events"](files, cache, True)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15309, "PRIOR_COMPARISONS": 338_183,
        "attach_training_scales": attach_efficiency_fields, "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15309-v15408-price-efficiency-events"
    result["causal_efficiency_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15309-v15408 price efficiency events\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15309-v15408-price-efficiency.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
