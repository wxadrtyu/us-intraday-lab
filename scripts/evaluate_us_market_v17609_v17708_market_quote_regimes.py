"""Evaluate training-frozen market-wide SIP quote regimes."""

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
    "calm_upshock_continuation",
    "stressed_downshock_reversal",
    "bid_regime_price_continuation",
    "dispersed_vwap_reclaim",
    "fresh_market_volume_reversal",
)


def attach_market_regimes(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    quoted, quote_evidence = PRIOR["attach_quote_states"](events)
    quoted["abs_imbalance"] = quoted["size_imbalance"].abs()
    state = quoted.groupby(["session_date", "bar_idx"], as_index=False).agg(
        median_spread=("relative_spread", "median"),
        spread_dispersion=("relative_spread", "std"),
        median_imbalance=("size_imbalance", "median"),
        imbalance_dispersion=("abs_imbalance", "median"),
        median_quote_age=("quote_age_ms", "median"),
        quote_availability_share=("quote_available", "mean"),
    )
    quoted = quoted.merge(state, on=["session_date", "bar_idx"], how="left", validate="many_to_one")
    scaled, scale_evidence = NORMALIZED["attach_training_scales"](quoted)
    training_state = state.loc[state["session_date"].between("2021-01-01", "2023-12-31")]
    thresholds = training_state.groupby("bar_idx", as_index=False).agg(
        market_spread_q25=("median_spread", lambda values: values.quantile(0.25)),
        market_spread_q75=("median_spread", lambda values: values.quantile(0.75)),
        imbalance_q75=("median_imbalance", lambda values: values.quantile(0.75)),
        dispersion_q75=("imbalance_dispersion", lambda values: values.quantile(0.75)),
        age_q25_market=("median_quote_age", lambda values: values.quantile(0.25)),
        availability_q75=("quote_availability_share", lambda values: values.quantile(0.75)),
    )
    scaled = scaled.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    evidence: dict[str, int | str] = {**quote_evidence, **scale_evidence}
    evidence["market_state_rows"] = len(state)
    evidence["market_threshold_cells"] = len(thresholds)
    return scaled, evidence


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["median_spread"] <= frame["market_spread_q25"]) & (frame["z_ret1"] > 2)
    if family == FAMILIES[1]:
        return (frame["median_spread"] >= frame["market_spread_q75"]) & (frame["z_ret1"] < -2)
    if family == FAMILIES[2]:
        return (frame["median_imbalance"] >= frame["imbalance_q75"]) & (frame["ret1"] > 0)
    if family == FAMILIES[3]:
        return (frame["imbalance_dispersion"] >= frame["dispersion_q75"]) & (
            frame["z_vwap"] < -2
        ) & (frame["ret1"] > 0)
    if family == FAMILIES[4]:
        return (frame["median_quote_age"] <= frame["age_q25_market"]) & (
            frame["quote_availability_share"] >= frame["availability_q75"]
        ) & (frame["relative_volume"] > 3) & (frame["z_ret1"] < -1.5)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["z_ret1"] - frame["median_spread"].rank(pct=True)
    if family == FAMILIES[1]:
        return -frame["z_ret1"] + frame["median_spread"].rank(pct=True)
    if family == FAMILIES[2]:
        return frame["ret1_rank"] + frame["size_imbalance"].rank(pct=True)
    if family == FAMILIES[3]:
        return -frame["z_vwap"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return frame["relative_volume"] - frame["z_ret1"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    ATTACH_GLOBALS["QUOTE_CACHE"] = Path(args.data_root) / "research/cache/us_market_event_quote_features_v1.parquet"
    globals_ = NORMALIZED["run"].__globals__
    globals_.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 17609,
        "PRIOR_COMPARISONS": 542_733,
        "TOP_COUNT_BY_DECISION": None,
        "attach_training_scales": attach_market_regimes,
        "event_mask": event_mask,
        "score": score,
    })
    result = NORMALIZED["run"](args)
    result["campaign_id"] = "v17609-v17708-market-quote-regimes"
    result["market_quote_regime_evidence"] = result.pop("training_only_scale_evidence")
    NORMALIZED["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17609-v17708 market quote regimes\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v17609-v17708-market-quote-regimes.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds",
    )}, indent=2))
