"""Evaluate high-confidence consensus across distinct causal sources."""

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
    "climax_in_high_activity_state",
    "path_reclaim_after_range_expansion",
    "rising_liquidity_breadth_breakout",
    "liquid_oversold_volume_dryup",
    "three_source_consensus_vote",
)
UNIVERSE: Path | None = None


def attach_sources(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if UNIVERSE is None:
        raise RuntimeError("monthly universe path was not bound")
    con = duckdb.connect()
    universe = con.execute(
        "SELECT symbol, month, median_dollar_volume FROM read_parquet(?) WHERE eligible=true",
        [str(UNIVERSE)]).fetch_df()
    con.close()
    universe["month"] = pd.to_datetime(universe["month"]).dt.to_period("M").dt.to_timestamp()
    universe = universe.sort_values(["symbol", "month"])
    universe["prior_dv"] = universe.groupby("symbol")["median_dollar_volume"].shift(1)
    universe["dv_change"] = universe["median_dollar_volume"] / universe["prior_dv"] - 1.0
    universe["liquidity_rank"] = universe.groupby("month")["median_dollar_volume"].rank(pct=True)
    frame = events.copy()
    frame["month"] = frame["session_date"].dt.to_period("M").dt.to_timestamp()
    frame = frame.merge(universe[["symbol", "month", "dv_change", "liquidity_rank"]],
                        on=["symbol", "month"], how="inner", validate="many_to_one")
    keys = ["session_date", "bar_idx"]
    state = frame.groupby(keys, as_index=False).agg(
        market_ret3=("ret3", "median"),
        positive_breadth=("ret1", lambda values: float((values > 0).mean())),
        median_abs_ret3=("ret3", lambda values: float(values.abs().median())),
    )
    training = state.loc[(state["session_date"] >= "2021-01-01")
                         & (state["session_date"] <= "2023-12-31")]
    threshold = training.groupby("bar_idx", as_index=False)["median_abs_ret3"].quantile(0.75)
    threshold = threshold.rename(columns={"median_abs_ret3": "absolute_move_q75"})
    state = state.merge(threshold, on="bar_idx", how="left", validate="many_to_one")
    frame = frame.merge(state, on=keys, how="left", validate="many_to_one")
    frame["component_climax"] = ((frame["ret1"] < -0.010)
                                  & (frame["volume_rank"] >= 0.90)
                                  & (frame["range_pos"] <= 0.25))
    frame["component_path"] = ((frame["ret3"] < -0.008) & (frame["ret1"] > 0.0015))
    frame["component_participation"] = ((frame["dv_change"] > 0.50)
                                         & (frame["volume_to_prior"] > 1.25))
    frame["component_breadth"] = frame["positive_breadth"] > 0.55
    frame["component_liquidity"] = frame["liquidity_rank"] > 0.75
    frame["component_votes"] = sum(frame[column].astype(int) for column in (
        "component_climax", "component_path", "component_participation",
        "component_breadth", "component_liquidity"))
    return frame, {"enriched_events": len(frame),
                   "method": "five causal price, liquidity, breadth and point-in-time sources"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["component_climax"] & (frame["median_abs_ret3"] > frame["absolute_move_q75"])
    if family == FAMILIES[1]:
        return (frame["component_path"] & (frame["bar_range"] > 0.006)
                & (frame["volume_to_prior"] < 1.0))
    if family == FAMILIES[2]:
        return (frame["component_participation"] & frame["component_breadth"]
                & (frame["ret1"] > 0.003))
    if family == FAMILIES[3]:
        return (frame["component_liquidity"] & (frame["market_ret3"] < -0.002)
                & (frame["ret3"] < -0.006) & (frame["ret1"] > 0.0)
                & (frame["volume_to_prior"] < 0.8))
    if family == FAMILIES[4]:
        return frame["component_votes"] >= 3
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return -frame["ret1"] + frame["volume_rank"] - frame["range_pos"]
    if family == FAMILIES[1]:
        return -frame["ret3"] + frame["ret1_rank"] + frame["bar_range"]
    if family == FAMILIES[2]:
        return frame["dv_change"] + frame["volume_to_prior"] + frame["ret1_rank"]
    if family == FAMILIES[3]:
        return frame["liquidity_rank"] - frame["ret3"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return frame["component_votes"] + frame["ret1_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global UNIVERSE
    UNIVERSE = (Path(args.data_root) / "data" / "catalog" / "monthly_universe"
                / "us-market-monthly-universe-b26117d72ec676735fcc132b" / "decisions.parquet")
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update({
        "FAMILIES": FAMILIES, "FIRST_VERSION": 15809, "PRIOR_COMPARISONS": 338_683,
        "attach_training_scales": attach_sources, "event_mask": event_mask, "score": score,
    })
    result = BASE["run"](args)
    result["campaign_id"] = "v15809-v15908-cross-source-consensus"
    result["cross_source_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v15809-v15908 cross-source consensus\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v15809-v15908-cross-source.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
