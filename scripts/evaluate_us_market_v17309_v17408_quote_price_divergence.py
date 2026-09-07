"""Evaluate training-frozen SIP quote/price divergence hypotheses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

PRIOR = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v17109_v17208_sip_quote_states.py")),
    run_name="v17109_divergence_common",
)
NORMALIZED = PRIOR["BASE"]
ATTACH_GLOBALS = PRIOR["attach_quote_states"].__globals__
FAMILIES = (
    "up_move_ask_heavy_continuation",
    "down_move_bid_heavy_reversal",
    "below_vwap_bid_reclaim",
    "tight_spread_bid_confirmation",
    "wide_spread_sell_capitulation_repair",
)


def attach_divergence_states(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    attached, evidence = PRIOR["attach_quote_states"](events)
    training = attached.loc[
        attached["session_date"].between("2021-01-01", "2023-12-31")
        & attached["valid_quote"]
    ]
    thresholds = training.groupby("bar_idx", as_index=False).agg(
        spread_q20=("relative_spread", lambda values: values.quantile(0.20)),
        spread_q80=("relative_spread", lambda values: values.quantile(0.80)),
        imbalance_q20=("size_imbalance", lambda values: values.quantile(0.20)),
        imbalance_q80=("size_imbalance", lambda values: values.quantile(0.80)),
    )
    attached = attached.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    evidence["divergence_threshold_cells"] = len(thresholds)
    evidence["quotes_seen_used_for_alpha"] = "false"
    return attached, evidence


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["valid_quote"]
    if family == FAMILIES[0]:
        return valid & (frame["ret1"] > 0) & (
            frame["size_imbalance"] <= frame["imbalance_q20"]
        )
    if family == FAMILIES[1]:
        return valid & (frame["ret1"] < 0) & (
            frame["size_imbalance"] >= frame["imbalance_q80"]
        )
    if family == FAMILIES[2]:
        return valid & (frame["vwap_dev"] < 0) & (frame["ret1"] > 0) & (
            frame["size_imbalance"] >= frame["imbalance_q80"]
        )
    if family == FAMILIES[3]:
        return valid & (frame["relative_spread"] <= frame["spread_q20"]) & (
            frame["size_imbalance"] >= frame["imbalance_q80"]
        ) & (frame["ret1"] > 0)
    if family == FAMILIES[4]:
        return valid & (frame["relative_spread"] >= frame["spread_q80"]) & (
            frame["size_imbalance"] <= frame["imbalance_q20"]
        ) & (frame["ret1"] < 0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    imbalance_rank = frame["size_imbalance"].rank(pct=True)
    spread_rank = frame["relative_spread"].rank(pct=True)
    if family == FAMILIES[0]:
        return frame["ret1_rank"] - imbalance_rank
    if family == FAMILIES[1]:
        return -frame["ret1"].rank(pct=True) + imbalance_rank
    if family == FAMILIES[2]:
        return -frame["vwap_dev"].rank(pct=True) + frame["ret1_rank"] + imbalance_rank
    if family == FAMILIES[3]:
        return frame["ret1_rank"] + imbalance_rank - spread_rank
    if family == FAMILIES[4]:
        return -frame["ret1"].rank(pct=True) - imbalance_rank + spread_rank
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    ATTACH_GLOBALS["QUOTE_CACHE"] = (
        Path(args.data_root) / "research/cache/us_market_event_quote_features_v1.parquet"
    )
    globals_ = NORMALIZED["run"].__globals__
    globals_.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 17309,
            "PRIOR_COMPARISONS": 542_433,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_divergence_states,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = NORMALIZED["run"](args)
    result["campaign_id"] = "v17309-v17408-quote-price-divergence"
    result["quote_divergence_evidence"] = result.pop("training_only_scale_evidence")
    NORMALIZED["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17309-v17408 quote-price divergence\n\n"
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
        "--output", default="research/results/2026-09-07-v17309-v17408-quote-price-divergence.json"
    )
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds",
    )}, indent=2))
