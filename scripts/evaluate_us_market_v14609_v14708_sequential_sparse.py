"""Evaluate non-overlapping sequential sparse-event sleeves."""

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

SPARSE = run_path(str(Path(__file__).with_name(
    "evaluate_us_market_v14509_v14608_sparse_events.py")), run_name="v14509_common")
COMMON = SPARSE["COMMON"]
FAMILIES = SPARSE["FAMILIES"]
SCHEDULES = ((2, 11), (5, 17), (11, 23), (2, 23), (2, 11, 23))
HOLDINGS = (1, 2, 4, 6)
FIRST_VERSION = 14609
PRIOR_COMPARISONS = 337_483


def add_series(parts: list[pd.Series]) -> pd.Series:
    result = parts[0].copy()
    for part in parts[1:]:
        result = result.add(part, fill_value=0.0)
    return result.sort_index()


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

    records: list[dict[str, Any]] = []
    all_returns: dict[int, dict[str, pd.Series]] = {}
    for family_index, family in enumerate(FAMILIES):
        qualifying = events.loc[SPARSE["event_mask"](events, family)].copy()
        qualifying["score"] = SPARSE["event_score"](qualifying, family)
        decision_returns: dict[tuple[int, int], dict[str, pd.Series]] = {}
        decision_signal_dates: dict[int, set[pd.Timestamp]] = {}
        for decision in sorted({bar for schedule in SCHEDULES for bar in schedule}):
            calendar = pd.DatetimeIndex(sorted(events.loc[
                events["bar_idx"] == decision, "session_date"].unique()))
            subset = qualifying.loc[qualifying["bar_idx"] == decision].dropna(subset=["score"])
            selected = (subset.sort_values(["session_date", "score", "symbol"],
                                           ascending=[True, False, True])
                        .groupby("session_date", sort=False).head(10))
            decision_signal_dates[decision] = set(selected["session_date"].unique())
            for holding in HOLDINGS:
                decision_returns[(decision, holding)] = SPARSE["sparse_returns"](
                    selected, holding, calendar)

        for schedule_index, schedule in enumerate(SCHEDULES):
            for holding_index, holding in enumerate(HOLDINGS):
                version = FIRST_VERSION + family_index * 20 + schedule_index * 4 + holding_index
                scenarios = {
                    name: add_series([decision_returns[(bar, holding)][name] for bar in schedule])
                    for name in ("standard_9bp", "cost_18bp", "delay_5m_9bp")
                }
                all_returns[version] = scenarios
                signal_dates = set().union(*(decision_signal_dates[bar] for bar in schedule))
                records.append({
                    "version": version, "family": family, "decision_schedule": list(schedule),
                    "holding_bars": holding, "holding_minutes": holding * 5,
                    "signal_sessions": len(signal_dates),
                    "development_train": {name: COMMON["period_metrics"](
                        series, "2021-01-01", "2023-12-31") for name, series in scenarios.items()},
                    "development_oos": {name: COMMON["period_metrics"](
                        series, "2024-01-01", "2025-12-31") for name, series in scenarios.items()},
                    "development_gate_passed": COMMON["development_gate"](scenarios),
                })

    def safe(value: float) -> float:
        return value if math.isfinite(value) else -math.inf

    records.sort(key=lambda item: (
        item["development_gate_passed"],
        safe(min(x["annualized_return"] for x in item["development_oos"].values())),
        safe(min(x["information_ratio"] for x in item["development_oos"].values())),
    ), reverse=True)
    by_version = {item["version"]: item for item in records}
    for rank, version in enumerate([item["version"] for item in records], start=1):
        item = by_version[version]
        item["development_rank"] = rank
        scenarios = all_returns[version]
        item["robustness_standard_9bp"] = COMMON["robustness"](scenarios["standard_9bp"])
        item["consumed_2026q1"] = {name: COMMON["period_metrics"](
            series, "2026-01-01", "2026-03-31") for name, series in scenarios.items()}
        oos = scenarios["standard_9bp"].loc[
            (scenarios["standard_9bp"].index >= "2024-01-01")
            & (scenarios["standard_9bp"].index <= "2025-12-31")]
        t_stat, raw_p = stats.ttest_1samp(oos, 0.0, alternative="greater")
        item["multiplicity"] = {"t_stat": float(t_stat), "raw_one_sided_p": float(raw_p),
                                "cumulative_comparisons": PRIOR_COMPARISONS + 100,
                                "bonferroni_p": min(1.0, float(raw_p) * (PRIOR_COMPARISONS + 100))}

    grid = {(x["family"], tuple(x["decision_schedule"]), x["holding_bars"]): x for x in records}
    for item in records:
        neighbors: list[bool] = []
        schedule_index = SCHEDULES.index(tuple(item["decision_schedule"]))
        holding_index = HOLDINGS.index(item["holding_bars"])
        for schedule_delta, holding_delta in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            si, hi = schedule_index + schedule_delta, holding_index + holding_delta
            if 0 <= si < len(SCHEDULES) and 0 <= hi < len(HOLDINGS):
                neighbors.append(grid[(item["family"], SCHEDULES[si], HOLDINGS[hi])][
                    "development_gate_passed"])
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
        "campaign_id": "v14609-v14708-sequential-sparse-sleeves",
        "dataset": {"shards_loaded": len(files), "events": len(events), "cache": str(cache),
                    "latest_loaded_session": str(events.session_date.max().date()),
                    "blind_files_loaded": 0},
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
        "# v14609-v14708 sequential sparse sleeves\n\n"
        f"- Status: COMPLETE; versions: {len(records)}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, schedule "
        f"{best['decision_schedule']}, hold {best['holding_minutes']}m)\n"
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
    parser.add_argument("--output", default="research/results/2026-09-06-v14609-v14708-sequential-sparse-sleeves.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
