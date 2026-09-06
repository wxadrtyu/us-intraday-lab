"""Evaluate causal minute-OHLC body, close-location and wick-pressure hypotheses."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

import duckdb
import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_common",
)
FAMILIES = (
    "bullish_body_consensus",
    "close_location_accumulation",
    "lower_wick_rejection",
    "pressure_reacceleration",
    "low_wick_directional_pressure",
)
PRESSURE_CONTEXT: Path | None = None


def materialize_pressure_context(data_root: Path, output: Path) -> dict[str, int | str]:
    files = BASE["COMMON"]["discover_permitted_files"](data_root)
    if output.exists():
        con = duckdb.connect()
        rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(output)]).fetchone()[0]
        con.close()
        return {"cache": str(output), "rows": int(rows), "shards": len(files), "reused": "yes"}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.parquet")
    database = output.with_suffix(".duckdb")
    if temporary.exists():
        temporary.unlink()
    con = duckdb.connect(str(database))
    con.execute(f"PRAGMA temp_directory='{output.parent.as_posix()}/duckdb_pressure_tmp'")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute(
        """
        CREATE OR REPLACE TABLE minute_pressure AS
        SELECT symbol, session_date, timestamp, volume,
          CAST(FLOOR((EXTRACT(hour FROM timezone('America/New_York', timestamp)) * 60
            + EXTRACT(minute FROM timezone('America/New_York', timestamp)) - 570) / 5)
            AS INTEGER) AS bar_idx,
          (close - open) / nullif(high - low, 0) AS body_pressure,
          (close - low) / nullif(high - low, 0) AS close_location,
          (high - greatest(open, close)) / nullif(high - low, 0) AS upper_wick_fraction,
          (least(open, close) - low) / nullif(high - low, 0) AS lower_wick_fraction
        FROM read_parquet(?, union_by_name=true)
        WHERE session_date BETWEEN DATE '2021-01-01' AND DATE '2026-03-31'
        """,
        [[str(path) for path in files]],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE five_minute_pressure AS
        SELECT symbol, session_date, bar_idx,
          count(*) AS minute_count,
          count(body_pressure) AS valid_pressure_minutes,
          sum(body_pressure * volume) / nullif(sum(volume), 0) AS weighted_body_pressure,
          avg(CASE WHEN body_pressure > 0 THEN 1.0 ELSE 0.0 END) AS bullish_minute_share,
          avg(close_location) AS mean_close_location,
          arg_max(close_location, timestamp) AS final_close_location,
          avg(lower_wick_fraction) AS mean_lower_wick,
          avg(upper_wick_fraction) AS mean_upper_wick,
          avg(abs(body_pressure)) AS mean_absolute_body,
          arg_max(body_pressure, timestamp) AS final_minute_body_pressure
        FROM minute_pressure
        WHERE bar_idx BETWEEN 0 AND 77
        GROUP BY symbol, session_date, bar_idx
        """
    )
    con.execute(
        """
        COPY (
          WITH enriched AS (
            SELECT *,
              lag(bar_idx) OVER w AS prior_bar_idx,
              lag(weighted_body_pressure) OVER w AS prior_body_pressure,
              sum(minute_count) OVER wr AS running_minute_count
            FROM five_minute_pressure
            WINDOW w AS (PARTITION BY symbol, session_date ORDER BY bar_idx),
              wr AS (PARTITION BY symbol, session_date ORDER BY bar_idx
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          )
          SELECT symbol, session_date, bar_idx, weighted_body_pressure,
            bullish_minute_share, mean_close_location, final_close_location,
            mean_lower_wick, mean_upper_wick, mean_absolute_body,
            final_minute_body_pressure,
            weighted_body_pressure - prior_body_pressure AS pressure_change,
            mean_lower_wick - mean_upper_wick AS wick_balance,
            mean_lower_wick + mean_upper_wick AS total_wick_fraction
          FROM enriched
          WHERE bar_idx IN (2, 5, 11, 17, 23)
            AND minute_count = 5 AND valid_pressure_minutes = 5
            AND running_minute_count = (bar_idx + 1) * 5
            AND prior_bar_idx = bar_idx - 1 AND prior_body_pressure IS NOT NULL
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(temporary)],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(temporary)]).fetchone()[0]
    con.close()
    os.replace(temporary, output)
    return {"cache": str(output), "rows": int(rows), "shards": len(files), "reused": "no"}


def attach_pressure(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if PRESSURE_CONTEXT is None:
        raise RuntimeError("OHLC pressure context cache was not bound")
    con = duckdb.connect()
    context = con.execute("SELECT * FROM read_parquet(?)", [str(PRESSURE_CONTEXT)]).fetch_df()
    con.close()
    context["session_date"] = pd.to_datetime(context["session_date"])
    keys = ["session_date", "bar_idx"]
    for column in ("weighted_body_pressure", "wick_balance", "pressure_change"):
        context[f"{column}_rank"] = context.groupby(keys, sort=False)[column].rank(pct=True)
    attached = events.merge(context, on=["symbol", "session_date", "bar_idx"], how="inner", validate="one_to_one")
    return attached, {"pressure_events": len(attached), "method": "complete causal minute OHLC path"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["bullish_minute_share"] >= 0.80) & (frame["weighted_body_pressure"] > 0.25)
    if family == FAMILIES[1]:
        return (frame["mean_close_location"] > 0.70) & (frame["final_close_location"] > 0.75)
    if family == FAMILIES[2]:
        return (frame["wick_balance"] > 0.15) & (frame["final_close_location"] > 0.70)
    if family == FAMILIES[3]:
        return (frame["pressure_change"] > 0.40) & (frame["final_close_location"] > 0.70)
    if family == FAMILIES[4]:
        return (
            (frame["total_wick_fraction"] < 0.35)
            & (frame["mean_absolute_body"] > 0.45)
            & (frame["weighted_body_pressure"] > 0.20)
        )
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["bullish_minute_share"] + frame["weighted_body_pressure_rank"]
    if family == FAMILIES[1]:
        return frame["mean_close_location"] + frame["final_close_location"]
    if family == FAMILIES[2]:
        return frame["wick_balance_rank"] + frame["final_close_location"]
    if family == FAMILIES[3]:
        return frame["pressure_change_rank"] + frame["final_close_location"]
    if family == FAMILIES[4]:
        return frame["mean_absolute_body"] + frame["weighted_body_pressure_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global PRESSURE_CONTEXT
    data_root = Path(args.data_root)
    PRESSURE_CONTEXT = data_root / "research" / "cache" / "v16609_v16708_ohlc_pressure.parquet"
    cache_evidence = materialize_pressure_context(data_root, PRESSURE_CONTEXT)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16609,
            "PRIOR_COMPARISONS": 339_483,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_pressure,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16609-v16708-causal-ohlc-pressure"
    result["pressure_cache_evidence"] = cache_evidence
    result["ohlc_pressure_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16609-v16708 causal OHLC pressure\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; all hard gates and historical supplement remain mandatory.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v16609-v16708-ohlc-pressure.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
