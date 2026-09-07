"""Evaluate trade-print filters on the opening volume-climax return source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pandas as pd

PARENT = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v15909_v16008_climax_concentration.py")),
    run_name="v15909_trade_filter_parent",
)
BASE = PARENT["BASE"]
FAMILIES = (
    "valid_trade",
    "print_below_mid",
    "print_not_above_mid",
    "negative_location",
    "positive_location",
)
TRADE_CACHE: Path | None = None
UNIVERSE: Path | None = None
LABELS = (2, 5, 11, 17, 23)
TOP_COUNTS = dict(zip(LABELS, (1, 2, 3, 5, 10), strict=True))


def attach_filtered_climax(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if TRADE_CACHE is None or not TRADE_CACHE.is_file() or UNIVERSE is None:
        raise RuntimeError("trade cache or universe is unavailable")
    parent_globals = PARENT["attach_climax_context"].__globals__
    parent_globals["UNIVERSE"] = UNIVERSE
    attached, evidence = PARENT["attach_climax_context"](events)
    trades = pd.read_parquet(TRADE_CACHE)
    trades["session_date"] = pd.to_datetime(trades["session_date"])
    trades = trades.loc[trades["bar_idx"].eq(2), [
        "symbol", "session_date", "trade_available",
        "trade_location_volume_imbalance", "last_trade_edge_to_midpoint",
    ]]
    attached = attached.merge(trades, on=["symbol", "session_date"], how="left", validate="many_to_one")
    evidence.update({
        "trade_filter_source": "fixed [decision-1s, decision) Alpaca SIP aggregate",
        "available_opening_trade_rows_replicated": int(attached["trade_available"].fillna(False).sum()),
        "cross_section_contract": "all eligible symbols jointly ranked per session",
    })
    return attached, evidence


def parent_state(frame: pd.DataFrame) -> pd.Series:
    base = cast(pd.Series, PARENT["base_climax"](frame))
    return base & (frame["median_abs_ret3"] > frame["absolute_move_q75"])


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    base = parent_state(frame)
    valid = frame["trade_available"].fillna(False)
    if family == FAMILIES[0]:
        return base & valid
    if family == FAMILIES[1]:
        return base & valid & frame["last_trade_edge_to_midpoint"].lt(0)
    if family == FAMILIES[2]:
        return base & valid & frame["last_trade_edge_to_midpoint"].le(0)
    if family == FAMILIES[3]:
        return base & valid & frame["trade_location_volume_imbalance"].lt(0)
    if family == FAMILIES[4]:
        return base & valid & frame["trade_location_volume_imbalance"].gt(0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    value = -frame["ret1"] + frame["volume_rank"] - frame["range_pos"]
    if family in (FAMILIES[1], FAMILIES[2]):
        value = value - frame["last_trade_edge_to_midpoint"].rank(pct=True)
    elif family == FAMILIES[3]:
        value = value - frame["trade_location_volume_imbalance"].rank(pct=True)
    elif family == FAMILIES[4]:
        value = value + frame["trade_location_volume_imbalance"].rank(pct=True)
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    global TRADE_CACHE, UNIVERSE
    data_root = Path(args.data_root)
    TRADE_CACHE = data_root / "research/cache/us_market_event_trade_features_1s_v1.parquet"
    UNIVERSE = data_root / "data/catalog/monthly_universe/us-market-monthly-universe-b26117d72ec676735fcc132b/decisions.parquet"
    globals_ = BASE["run"].__globals__
    globals_.update({
        "FAMILIES": FAMILIES,
        "FIRST_VERSION": 17909,
        "PRIOR_COMPARISONS": 543_033,
        "TOP_COUNT_BY_DECISION": TOP_COUNTS,
        "attach_training_scales": attach_filtered_climax,
        "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v17909-v18008-trade-filtered-opening-climax"
    result["trade_filter_evidence"] = result.pop("training_only_scale_evidence")
    for item in result["results_by_development_rank"]:
        item["actual_decision_bar"] = 2
        item["top_count"] = TOP_COUNTS[item["decision_bar"]]
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17909-v18008 trade-filtered opening climax\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, top {best['top_count']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}" for name, value in best["development_oos"].items())
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO unless every gate, history supplement and native null pass.\n",
        "utf-8",
    )
    return cast(dict[str, Any], result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v17909-v18008-trade-filtered-climax.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
