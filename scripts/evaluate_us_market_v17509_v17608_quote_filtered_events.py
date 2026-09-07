"""Evaluate quote-quality filters applied to normalized price-volume events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from evaluate_us_market_v17409_v17508_microprice_edge import (
    ATTACH_GLOBALS,
    NORMALIZED,
    PRIOR,
)

FAMILIES = (
    "tight_downshock_reversal",
    "fresh_three_bar_reclaim",
    "tight_upshock_continuation",
    "fresh_tight_vwap_reclaim",
    "fresh_volume_downshock_reversal",
)


def attach_filtered_events(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    quoted, quote_evidence = PRIOR["attach_quote_states"](events)
    scaled, scale_evidence = NORMALIZED["attach_training_scales"](quoted)
    training = scaled.loc[
        scaled["session_date"].between("2021-01-01", "2023-12-31")
        & scaled["valid_quote"]
    ]
    thresholds = training.groupby("bar_idx", as_index=False).agg(
        filter_spread_q25=("relative_spread", lambda values: values.quantile(0.25)),
        filter_age_q25=("quote_age_ms", lambda values: values.quantile(0.25)),
    )
    scaled = scaled.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    evidence: dict[str, int | str] = {**quote_evidence, **scale_evidence}
    evidence["quote_filter_threshold_cells"] = len(thresholds)
    return scaled, evidence


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["valid_quote"]
    tight = frame["relative_spread"] <= frame["filter_spread_q25"]
    fresh = frame["quote_age_ms"] <= frame["filter_age_q25"]
    if family == FAMILIES[0]:
        return valid & tight & (frame["z_ret1"] < -2.0)
    if family == FAMILIES[1]:
        return valid & fresh & (frame["z_ret3"] < -2.0) & (frame["ret1"] > 0)
    if family == FAMILIES[2]:
        return valid & tight & (frame["z_ret1"] > 2.0)
    if family == FAMILIES[3]:
        return valid & tight & fresh & (frame["z_vwap"] < -2.0) & (frame["ret1"] > 0)
    if family == FAMILIES[4]:
        return valid & fresh & (frame["relative_volume"] > 3.0) & (frame["z_ret1"] < -1.5)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    tightness = -frame["relative_spread"].rank(pct=True)
    freshness = -frame["quote_age_ms"].rank(pct=True)
    if family == FAMILIES[0]:
        return -frame["z_ret1"] + tightness
    if family == FAMILIES[1]:
        return -frame["z_ret3"] + frame["ret1_rank"] + freshness
    if family == FAMILIES[2]:
        return frame["z_ret1"] + tightness
    if family == FAMILIES[3]:
        return -frame["z_vwap"] + frame["ret1_rank"] + tightness + freshness
    if family == FAMILIES[4]:
        return frame["relative_volume"] - frame["z_ret1"] + freshness
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    ATTACH_GLOBALS["QUOTE_CACHE"] = (
        Path(args.data_root) / "research/cache/us_market_event_quote_features_v1.parquet"
    )
    globals_ = NORMALIZED["run"].__globals__
    globals_.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 17509,
        "PRIOR_COMPARISONS": 542_633,
        "TOP_COUNT_BY_DECISION": None,
        "attach_training_scales": attach_filtered_events,
        "event_mask": event_mask,
        "score": score,
    })
    result = NORMALIZED["run"](args)
    result["campaign_id"] = "v17509-v17608-quote-filtered-price-volume-events"
    result["quote_filter_evidence"] = result.pop("training_only_scale_evidence")
    NORMALIZED["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17509-v17608 quote-filtered price-volume events\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n",
        "utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v17509-v17608-quote-filtered-events.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds",
    )}, indent=2))
