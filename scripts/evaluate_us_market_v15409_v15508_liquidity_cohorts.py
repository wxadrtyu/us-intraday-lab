"""Evaluate point-in-time monthly liquidity cohort event signals."""

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
    "high_liquidity_downshock_reversal",
    "high_liquidity_up_continuation",
    "rising_liquidity_breakout",
    "falling_liquidity_exhaustion",
    "mid_liquidity_vwap_reclaim",
)
UNIVERSE: Path | None = None


def attach_liquidity_cohorts(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if UNIVERSE is None:
        raise RuntimeError("monthly universe path was not bound")
    con = duckdb.connect()
    universe = con.execute(
        "SELECT symbol, month, median_dollar_volume FROM read_parquet(?) WHERE eligible = true",
        [str(UNIVERSE)],
    ).fetch_df()
    con.close()
    universe["month"] = pd.to_datetime(universe["month"]).dt.to_period("M").dt.to_timestamp()
    universe = universe.sort_values(["symbol", "month"])
    universe["prior_dollar_volume"] = universe.groupby("symbol")["median_dollar_volume"].shift(1)
    universe["dollar_volume_change"] = (
        universe["median_dollar_volume"] / universe["prior_dollar_volume"] - 1.0)
    universe["liquidity_rank"] = universe.groupby("month")["median_dollar_volume"].rank(pct=True)
    attached = events.copy()
    attached["month"] = attached["session_date"].dt.to_period("M").dt.to_timestamp()
    attached = attached.merge(universe, on=["symbol", "month"], how="inner",
                              validate="many_to_one")
    return attached, {"cohort_events": len(attached),
                      "method": "point-in-time monthly eligible median-dollar-volume rank and change"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return ((frame["liquidity_rank"] > 0.75) & (frame["ret1"] < -0.005)
                & (frame["volume_to_prior"] > 1.25))
    if family == FAMILIES[1]:
        return ((frame["liquidity_rank"] > 0.75) & (frame["ret3"] > 0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[2]:
        return ((frame["dollar_volume_change"] > 0.50) & (frame["ret1"] > 0.003)
                & (frame["volume_to_prior"] > 1.25))
    if family == FAMILIES[3]:
        return ((frame["dollar_volume_change"] < -0.30) & (frame["ret3"] < -0.008)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[4]:
        return ((frame["liquidity_rank"].between(0.25, 0.75))
                & (frame["vwap_dev"] < -0.006) & (frame["ret1"] > 0.001))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return -frame["ret1"] + frame["volume_to_prior"] + frame["liquidity_rank"]
    if family == FAMILIES[1]:
        return frame["ret3"] + frame["ret1_rank"] + frame["liquidity_rank"]
    if family == FAMILIES[2]:
        return frame["dollar_volume_change"] + frame["ret1_rank"] + frame["volume_to_prior"]
    if family == FAMILIES[3]:
        return -frame["dollar_volume_change"] - frame["ret3"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return -frame["vwap_dev"] + frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global UNIVERSE
    UNIVERSE = (Path(args.data_root) / "data" / "catalog" / "monthly_universe"
                / "us-market-monthly-universe-b26117d72ec676735fcc132b" / "decisions.parquet")
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15409, "PRIOR_COMPARISONS": 338_283,
        "attach_training_scales": attach_liquidity_cohorts, "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15409-v15508-point-in-time-liquidity-cohorts"
    result["point_in_time_liquidity_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15409-v15508 point-in-time liquidity cohorts\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15409-v15508-liquidity-cohorts.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
