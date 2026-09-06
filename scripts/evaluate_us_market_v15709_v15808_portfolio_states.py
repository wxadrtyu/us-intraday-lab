"""Evaluate portfolio-level state-timed liquid baskets."""

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
    "broad_oversold_liquid_rebound",
    "breadth_thrust_liquid_leaders",
    "high_dispersion_relative_winners",
    "high_dispersion_loser_reclaims",
    "concentrated_activity_liquid_leaders",
)
UNIVERSE: Path | None = None


def attach_portfolio_states(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if UNIVERSE is None:
        raise RuntimeError("monthly universe path was not bound")
    con = duckdb.connect()
    universe = con.execute(
        "SELECT symbol, month, median_dollar_volume FROM read_parquet(?) WHERE eligible=true",
        [str(UNIVERSE)]).fetch_df()
    con.close()
    universe["month"] = pd.to_datetime(universe["month"]).dt.to_period("M").dt.to_timestamp()
    universe["liquidity_rank"] = universe.groupby("month")["median_dollar_volume"].rank(pct=True)
    frame = events.copy()
    frame["month"] = frame["session_date"].dt.to_period("M").dt.to_timestamp()
    frame = frame.merge(universe[["symbol", "month", "liquidity_rank"]],
                        on=["symbol", "month"], how="inner", validate="many_to_one")
    keys = ["session_date", "bar_idx"]
    state = frame.groupby(keys, as_index=False).agg(
        market_ret3=("ret3", "median"),
        positive_breadth=("ret1", lambda values: float((values > 0).mean())),
        ret3_dispersion=("ret3", "std"), total_volume=("volume", "sum"))
    top = (frame.sort_values(keys + ["volume"], ascending=[True, True, False])
           .groupby(keys, sort=False).head(10).groupby(keys, as_index=False)["volume"].sum()
           .rename(columns={"volume": "top_volume"}))
    state = state.merge(top, on=keys, how="left", validate="one_to_one")
    training = state.loc[(state["session_date"] >= "2021-01-01")
                         & (state["session_date"] <= "2023-12-31")]
    threshold = training.groupby("bar_idx", as_index=False)["ret3_dispersion"].quantile(0.75)
    threshold = threshold.rename(columns={"ret3_dispersion": "dispersion_q75"})
    state = state.merge(threshold, on="bar_idx", how="left", validate="many_to_one")
    state["volume_concentration"] = state["top_volume"] / state["total_volume"]
    attached = frame.merge(state, on=keys, how="left", validate="many_to_one")
    return attached, {"portfolio_state_events": len(attached),
                      "method": "point-in-time liquid cohorts plus causal breadth and dispersion"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    liquid = frame["liquidity_rank"] > 0.75
    if family == FAMILIES[0]:
        return liquid & (frame["market_ret3"] < -0.003) & (frame["positive_breadth"] < 0.35)
    if family == FAMILIES[1]:
        return (liquid & (frame["market_ret3"] > 0.002)
                & (frame["positive_breadth"] > 0.65) & (frame["ret1"] > 0.0))
    if family == FAMILIES[2]:
        return (liquid & (frame["ret3_dispersion"] > frame["dispersion_q75"])
                & (frame["ret1_rank"] > 0.80))
    if family == FAMILIES[3]:
        return ((frame["ret3_dispersion"] > frame["dispersion_q75"])
                & (frame["ret3"].groupby([frame["session_date"], frame["bar_idx"]]).rank(pct=True) < 0.10)
                & (frame["ret1"] > 0.0))
    if family == FAMILIES[4]:
        return (liquid & (frame["volume_concentration"] > 0.20) & (frame["ret1"] > 0.0))
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["liquidity_rank"]
    if family in (FAMILIES[1], FAMILIES[2], FAMILIES[4]):
        return frame["ret1_rank"] + frame["liquidity_rank"]
    if family == FAMILIES[3]:
        return -frame["ret3"] + frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global UNIVERSE
    UNIVERSE = (Path(args.data_root) / "data" / "catalog" / "monthly_universe"
                / "us-market-monthly-universe-b26117d72ec676735fcc132b" / "decisions.parquet")
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15709, "PRIOR_COMPARISONS": 338_583,
        "attach_training_scales": attach_portfolio_states, "event_mask": event_mask,
        "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15709-v15808-portfolio-state-baskets"
    result["portfolio_state_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15709-v15808 portfolio state baskets\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15709-v15808-portfolio-states.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
