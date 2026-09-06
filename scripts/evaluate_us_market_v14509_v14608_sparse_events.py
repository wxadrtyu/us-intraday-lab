"""Evaluate preregistered sparse full-market intraday event hypotheses."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from runpy import run_path
from typing import Any

import duckdb
import pandas as pd
from scipy import stats

COMMON = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14309_v14408_short_reversion.py")), run_name="v14309_common")
FAMILIES = (
    "downside_exhaustion_reclaim",
    "upside_impulse_continuation",
    "volume_climax_reversal",
    "deep_vwap_reclaim",
    "range_breakout_confirmation",
)
DECISIONS = (2, 5, 11, 17, 23)
HOLDINGS = (1, 2, 4, 6)
FIRST_VERSION = 14509
PRIOR_COMPARISONS = 337_383


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["ret3"] < -0.015) & (frame["ret1"] > 0.001)
    if family == FAMILIES[1]:
        return (frame["ret3"] > 0.015) & (frame["ret1"] > 0.0)
    if family == FAMILIES[2]:
        return ((frame["ret1"] < -0.010) & (frame["volume_rank"] >= 0.90)
                & (frame["range_pos"] <= 0.25))
    if family == FAMILIES[3]:
        return (frame["vwap_dev"] < -0.008) & (frame["ret1"] > 0.001)
    if family == FAMILIES[4]:
        return ((frame["ret3"] > 0.012) & (frame["range_pos"] >= 0.85)
                & (frame["volume_rank"] >= 0.75))
    raise ValueError(family)


def event_score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return 1.0 - frame["ret3_rank"] + frame["ret1_rank"]
    if family == FAMILIES[1]:
        return frame["ret3_rank"] + frame["ret1_rank"]
    if family == FAMILIES[2]:
        return 1.0 - frame["ret1_rank"] + frame["volume_rank"] - frame["range_rank"]
    if family == FAMILIES[3]:
        return 1.0 - frame["vwap_rank"] + frame["ret1_rank"]
    if family == FAMILIES[4]:
        return frame["ret3_rank"] + frame["range_rank"] + frame["volume_rank"]
    raise ValueError(family)


def sparse_returns(
    selected: pd.DataFrame, holding: int, calendar: pd.DatetimeIndex
) -> dict[str, pd.Series]:
    standard_exit = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}[holding]
    delayed_exit = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}[holding]
    raw = (selected[standard_exit] / selected["p1_open"] - 1.0).groupby(
        selected["session_date"]).mean().reindex(calendar, fill_value=0.0)
    delayed = (selected[delayed_exit] / selected["p2_open"] - 1.0).groupby(
        selected["session_date"]).mean().reindex(calendar, fill_value=0.0)
    traded = pd.Series(0.0, index=calendar)
    traded.loc[selected["session_date"].drop_duplicates()] = 1.0
    return {
        "standard_9bp": raw - traded * 0.0009,
        "cost_18bp": raw - traded * 0.0018,
        "delay_5m_9bp": delayed - traded * 0.0009,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    data_root = Path(args.data_root)
    files = COMMON["discover_permitted_files"](data_root)
    cache = data_root / "research" / "cache" / "v14309_v14408_events.parquet"
    COMMON["materialize_events"](files, cache, False)
    con = duckdb.connect()
    events = con.execute("SELECT * FROM read_parquet(?)", [str(cache)]).fetch_df()
    con.close()
    events["session_date"] = pd.to_datetime(events["session_date"])
    keys = ["session_date", "bar_idx"]
    for column, rank_column in (
        ("ret1", "ret1_rank"), ("ret3", "ret3_rank"),
        ("vwap_dev", "vwap_rank"), ("volume", "volume_rank"),
        ("range_pos", "range_rank"),
    ):
        events[rank_column] = events.groupby(keys, sort=False)[column].rank(pct=True)

    all_returns: dict[int, dict[str, pd.Series]] = {}
    records: list[dict[str, Any]] = []
    for family_index, family in enumerate(FAMILIES):
        qualifying = events.loc[event_mask(events, family)].copy()
        qualifying["score"] = event_score(qualifying, family)
        for decision_index, decision in enumerate(DECISIONS):
            calendar = pd.DatetimeIndex(sorted(events.loc[
                events["bar_idx"] == decision, "session_date"].unique()))
            subset = qualifying.loc[qualifying["bar_idx"] == decision].dropna(subset=["score"])
            selected = (subset.sort_values(["session_date", "score", "symbol"],
                                           ascending=[True, False, True])
                        .groupby("session_date", sort=False).head(10))
            for holding_index, holding in enumerate(HOLDINGS):
                version = FIRST_VERSION + family_index * 20 + decision_index * 4 + holding_index
                returns = sparse_returns(selected, holding, calendar)
                all_returns[version] = returns
                records.append({
                    "version": version, "family": family, "decision_bar": decision,
                    "holding_bars": holding, "holding_minutes": holding * 5,
                    "signal_sessions": int(selected["session_date"].nunique()),
                    "selected_stock_events": len(selected),
                    "development_train": {name: COMMON["period_metrics"](
                        series, "2021-01-01", "2023-12-31") for name, series in returns.items()},
                    "development_oos": {name: COMMON["period_metrics"](
                        series, "2024-01-01", "2025-12-31") for name, series in returns.items()},
                    "development_gate_passed": COMMON["development_gate"](returns),
                })

    def safe(value: float) -> float:
        return value if math.isfinite(value) else -math.inf

    records.sort(key=lambda x: (
        x["development_gate_passed"],
        safe(min(y["annualized_return"] for y in x["development_oos"].values())),
        safe(min(y["information_ratio"] for y in x["development_oos"].values())),
    ), reverse=True)
    by_version = {item["version"]: item for item in records}
    for rank, version in enumerate([item["version"] for item in records], start=1):
        item = by_version[version]
        item["development_rank"] = rank
        returns = all_returns[version]
        item["robustness_standard_9bp"] = COMMON["robustness"](returns["standard_9bp"])
        item["consumed_2026q1"] = {name: COMMON["period_metrics"](
            series, "2026-01-01", "2026-03-31") for name, series in returns.items()}
        oos = returns["standard_9bp"].loc[
            (returns["standard_9bp"].index >= "2024-01-01")
            & (returns["standard_9bp"].index <= "2025-12-31")]
        t_stat, raw_p = stats.ttest_1samp(oos, 0.0, alternative="greater")
        item["multiplicity"] = {"t_stat": float(t_stat), "raw_one_sided_p": float(raw_p),
                                "cumulative_comparisons": PRIOR_COMPARISONS + 100,
                                "bonferroni_p": min(1.0, float(raw_p) * (PRIOR_COMPARISONS + 100))}

    grid = {(x["family"], x["decision_bar"], x["holding_bars"]): x for x in records}
    for item in records:
        neighbors = []
        for decision in DECISIONS:
            for holding in HOLDINGS:
                distance = (abs(DECISIONS.index(decision) - DECISIONS.index(item["decision_bar"]))
                            + abs(HOLDINGS.index(holding) - HOLDINGS.index(item["holding_bars"])))
                if distance == 1:
                    neighbors.append(grid[(item["family"], decision, holding)]["development_gate_passed"])
        item["neighborhood"] = {"observations": len(neighbors), "pass_count": sum(neighbors),
                                "pass_share": sum(neighbors) / len(neighbors) if neighbors else 0.0}
        robust = item["robustness_standard_9bp"]
        consumed = all(x["total_return"] > 0.05 for x in item["consumed_2026q1"].values())
        item["pre_null_gate_passed"] = bool(
            item["development_gate_passed"] and consumed and robust["positive_folds"] >= 4
            and robust["all_start_dates_positive"] and item["neighborhood"]["pass_share"] >= 0.70
            and item["multiplicity"]["bonferroni_p"] < 0.05)
        item["native_factory_null"] = "NOT_RUN_PRE_NULL_GATES_FAILED"
        item["final_admission"] = "NO_ADMISSION_HISTORICAL_2018_2020_UNAVAILABLE"

    result = COMMON["finite"]({
        "schema_version": "1.0.0", "status": "COMPLETE",
        "campaign_id": "v14509-v14608-sparse-event-alpha",
        "dataset": {"shards_loaded": len(files), "events": len(events), "cache": str(cache),
                    "latest_loaded_session": str(events.session_date.max().date()), "blind_files_loaded": 0},
        "ranking_frozen_before_consumed_diagnostic": True, "versions_completed": len(records),
        "pre_null_candidates": sum(x["pre_null_gate_passed"] for x in records),
        "admitted_candidates": 0,
        "historical_gate": "UNAVAILABLE_REQUIRES_CANDIDATE_SPECIFIC_2018_2020_SUPPLEMENT",
        "elapsed_seconds": time.monotonic() - started, "results_by_development_rank": records,
    })
    output = Path(args.output)
    COMMON["atomic_json"](output, result)
    best = records[0]
    output.with_suffix(".md").write_text(
        "# v14509-v14608 sparse event alpha\n\n"
        f"- Status: COMPLETE; versions: {len(records)}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold "
        f"{best['holding_minutes']}m, signal sessions {best['signal_sessions']})\n"
        + "\n".join(f"- {name}: annualized {value['annualized_return']:.2%}, MDD "
                     f"{value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
                     for name, value in best["development_oos"].items())
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; all gates including historical supplement remain mandatory.\n",
        encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-06-v14509-v14608-sparse-event-alpha.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
