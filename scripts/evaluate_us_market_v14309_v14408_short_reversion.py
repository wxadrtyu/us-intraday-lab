"""Evaluate preregistered full-market 5-30 minute long-only reversal hypotheses.

The script deliberately discovers only provider manifests dated through 2026-03,
materializes a reusable 5-minute event cache, freezes development ranking on
2021-2025, and only then computes the consumed 2026Q1 diagnostic.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

FAMILIES = (
    "one_bar_cross_section_reversal",
    "three_bar_cross_section_reversal",
    "below_intraday_vwap_reclaim",
    "negative_return_with_volume_shock",
    "low_intraday_range_position_reclaim",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
FIRST_VERSION = 14309
PRIOR_COMPARISONS = 337_183


@dataclass(frozen=True)
class Variant:
    version: int
    family: str
    decision_bar: int
    holding_bars: int


def variants() -> list[Variant]:
    result: list[Variant] = []
    version = FIRST_VERSION
    for family in FAMILIES:
        for decision_bar in DECISION_BARS:
            for holding_bars in HOLDING_BARS:
                result.append(Variant(version, family, decision_bar, holding_bars))
                version += 1
    if version != 14409:
        raise AssertionError("preregistered grid must contain exactly 100 versions")
    return result


def discover_permitted_files(root: Path) -> list[Path]:
    staging = root / "data" / "staging" / "alpaca_iex_1min_dynamic"
    files: list[Path] = []
    for manifest in sorted(staging.glob("20??-??/*.json")):
        month = manifest.parent.name
        if not ("2021-01" <= month <= "2026-03"):
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("blind_test_candidate") is True:
            raise RuntimeError(f"blind manifest encountered in permitted range: {manifest}")
        if payload.get("strategy_metrics_permitted") is not True:
            raise RuntimeError(f"non-permitted manifest encountered: {manifest}")
        parquet = manifest.with_suffix(".parquet")
        if not parquet.exists():
            raise FileNotFoundError(parquet)
        files.append(parquet)
    if not files:
        raise RuntimeError("no permitted minute shards discovered")
    return files


def materialize_events(files: list[Path], cache: Path, rebuild: bool) -> None:
    if cache.exists() and not rebuild:
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    temp_cache = cache.with_suffix(".tmp.parquet")
    if temp_cache.exists():
        temp_cache.unlink()
    db_path = cache.with_suffix(".duckdb")
    con = duckdb.connect(str(db_path))
    con.execute(f"PRAGMA temp_directory='{cache.parent.as_posix()}/duckdb_tmp'")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    paths = [str(path) for path in files]
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE bars AS
        WITH minute_rows AS (
          SELECT symbol, session_date, timestamp, open, high, low, close, volume, vwap,
            CAST(FLOOR((EXTRACT(hour FROM timezone('America/New_York', timestamp)) * 60
              + EXTRACT(minute FROM timezone('America/New_York', timestamp)) - 570) / 5)
              AS INTEGER) AS bar_idx
          FROM read_parquet(?, union_by_name=true)
          WHERE session_date BETWEEN DATE '2021-01-01' AND DATE '2026-03-31'
        )
        SELECT symbol, session_date, bar_idx,
          arg_min(open, timestamp) AS open,
          max(high) AS high,
          min(low) AS low,
          arg_max(close, timestamp) AS close,
          sum(volume) AS volume,
          sum(vwap * volume) / nullif(sum(volume), 0) AS vwap,
          count(*) AS minute_count
        FROM minute_rows
        WHERE bar_idx BETWEEN 0 AND 77
        GROUP BY symbol, session_date, bar_idx
        """,
        [paths],
    )
    con.execute(
        """
        COPY (
          WITH enriched AS (
            SELECT *,
              lag(bar_idx, 1) OVER w AS lag1_idx,
              lag(close, 1) OVER w AS lag1_close,
              lag(bar_idx, 3) OVER w AS lag3_idx,
              lag(close, 3) OVER w AS lag3_close,
              sum(vwap * volume) OVER wr / nullif(sum(volume) OVER wr, 0) AS running_vwap,
              min(low) OVER wr AS running_low,
              max(high) OVER wr AS running_high,
              lead(bar_idx, 1) OVER w AS p1_idx, lead(open, 1) OVER w AS p1_open,
              lead(bar_idx, 2) OVER w AS p2_idx, lead(open, 2) OVER w AS p2_open,
              lead(bar_idx, 3) OVER w AS p3_idx, lead(open, 3) OVER w AS p3_open,
              lead(bar_idx, 5) OVER w AS p5_idx, lead(open, 5) OVER w AS p5_open,
              lead(bar_idx, 7) OVER w AS p7_idx, lead(open, 7) OVER w AS p7_open,
              lead(bar_idx, 8) OVER w AS p8_idx, lead(open, 8) OVER w AS p8_open
            FROM bars
            WINDOW w AS (PARTITION BY symbol, session_date ORDER BY bar_idx),
              wr AS (PARTITION BY symbol, session_date ORDER BY bar_idx
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          )
          SELECT symbol, session_date, bar_idx, volume,
            close / lag1_close - 1 AS ret1,
            close / lag3_close - 1 AS ret3,
            close / running_vwap - 1 AS vwap_dev,
            (close - running_low) / nullif(running_high - running_low, 0) AS range_pos,
            p1_open, p2_open, p3_open, p5_open, p7_open, p8_open
          FROM enriched
          WHERE bar_idx IN (2, 5, 11, 17, 23)
            AND minute_count = 5
            AND lag1_idx = bar_idx - 1 AND lag3_idx = bar_idx - 3
            AND p1_idx = bar_idx + 1 AND p2_idx = bar_idx + 2
            AND p3_idx = bar_idx + 3 AND p5_idx = bar_idx + 5
            AND p7_idx = bar_idx + 7 AND p8_idx = bar_idx + 8
            AND lag1_close > 0 AND lag3_close > 0 AND running_vwap > 0
            AND p1_open > 0 AND p2_open > 0 AND p3_open > 0
            AND p5_open > 0 AND p7_open > 0 AND p8_open > 0
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(temp_cache)],
    )
    con.close()
    os.replace(temp_cache, cache)


def metrics(returns: pd.Series) -> dict[str, float | int]:
    clean = returns.dropna().astype(float)
    n = len(clean)
    if n == 0:
        return {"sessions": 0, "total_return": math.nan, "annualized_return": math.nan,
                "max_drawdown": math.nan, "information_ratio": math.nan}
    wealth = (1.0 + clean).cumprod()
    total = float(wealth.iloc[-1] - 1.0)
    annual = float((1.0 + total) ** (252.0 / n) - 1.0) if total > -1 else -1.0
    drawdown = float((1.0 - wealth / wealth.cummax()).max())
    std = float(clean.std(ddof=1))
    ir = float(clean.mean() / std * math.sqrt(252.0)) if std > 0 else math.nan
    return {"sessions": n, "total_return": total, "annualized_return": annual,
            "max_drawdown": drawdown, "information_ratio": ir}


def score_events(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return 1.0 - frame["ret1_rank"]
    if family == FAMILIES[1]:
        return 1.0 - frame["ret3_rank"]
    if family == FAMILIES[2]:
        return 1.0 - frame["vwap_rank"] + 0.25 * frame["ret1_rank"]
    if family == FAMILIES[3]:
        return 1.0 - frame["ret3_rank"] + 0.5 * frame["volume_rank"]
    if family == FAMILIES[4]:
        return 1.0 - frame["range_rank"] + 0.25 * frame["ret1_rank"]
    raise ValueError(family)


def scenario_returns(selected: pd.DataFrame, holding: int) -> dict[str, pd.Series]:
    standard_exit = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}[holding]
    delayed_exit = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}[holding]
    raw = selected[standard_exit] / selected["p1_open"] - 1.0
    delayed = selected[delayed_exit] / selected["p2_open"] - 1.0
    by_day_raw = raw.groupby(selected["session_date"], sort=True).mean()
    by_day_delayed = delayed.groupby(selected["session_date"], sort=True).mean()
    return {
        "standard_9bp": by_day_raw - 0.0009,
        "cost_18bp": by_day_raw - 0.0018,
        "delay_5m_9bp": by_day_delayed - 0.0009,
    }


def period_metrics(series: pd.Series, start: str, end: str) -> dict[str, float | int]:
    index = pd.to_datetime(series.index)
    mask = (index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))
    return metrics(series.loc[mask])


def development_gate(scenarios: dict[str, pd.Series]) -> bool:
    for series in scenarios.values():
        item = period_metrics(series, "2024-01-01", "2025-12-31")
        if not (item["annualized_return"] >= 0.50 and item["max_drawdown"] < 0.20
                and item["information_ratio"] >= 1.0):
            return False
    return True


def robustness(series: pd.Series) -> dict[str, Any]:
    oos = series.loc[(pd.to_datetime(series.index) >= "2024-01-01")
                     & (pd.to_datetime(series.index) <= "2025-12-31")]
    chunks = np.array_split(oos, 5)
    fold_returns = [metrics(chunk)["total_return"] for chunk in chunks]
    offsets = (0, 20, 40, 60)
    starts = [metrics(oos.iloc[offset:])["total_return"] for offset in offsets]
    return {
        "fold_total_returns": fold_returns,
        "positive_folds": sum(value > 0 for value in fold_returns),
        "start_offset_total_returns": dict(zip(map(str, offsets), starts, strict=True)),
        "all_start_dates_positive": all(value > 0 for value in starts),
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False, default=str)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite(item) for item in value]
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    data_root = Path(args.data_root)
    files = discover_permitted_files(data_root)
    cache = data_root / "research" / "cache" / "v14309_v14408_events.parquet"
    materialize_events(files, cache, args.rebuild_cache)
    con = duckdb.connect()
    events = con.execute("SELECT * FROM read_parquet(?)", [str(cache)]).fetch_df()
    con.close()
    events["session_date"] = pd.to_datetime(events["session_date"])
    group_keys = ["session_date", "bar_idx"]
    for column, rank_column in (
        ("ret1", "ret1_rank"), ("ret3", "ret3_rank"),
        ("vwap_dev", "vwap_rank"), ("volume", "volume_rank"),
        ("range_pos", "range_rank"),
    ):
        events[rank_column] = events.groupby(group_keys, sort=False)[column].rank(pct=True)

    all_returns: dict[int, dict[str, pd.Series]] = {}
    records: list[dict[str, Any]] = []
    for family in FAMILIES:
        events["score"] = score_events(events, family)
        for decision in DECISION_BARS:
            subset = events.loc[events["bar_idx"] == decision].dropna(subset=["score"])
            chosen = (subset.sort_values(["session_date", "score", "symbol"],
                                         ascending=[True, False, True])
                      .groupby("session_date", sort=False).head(10))
            counts = chosen.groupby("session_date").size()
            chosen = chosen[chosen["session_date"].isin(counts[counts == 10].index)]
            for holding in HOLDING_BARS:
                version = FIRST_VERSION + FAMILIES.index(family) * 20 + DECISION_BARS.index(decision) * 4 + HOLDING_BARS.index(holding)
                returns = scenario_returns(chosen, holding)
                all_returns[version] = returns
                oos = {name: period_metrics(series, "2024-01-01", "2025-12-31")
                       for name, series in returns.items()}
                train = {name: period_metrics(series, "2021-01-01", "2023-12-31")
                         for name, series in returns.items()}
                records.append({
                    "version": version, "family": family, "decision_bar": decision,
                    "holding_bars": holding, "holding_minutes": holding * 5,
                    "development_train": train, "development_oos": oos,
                    "development_gate_passed": development_gate(returns),
                })

    # Freeze ranking before any consumed-period metric is computed.
    records.sort(key=lambda item: (
        item["development_gate_passed"],
        min(x["annualized_return"] for x in item["development_oos"].values()),
        min(x["information_ratio"] for x in item["development_oos"].values()),
    ), reverse=True)
    frozen_order = [item["version"] for item in records]
    by_version = {item["version"]: item for item in records}
    for rank, version in enumerate(frozen_order, start=1):
        item = by_version[version]
        item["development_rank"] = rank
        returns = all_returns[version]
        item["robustness_standard_9bp"] = robustness(returns["standard_9bp"])
        item["consumed_2026q1"] = {
            name: period_metrics(series, "2026-01-01", "2026-03-31")
            for name, series in returns.items()
        }
        standard_oos = returns["standard_9bp"].loc[
            (pd.to_datetime(returns["standard_9bp"].index) >= "2024-01-01")
            & (pd.to_datetime(returns["standard_9bp"].index) <= "2025-12-31")]
        t_stat, raw_p = stats.ttest_1samp(standard_oos, 0.0, alternative="greater")
        item["multiplicity"] = {
            "t_stat": float(t_stat), "raw_one_sided_p": float(raw_p),
            "cumulative_comparisons": PRIOR_COMPARISONS + len(records),
            "bonferroni_p": min(1.0, float(raw_p) * (PRIOR_COMPARISONS + len(records))),
        }

    grid = {(item["family"], item["decision_bar"], item["holding_bars"]): item
            for item in records}
    for item in records:
        neighbors: list[bool] = []
        for decision in DECISION_BARS:
            for holding in HOLDING_BARS:
                distance = (
                    abs(DECISION_BARS.index(decision) - DECISION_BARS.index(item["decision_bar"]))
                    + abs(HOLDING_BARS.index(holding) - HOLDING_BARS.index(item["holding_bars"]))
                )
                if distance == 1:
                    neighbors.append(
                        grid[(item["family"], decision, holding)]["development_gate_passed"]
                    )
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

    passed = [item for item in records if item["pre_null_gate_passed"]]
    result = {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "campaign_id": "v14309-v14408-cross-section-short-reversion",
        "dataset": {"shards_loaded": len(files), "events": len(events),
                    "cache": str(cache), "latest_loaded_session": str(events.session_date.max().date()),
                    "blind_files_loaded": 0},
        "ranking_frozen_before_consumed_diagnostic": True,
        "versions_completed": len(records), "pre_null_candidates": len(passed),
        "admitted_candidates": 0,
        "historical_gate": "UNAVAILABLE_REQUIRES_CANDIDATE_SPECIFIC_2018_2020_SUPPLEMENT",
        "elapsed_seconds": time.monotonic() - started,
        "results_by_development_rank": records,
    }
    result = finite(result)
    output = Path(args.output)
    atomic_json(output, result)
    best = records[0]
    md = output.with_suffix(".md")
    md.write_text(
        "# v14309-v14408 full-market short-reversion research\n\n"
        f"- Status: COMPLETE; versions: {len(records)}; admitted: 0\n"
        f"- Data: {len(files)} immutable shards, {len(events):,} decision events; blind files loaded: 0\n"
        f"- Best development version: v{best['version']} ({best['family']}, decision bar "
        f"{best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        f"- OOS 9bp annualized/MDD/IR: {best['development_oos']['standard_9bp']['annualized_return']:.2%} / "
        f"{best['development_oos']['standard_9bp']['max_drawdown']:.2%} / "
        f"{best['development_oos']['standard_9bp']['information_ratio']:.2f}\n"
        f"- OOS 18bp annualized/MDD/IR: {best['development_oos']['cost_18bp']['annualized_return']:.2%} / "
        f"{best['development_oos']['cost_18bp']['max_drawdown']:.2%} / "
        f"{best['development_oos']['cost_18bp']['information_ratio']:.2f}\n"
        f"- OOS delayed annualized/MDD/IR: {best['development_oos']['delay_5m_9bp']['annualized_return']:.2%} / "
        f"{best['development_oos']['delay_5m_9bp']['max_drawdown']:.2%} / "
        f"{best['development_oos']['delay_5m_9bp']['information_ratio']:.2f}\n"
        f"- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO. Historical 2018-2020 full-market minute supplement is unavailable; "
        "native null is not run unless every pre-null gate passes.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-06-v14309-v14408-cross-section-short-reversion.json")
    parser.add_argument("--rebuild-cache", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in (
        "status", "versions_completed", "pre_null_candidates", "admitted_candidates",
        "elapsed_seconds")}, indent=2))
