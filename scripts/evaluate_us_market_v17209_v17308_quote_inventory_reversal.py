"""Evaluate development-justified quote inventory-reversal hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

PRIOR = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v17109_v17208_sip_quote_states.py")),
    run_name="v17109_quote_common",
)
NORMALIZED = PRIOR["BASE"]
ATTACH_GLOBALS = PRIOR["attach_quote_states"].__globals__
FAMILIES = (
    "bid_supported_down_above_vwap",
    "quiet_down_above_vwap",
    "stale_down_above_vwap",
    "wide_down_above_vwap",
    "wide_bid_supported_inventory_exhaustion",
)


def attach_inventory_states(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    attached, evidence = PRIOR["attach_quote_states"](events)
    training = attached.loc[
        attached["session_date"].between("2021-01-01", "2023-12-31")
        & attached["valid_quote"]
    ]
    thresholds = training.groupby("bar_idx", as_index=False).agg(
        spread_q80=("relative_spread", lambda values: values.quantile(0.80)),
        age_q80=("quote_age_ms", lambda values: values.quantile(0.80)),
        activity_q20=("quotes_seen", lambda values: values.quantile(0.20)),
        imbalance_q80=("size_imbalance", lambda values: values.quantile(0.80)),
    )
    attached = attached.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    evidence["inventory_threshold_cells"] = len(thresholds)
    return attached, evidence


def common_state(frame: pd.DataFrame) -> pd.Series:
    return frame["valid_quote"] & (frame["ret1"] < 0) & (frame["vwap_dev"] > 0)


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    common = common_state(frame)
    if family == FAMILIES[0]:
        return common & (frame["size_imbalance"] >= frame["imbalance_q80"])
    if family == FAMILIES[1]:
        return common & (frame["quotes_seen"] <= frame["activity_q20"])
    if family == FAMILIES[2]:
        return common & (frame["quote_age_ms"] >= frame["age_q80"])
    if family == FAMILIES[3]:
        return common & (frame["relative_spread"] >= frame["spread_q80"])
    if family == FAMILIES[4]:
        return common & (frame["relative_spread"] >= frame["spread_q80"]) & (
            frame["size_imbalance"] >= frame["imbalance_q80"]
        )
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    downshock = -frame["ret1"].rank(pct=True)
    above_vwap = frame["vwap_dev"].rank(pct=True)
    if family == FAMILIES[0]:
        return frame["size_imbalance"].rank(pct=True) + downshock + above_vwap
    if family == FAMILIES[1]:
        return -frame["quotes_seen"].rank(pct=True) + downshock + above_vwap
    if family == FAMILIES[2]:
        return frame["quote_age_ms"].rank(pct=True) + downshock + above_vwap
    if family == FAMILIES[3]:
        return frame["relative_spread"].rank(pct=True) + downshock + above_vwap
    if family == FAMILIES[4]:
        return (
            frame["relative_spread"].rank(pct=True)
            + frame["size_imbalance"].rank(pct=True)
            + downshock
            + above_vwap
        )
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    ATTACH_GLOBALS["QUOTE_CACHE"] = (
        Path(args.data_root) / "research/cache/us_market_event_quote_features_v1.parquet"
    )
    evaluator_globals = NORMALIZED["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 17209,
            "PRIOR_COMPARISONS": 542_333,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_inventory_states,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = NORMALIZED["run"](args)
    result["campaign_id"] = "v17209-v17308-quote-inventory-reversal"
    result["inventory_state_evidence"] = result.pop("training_only_scale_evidence")
    NORMALIZED["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17209-v17308 quote inventory reversal\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, "
        f"hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, "
            f"MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: "
        f"{best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n",
        "utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument(
        "--output",
        default="research/results/2026-09-07-v17209-v17308-quote-inventory-reversal.json",
    )
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(
        json.dumps(
            {key: summary[key] for key in (
                "status", "versions_completed", "pre_null_candidates",
                "admitted_candidates", "elapsed_seconds",
            )},
            indent=2,
        )
    )
