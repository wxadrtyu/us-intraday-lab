"""Evaluate preregistered full-market 5-30 minute continuation hypotheses."""

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
    "one_bar_cross_section_momentum",
    "three_bar_cross_section_momentum",
    "above_intraday_vwap_continuation",
    "positive_return_with_volume_confirmation",
    "high_intraday_range_position_continuation",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
FIRST_VERSION = 14409
PRIOR_COMPARISONS = 337_283


def score_events(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["ret1_rank"]
    if family == FAMILIES[1]:
        return frame["ret3_rank"]
    if family == FAMILIES[2]:
        return frame["vwap_rank"] + 0.25 * frame["ret1_rank"]
    if family == FAMILIES[3]:
        return frame["ret3_rank"] + 0.5 * frame["volume_rank"]
    if family == FAMILIES[4]:
        return frame["range_rank"] + 0.25 * frame["ret1_rank"]
    raise ValueError(family)


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
        events["score"] = score_events(events, family)
        for decision_index, decision in enumerate(DECISION_BARS):
            subset = events.loc[events["bar_idx"] == decision].dropna(subset=["score"])
            chosen = (subset.sort_values(["session_date", "score", "symbol"],
                                         ascending=[True, False, True])
                      .groupby("session_date", sort=False).head(10))
            counts = chosen.groupby("session_date").size()
            chosen = chosen[chosen["session_date"].isin(counts[counts == 10].index)]
            for holding_index, holding in enumerate(HOLDING_BARS):
                version = FIRST_VERSION + family_index * 20 + decision_index * 4 + holding_index
                returns = COMMON["scenario_returns"](chosen, holding)
                all_returns[version] = returns
                oos = {name: COMMON["period_metrics"](series, "2024-01-01", "2025-12-31")
                       for name, series in returns.items()}
                train = {name: COMMON["period_metrics"](series, "2021-01-01", "2023-12-31")
                         for name, series in returns.items()}
                records.append({
                    "version": version, "family": family, "decision_bar": decision,
                    "holding_bars": holding, "holding_minutes": holding * 5,
                    "development_train": train, "development_oos": oos,
                    "development_gate_passed": COMMON["development_gate"](returns),
                })

    def ranking_value(value: float) -> float:
        return value if math.isfinite(value) else -math.inf

    records.sort(key=lambda item: (
        item["development_gate_passed"],
        ranking_value(min(x["annualized_return"] for x in item["development_oos"].values())),
        ranking_value(min(x["information_ratio"] for x in item["development_oos"].values())),
    ), reverse=True)
    frozen_order = [item["version"] for item in records]
    by_version = {item["version"]: item for item in records}
    for rank, version in enumerate(frozen_order, start=1):
        item = by_version[version]
        item["development_rank"] = rank
        returns = all_returns[version]
        item["robustness_standard_9bp"] = COMMON["robustness"](returns["standard_9bp"])
        item["consumed_2026q1"] = {
            name: COMMON["period_metrics"](series, "2026-01-01", "2026-03-31")
            for name, series in returns.items()
        }
        oos = returns["standard_9bp"].loc[
            (pd.to_datetime(returns["standard_9bp"].index) >= "2024-01-01")
            & (pd.to_datetime(returns["standard_9bp"].index) <= "2025-12-31")]
        if len(oos) >= 2:
            t_stat, raw_p = stats.ttest_1samp(oos, 0.0, alternative="greater")
        else:
            t_stat, raw_p = math.nan, 1.0
        item["multiplicity"] = {
            "t_stat": float(t_stat), "raw_one_sided_p": float(raw_p),
            "cumulative_comparisons": PRIOR_COMPARISONS + len(records),
            "bonferroni_p": min(1.0, float(raw_p) * (PRIOR_COMPARISONS + len(records))),
        }

    grid = {(x["family"], x["decision_bar"], x["holding_bars"]): x for x in records}
    for item in records:
        neighbors: list[bool] = []
        for decision in DECISION_BARS:
            for holding in HOLDING_BARS:
                distance = (
                    abs(DECISION_BARS.index(decision) - DECISION_BARS.index(item["decision_bar"]))
                    + abs(HOLDING_BARS.index(holding) - HOLDING_BARS.index(item["holding_bars"]))
                )
                if distance == 1:
                    neighbors.append(grid[(item["family"], decision, holding)]["development_gate_passed"])
        item["neighborhood"] = {
            "observations": len(neighbors), "pass_count": sum(neighbors),
            "pass_share": sum(neighbors) / len(neighbors) if neighbors else 0.0,
        }
        consumed_pass = all(x["total_return"] > 0.05 for x in item["consumed_2026q1"].values())
        robust = item["robustness_standard_9bp"]
        item["pre_null_gate_passed"] = bool(
            item["development_gate_passed"] and consumed_pass
            and robust["positive_folds"] >= 4 and robust["all_start_dates_positive"]
            and item["neighborhood"]["pass_share"] >= 0.70
            and item["multiplicity"]["bonferroni_p"] < 0.05
        )
        item["native_factory_null"] = "NOT_RUN_PRE_NULL_GATES_FAILED"
        item["final_admission"] = "NO_ADMISSION_HISTORICAL_2018_2020_UNAVAILABLE"

    result = COMMON["finite"]({
        "schema_version": "1.0.0", "status": "COMPLETE",
        "campaign_id": "v14409-v14508-cross-section-continuation",
        "dataset": {"shards_loaded": len(files), "events": len(events), "cache": str(cache),
                    "latest_loaded_session": str(events.session_date.max().date()),
                    "blind_files_loaded": 0},
        "ranking_frozen_before_consumed_diagnostic": True,
        "versions_completed": len(records),
        "pre_null_candidates": sum(x["pre_null_gate_passed"] for x in records),
        "admitted_candidates": 0,
        "historical_gate": "UNAVAILABLE_REQUIRES_CANDIDATE_SPECIFIC_2018_2020_SUPPLEMENT",
        "elapsed_seconds": time.monotonic() - started,
        "results_by_development_rank": records,
    })
    output = Path(args.output)
    COMMON["atomic_json"](output, result)
    best = records[0]
    output.with_suffix(".md").write_text(
        "# v14409-v14508 full-market continuation research\n\n"
        f"- Status: COMPLETE; versions: {len(records)}; admitted: 0\n"
        f"- Data: {len(files)} immutable shards, {len(events):,} events; blind files loaded: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, "
        f"hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD "
            f"{value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: "
        f"{best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; historical supplement and all remaining gates are required.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-06-v14409-v14508-cross-section-continuation.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
