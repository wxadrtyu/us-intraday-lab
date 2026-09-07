"""Evaluate symbol-and-slot normalized fixed-one-second trade residuals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import numpy as np
import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_trade_residual_common",
)
FAMILIES = (
    "abnormal_notional_momentum",
    "abnormal_trade_count_accumulation",
    "print_discount_reversal",
    "distributed_participation_continuation",
    "low_price_response_absorption",
)
TRADE_CACHE: Path | None = None


def attach_trade_residuals(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if TRADE_CACHE is None or not TRADE_CACHE.is_file():
        raise RuntimeError("audited fixed-one-second SIP trade cache is unavailable")
    trades = pd.read_parquet(TRADE_CACHE)
    trades["session_date"] = pd.to_datetime(trades["session_date"])
    columns = [
        "symbol", "session_date", "bar_idx", "trade_available", "trades_1s",
        "volume_1s", "notional_1s", "trade_location_volume_imbalance",
        "largest_trade_share", "last_trade_edge_to_midpoint",
    ]
    attached = events.merge(trades[columns], on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one")
    attached["valid_trade"] = attached["trade_available"].fillna(False) & attached["notional_1s"].gt(0)
    training = attached.loc[attached["session_date"].between("2021-01-01", "2023-12-31") & attached["valid_trade"]].copy()
    baselines = training.groupby(["symbol", "bar_idx"], as_index=False).agg(
        observations=("notional_1s", "count"),
        notional_baseline=("notional_1s", "median"),
        trades_baseline=("trades_1s", "median"),
        volume_baseline_1s=("volume_1s", "median"),
    )
    baselines = baselines.loc[(baselines["observations"] >= 20) & baselines["notional_baseline"].gt(0) & baselines["trades_baseline"].gt(0) & baselines["volume_baseline_1s"].gt(0)]
    attached = attached.merge(baselines, on=["symbol", "bar_idx"], how="inner", validate="many_to_one")
    attached["relative_notional_1s"] = attached["notional_1s"] / attached["notional_baseline"]
    attached["relative_trades_1s"] = attached["trades_1s"] / attached["trades_baseline"]
    attached["relative_volume_1s"] = attached["volume_1s"] / attached["volume_baseline_1s"]
    attached["absolute_price_response"] = attached["ret1"].abs() / np.log1p(attached["relative_notional_1s"])
    thresholds = training.merge(baselines, on=["symbol", "bar_idx"], how="inner").assign(
        relative_notional_1s=lambda x: x["notional_1s"] / x["notional_baseline"],
        relative_trades_1s=lambda x: x["trades_1s"] / x["trades_baseline"],
        relative_volume_1s=lambda x: x["volume_1s"] / x["volume_baseline_1s"],
    ).groupby("bar_idx", as_index=False).agg(
        rel_notional_q75=("relative_notional_1s", lambda x: x.quantile(0.75)),
        rel_trades_q75=("relative_trades_1s", lambda x: x.quantile(0.75)),
        rel_volume_q75=("relative_volume_1s", lambda x: x.quantile(0.75)),
        print_edge_q25=("last_trade_edge_to_midpoint", lambda x: x.quantile(0.25)),
        large_share_q25=("largest_trade_share", lambda x: x.quantile(0.25)),
    )
    attached = attached.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    return attached, {
        "method": "2021-2023 symbol-by-decision-slot medians plus per-slot residual quantiles",
        "baseline_cells": len(baselines), "threshold_cells": len(thresholds),
        "attached_events": len(attached), "valid_trade_rows": int(attached["valid_trade"].sum()),
        "cross_section_contract": "all eligible symbols ranked jointly per session and bar",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["valid_trade"]
    if family == FAMILIES[0]:
        return valid & (frame["relative_notional_1s"] >= frame["rel_notional_q75"]) & (frame["ret1"] > 0)
    if family == FAMILIES[1]:
        return valid & (frame["relative_trades_1s"] >= frame["rel_trades_q75"]) & (frame["ret1"] > 0) & (frame["vwap_dev"] > 0)
    if family == FAMILIES[2]:
        return valid & (frame["last_trade_edge_to_midpoint"] <= frame["print_edge_q25"]) & (frame["ret1"] < 0)
    if family == FAMILIES[3]:
        return valid & (frame["relative_volume_1s"] >= frame["rel_volume_q75"]) & (frame["largest_trade_share"] <= frame["large_share_q25"]) & (frame["ret1"] > 0)
    if family == FAMILIES[4]:
        return valid & (frame["relative_notional_1s"] >= frame["rel_notional_q75"]) & (frame["ret1"] < 0) & (frame["trade_location_volume_imbalance"] > 0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    rel_notional = frame["relative_notional_1s"].rank(pct=True)
    rel_trades = frame["relative_trades_1s"].rank(pct=True)
    rel_volume = frame["relative_volume_1s"].rank(pct=True)
    momentum = frame["ret1"].rank(pct=True)
    if family == FAMILIES[0]:
        return rel_notional + momentum
    if family == FAMILIES[1]:
        return rel_trades + momentum + frame["vwap_dev"].rank(pct=True)
    if family == FAMILIES[2]:
        return -frame["last_trade_edge_to_midpoint"].rank(pct=True) - momentum
    if family == FAMILIES[3]:
        return rel_volume - frame["largest_trade_share"].rank(pct=True) + momentum
    if family == FAMILIES[4]:
        return rel_notional - frame["absolute_price_response"].rank(pct=True) + frame["trade_location_volume_imbalance"].rank(pct=True)
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict[str, Any]:
    global TRADE_CACHE
    TRADE_CACHE = Path(args.data_root) / "research/cache/us_market_event_trade_features_1s_v1.parquet"
    globals_ = BASE["run"].__globals__
    globals_.update({"FAMILIES": FAMILIES, "FIRST_VERSION": 17809, "PRIOR_COMPARISONS": 542_933, "TOP_COUNT_BY_DECISION": None, "attach_training_scales": attach_trade_residuals, "event_mask": event_mask, "score": score})
    result = BASE["run"](args)
    result["campaign_id"] = "v17809-v17908-symbol-normalized-trade-residuals"
    result["trade_residual_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17809-v17908 symbol-normalized trade residuals\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}" for name, value in best["development_oos"].items())
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO unless every gate, history supplement and native null pass.\n",
        "utf-8",
    )
    return cast(dict[str, Any], result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v17809-v17908-trade-residuals.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
