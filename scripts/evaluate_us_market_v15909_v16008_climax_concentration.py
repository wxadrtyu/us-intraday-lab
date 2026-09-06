"""Evaluate early volume-climax confirmations and concentration structures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import duckdb
import pandas as pd

BASE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14809_v14908_normalized_events.py")), run_name="v14809_common")
FAMILIES = (
    "high_absolute_market_activity",
    "high_point_in_time_liquidity",
    "broad_selloff",
    "idiosyncratic_downshock",
    "opening_liquidity_persistence",
)
LABELS = (2, 5, 11, 17, 23)
TOP_COUNTS = dict(zip(LABELS, (1, 2, 3, 5, 10), strict=True))
UNIVERSE: Path | None = None


def attach_climax_context(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if UNIVERSE is None:
        raise RuntimeError("monthly universe path was not bound")
    con = duckdb.connect()
    universe = con.execute(
        "SELECT symbol, month, median_dollar_volume FROM read_parquet(?) WHERE eligible=true",
        [str(UNIVERSE)]).fetch_df()
    con.close()
    universe["month"] = pd.to_datetime(universe["month"]).dt.to_period("M").dt.to_timestamp()
    universe["liquidity_rank"] = universe.groupby("month")["median_dollar_volume"].rank(pct=True)
    opening = events.loc[events["bar_idx"] == 2].copy()
    opening["month"] = opening["session_date"].dt.to_period("M").dt.to_timestamp()
    opening = opening.merge(universe[["symbol", "month", "liquidity_rank"]],
                            on=["symbol", "month"], how="inner", validate="many_to_one")
    state = opening.groupby("session_date", as_index=False).agg(
        market_ret1=("ret1", "median"),
        median_abs_ret3=("ret3", lambda values: float(values.abs().median())))
    training = state.loc[(state["session_date"] >= "2021-01-01")
                         & (state["session_date"] <= "2023-12-31")]
    q75 = float(training["median_abs_ret3"].quantile(0.75))
    opening = opening.merge(state, on="session_date", how="left", validate="many_to_one")
    opening["absolute_move_q75"] = q75
    parts = []
    for label in LABELS:
        part = opening.copy()
        part["bar_idx"] = label
        parts.append(part)
    attached = pd.concat(parts, ignore_index=True)
    return attached, {"opening_events": len(opening), "replicated_structure_events": len(attached),
                      "method": "actual bar 2 signal replicated across five concentration labels"}


def base_climax(frame: pd.DataFrame) -> pd.Series:
    return ((frame["ret1"] < -0.010) & (frame["volume_rank"] >= 0.90)
            & (frame["range_pos"] <= 0.25))


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    base = base_climax(frame)
    if family == FAMILIES[0]:
        return base & (frame["median_abs_ret3"] > frame["absolute_move_q75"])
    if family == FAMILIES[1]:
        return base & (frame["liquidity_rank"] > 0.75)
    if family == FAMILIES[2]:
        return base & (frame["market_ret1"] < -0.001)
    if family == FAMILIES[3]:
        return base & ((frame["ret1"] - frame["market_ret1"]) < -0.010)
    if family == FAMILIES[4]:
        return base & (frame["volume_to_open"] > 0.50)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    value = -frame["ret1"] + frame["volume_rank"] - frame["range_pos"]
    if family == FAMILIES[1]:
        value = value + frame["liquidity_rank"]
    if family == FAMILIES[2]:
        value = value - frame["market_ret1"]
    if family == FAMILIES[3]:
        value = value - (frame["ret1"] - frame["market_ret1"])
    if family == FAMILIES[4]:
        value = value + frame["volume_to_open"]
    return value


def run(args: argparse.Namespace) -> dict:
    global UNIVERSE
    UNIVERSE = (Path(args.data_root) / "data" / "catalog" / "monthly_universe"
                / "us-market-monthly-universe-b26117d72ec676735fcc132b" / "decisions.parquet")
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15909, "PRIOR_COMPARISONS": 338_783,
        "TOP_COUNT_BY_DECISION": TOP_COUNTS, "attach_training_scales": attach_climax_context,
        "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15909-v16008-climax-concentration"
    result["concentration_evidence"] = result.pop("training_only_scale_evidence")
    for item in result["results_by_development_rank"]:
        item["actual_decision_bar"] = 2
        item["top_count"] = TOP_COUNTS[item["decision_bar"]]
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15909-v16008 climax concentration\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, top {best['top_count']}, "
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
    parser.add_argument("--output", default="research/results/2026-09-07-v15909-v16008-climax-concentration.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
