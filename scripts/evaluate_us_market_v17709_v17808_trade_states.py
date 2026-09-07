"""Evaluate preregistered cross-sectional fixed-one-second trade-print states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_trade_common",
)
FAMILIES = (
    "buy_location_absorption_reversal",
    "sell_location_pressure_continuation",
    "large_print_momentum",
    "odd_lot_downshock_reversal",
    "participation_backed_vwap_reclaim",
)
TRADE_CACHE: Path | None = None


def attach_trade_states(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if TRADE_CACHE is None or not TRADE_CACHE.is_file():
        raise RuntimeError("audited fixed-one-second SIP trade cache is unavailable")
    trades = pd.read_parquet(TRADE_CACHE)
    trades["session_date"] = pd.to_datetime(trades["session_date"])
    columns = [
        "symbol", "session_date", "bar_idx", "trade_available", "trades_1s",
        "volume_1s", "notional_1s", "trade_location_volume_imbalance",
        "largest_trade_share", "odd_lot_share", "last_trade_edge_to_midpoint",
    ]
    attached = events.merge(
        trades[columns], on=["symbol", "session_date", "bar_idx"], how="left",
        validate="one_to_one",
    )
    attached["valid_trade"] = (
        attached["trade_available"].fillna(False)
        & attached["volume_1s"].gt(0)
        & attached["notional_1s"].gt(0)
    )
    training = attached.loc[
        attached["session_date"].between("2021-01-01", "2023-12-31")
        & attached["valid_trade"]
    ]
    thresholds = training.groupby("bar_idx", as_index=False).agg(
        imbalance_q25=("trade_location_volume_imbalance", lambda x: x.quantile(0.25)),
        imbalance_q75=("trade_location_volume_imbalance", lambda x: x.quantile(0.75)),
        volume_q75=("volume_1s", lambda x: x.quantile(0.75)),
        large_q75=("largest_trade_share", lambda x: x.quantile(0.75)),
        odd_q75=("odd_lot_share", lambda x: x.quantile(0.75)),
    )
    attached = attached.merge(thresholds, on="bar_idx", how="left", validate="many_to_one")
    return attached, {
        "method": "2021-2023 per-decision-bar frozen trade-state thresholds",
        "trade_rows": len(trades),
        "attached_events": len(attached),
        "available_trade_rows": int(attached["trade_available"].fillna(False).sum()),
        "valid_trade_rows": int(attached["valid_trade"].sum()),
        "threshold_cells": len(thresholds),
        "cross_section_contract": "all eligible symbols ranked jointly per session and bar",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["valid_trade"]
    imbalance = frame["trade_location_volume_imbalance"]
    if family == FAMILIES[0]:
        return valid & (frame["ret1"] < 0) & (imbalance >= frame["imbalance_q75"])
    if family == FAMILIES[1]:
        return valid & (frame["ret1"] < 0) & (imbalance <= frame["imbalance_q25"])
    if family == FAMILIES[2]:
        return valid & (frame["ret1"] > 0) & (frame["largest_trade_share"] >= frame["large_q75"])
    if family == FAMILIES[3]:
        return valid & (frame["ret1"] < 0) & (frame["odd_lot_share"] >= frame["odd_q75"])
    if family == FAMILIES[4]:
        return valid & (frame["vwap_dev"] < 0) & (frame["ret1"] > 0) & (frame["volume_1s"] >= frame["volume_q75"])
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    imbalance = frame["trade_location_volume_imbalance"].rank(pct=True)
    downshock = -frame["ret1"].rank(pct=True)
    momentum = frame["ret1"].rank(pct=True)
    participation = frame["volume_1s"].rank(pct=True)
    if family == FAMILIES[0]:
        return imbalance + downshock + participation
    if family == FAMILIES[1]:
        return -imbalance + downshock + participation
    if family == FAMILIES[2]:
        return frame["largest_trade_share"].rank(pct=True) + momentum + participation
    if family == FAMILIES[3]:
        return frame["odd_lot_share"].rank(pct=True) + downshock
    if family == FAMILIES[4]:
        return participation + momentum - frame["vwap_dev"].rank(pct=True)
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global TRADE_CACHE
    TRADE_CACHE = Path(args.data_root) / "research/cache/us_market_event_trade_features_1s_v1.parquet"
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 17709,
        "PRIOR_COMPARISONS": 542_833,
        "TOP_COUNT_BY_DECISION": None,
        "attach_training_scales": attach_trade_states,
        "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v17709-v17808-fixed-one-second-trade-states"
    result["trade_state_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17709-v17808 fixed-one-second SIP trade states\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO unless every gate, history supplement and native null pass.\n",
        "utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v17709-v17808-trade-states.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates",
        "admitted_candidates", "elapsed_seconds",
    )}, indent=2))
