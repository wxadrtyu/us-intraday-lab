"""Evaluate training-frozen, cross-sectional SIP quote-state hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_quote_common",
)
FAMILIES = (
    "tight_bid_support_continuation",
    "wide_bid_absorption_reversal",
    "fresh_bid_vwap_reclaim",
    "quote_burst_continuation",
    "fresh_balanced_downshock_reversal",
)
QUOTE_CACHE: Path | None = None


def attach_quote_states(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if QUOTE_CACHE is None or not QUOTE_CACHE.is_file():
        raise RuntimeError("audited SIP quote cache is unavailable")
    quotes = pd.read_parquet(QUOTE_CACHE)
    quotes["session_date"] = pd.to_datetime(quotes["session_date"])
    columns = [
        "symbol", "session_date", "bar_idx", "quote_available", "relative_spread",
        "size_imbalance", "quote_age_ms", "locked_or_crossed", "quotes_seen",
    ]
    attached = events.merge(
        quotes[columns], on=["symbol", "session_date", "bar_idx"], how="left",
        validate="one_to_one",
    )
    training = attached.loc[
        attached["session_date"].between("2021-01-01", "2023-12-31")
        & attached["quote_available"].fillna(False)
    ]
    thresholds = training.groupby("bar_idx", as_index=False).agg(
        spread_q25=("relative_spread", lambda values: values.quantile(0.25)),
        spread_q75=("relative_spread", lambda values: values.quantile(0.75)),
        age_q25=("quote_age_ms", lambda values: values.quantile(0.25)),
        age_q75=("quote_age_ms", lambda values: values.quantile(0.75)),
        updates_q75=("quotes_seen", lambda values: values.quantile(0.75)),
    )
    attached = attached.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    attached["valid_quote"] = (
        attached["quote_available"].fillna(False)
        & attached["relative_spread"].ge(0)
        & attached["relative_spread"].le(0.05)
        & ~attached["locked_or_crossed"].fillna(True)
    )
    return attached, {
        "method": "2021-2023 per-decision-bar frozen SIP quote-state thresholds",
        "quote_rows": len(quotes),
        "attached_events": len(attached),
        "available_quotes": int(attached["quote_available"].fillna(False).sum()),
        "valid_quotes": int(attached["valid_quote"].sum()),
        "threshold_cells": len(thresholds),
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["valid_quote"]
    if family == FAMILIES[0]:
        return valid & (frame["relative_spread"] <= frame["spread_q25"]) & (
            frame["size_imbalance"] >= 0.25
        ) & (frame["ret1"] > 0)
    if family == FAMILIES[1]:
        return valid & (frame["relative_spread"] >= frame["spread_q75"]) & (
            frame["size_imbalance"] >= 0.25
        ) & (frame["ret1"] < 0)
    if family == FAMILIES[2]:
        return valid & (frame["quote_age_ms"] <= frame["age_q25"]) & (
            frame["size_imbalance"] >= 0.15
        ) & (frame["vwap_dev"] < 0) & (frame["ret1"] > 0)
    if family == FAMILIES[3]:
        return valid & (frame["quotes_seen"] >= frame["updates_q75"]) & (
            frame["size_imbalance"] >= 0.15
        ) & (frame["ret3"] > 0)
    if family == FAMILIES[4]:
        return valid & (frame["quote_age_ms"] <= frame["age_q25"]) & (
            frame["size_imbalance"].abs() <= 0.15
        ) & (frame["ret1"] < 0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    tightness = -frame["relative_spread"].rank(pct=True)
    freshness = -frame["quote_age_ms"].rank(pct=True)
    activity = frame["quotes_seen"].rank(pct=True)
    if family == FAMILIES[0]:
        return frame["size_imbalance"] + frame["ret1_rank"] + tightness
    if family == FAMILIES[1]:
        return frame["size_imbalance"] - frame["ret1"] + frame["relative_spread"].rank(pct=True)
    if family == FAMILIES[2]:
        return frame["size_imbalance"] + frame["ret1_rank"] + freshness
    if family == FAMILIES[3]:
        return frame["size_imbalance"] + frame["ret1_rank"] + activity
    if family == FAMILIES[4]:
        return -frame["ret1"] - frame["size_imbalance"].abs() + freshness
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global QUOTE_CACHE
    QUOTE_CACHE = Path(args.data_root) / "research" / "cache" / "us_market_event_quote_features_v1.parquet"
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 17109,
            "PRIOR_COMPARISONS": 542_233,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_quote_states,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v17109-v17208-training-frozen-sip-quote-states"
    result["sip_quote_state_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17109-v17208 training-frozen SIP quote states\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, "
        f"hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, "
            f"MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: "
        f"{best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO unless every gate, history supplement and native null pass.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument(
        "--output",
        default="research/results/2026-09-07-v17109-v17208-sip-quote-states.json",
    )
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "status", "versions_completed", "pre_null_candidates",
                    "admitted_candidates", "elapsed_seconds",
                )
            },
            indent=2,
        )
    )
