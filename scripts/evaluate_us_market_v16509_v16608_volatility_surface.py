"""Evaluate causal minute-level realized-volatility surface hypotheses."""

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
    "positive_semivariance_dominance",
    "smooth_information_diffusion",
    "positive_jump_acceptance",
    "volatility_reacceleration",
    "volatility_contraction_persistence",
)
VOLATILITY_CONTEXT: Path | None = None


def materialize_volatility_context(data_root: Path, output: Path) -> dict[str, int | str]:
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
    con.execute(f"PRAGMA temp_directory='{output.parent.as_posix()}/duckdb_volatility_tmp'")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute(
        """
        CREATE OR REPLACE TABLE minute_returns AS
        WITH ordered AS (
          SELECT symbol, session_date, timestamp, close,
            CAST(FLOOR((EXTRACT(hour FROM timezone('America/New_York', timestamp)) * 60
              + EXTRACT(minute FROM timezone('America/New_York', timestamp)) - 570) / 5)
              AS INTEGER) AS bar_idx,
            lag(close) OVER (PARTITION BY symbol, session_date ORDER BY timestamp) AS prior_close
          FROM read_parquet(?, union_by_name=true)
          WHERE session_date BETWEEN DATE '2021-01-01' AND DATE '2026-03-31'
        )
        SELECT *, close / nullif(prior_close, 0) - 1 AS minute_return
        FROM ordered WHERE bar_idx BETWEEN 0 AND 77
        """,
        [[str(path) for path in files]],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE five_minute_volatility AS
        SELECT symbol, session_date, bar_idx,
          count(*) AS raw_minute_count,
          count(minute_return) AS return_count,
          sum(pow(minute_return, 2)) AS bar_variance,
          sum(CASE WHEN minute_return > 0 THEN pow(minute_return, 2) ELSE 0 END) AS bar_up_variance,
          sum(CASE WHEN minute_return < 0 THEN pow(minute_return, 2) ELSE 0 END) AS bar_down_variance,
          max(greatest(minute_return, 0)) AS max_positive_jump,
          min(least(minute_return, 0)) AS max_negative_jump
        FROM minute_returns
        GROUP BY symbol, session_date, bar_idx
        """
    )
    con.execute(
        """
        COPY (
          WITH surface AS (
            SELECT *,
              sum(raw_minute_count) OVER wr AS running_minute_count,
              sum(bar_variance) OVER wr AS running_variance,
              sum(bar_up_variance) OVER wr AS running_up_variance,
              sum(bar_down_variance) OVER wr AS running_down_variance,
              max(max_positive_jump) OVER wr AS running_max_positive_jump,
              min(max_negative_jump) OVER wr AS running_max_negative_jump,
              lag(bar_variance) OVER w AS prior_bar_variance,
              lag(bar_idx) OVER w AS prior_bar_idx
            FROM five_minute_volatility
            WINDOW w AS (PARTITION BY symbol, session_date ORDER BY bar_idx),
              wr AS (PARTITION BY symbol, session_date ORDER BY bar_idx
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          )
          SELECT symbol, session_date, bar_idx,
            sqrt(running_variance) AS realized_volatility,
            running_up_variance / nullif(running_variance, 0) AS upside_variance_share,
            greatest(running_max_positive_jump, abs(running_max_negative_jump)) /
              nullif(sqrt(running_variance), 0) AS jump_concentration,
            (running_max_positive_jump - abs(running_max_negative_jump)) /
              nullif(running_max_positive_jump + abs(running_max_negative_jump), 0) AS signed_jump_balance,
            bar_variance / nullif(prior_bar_variance, 0) AS volatility_acceleration,
            bar_up_variance / nullif(bar_variance, 0) AS current_upside_variance_share
          FROM surface
          WHERE bar_idx IN (2, 5, 11, 17, 23)
            AND raw_minute_count = 5
            AND running_minute_count = (bar_idx + 1) * 5
            AND prior_bar_idx = bar_idx - 1
            AND running_variance > 0 AND prior_bar_variance > 0
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(temporary)],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(temporary)]).fetchone()[0]
    con.close()
    os.replace(temporary, output)
    return {"cache": str(output), "rows": int(rows), "shards": len(files), "reused": "no"}


def attach_volatility_surface(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if VOLATILITY_CONTEXT is None:
        raise RuntimeError("volatility context cache was not bound")
    con = duckdb.connect()
    context = con.execute("SELECT * FROM read_parquet(?)", [str(VOLATILITY_CONTEXT)]).fetch_df()
    con.close()
    context["session_date"] = pd.to_datetime(context["session_date"])
    keys = ["session_date", "bar_idx"]
    for column in ("realized_volatility", "volatility_acceleration", "signed_jump_balance"):
        context[f"{column}_rank"] = context.groupby(keys, sort=False)[column].rank(pct=True)
    attached = events.merge(context, on=["symbol", "session_date", "bar_idx"], how="inner", validate="one_to_one")
    return attached, {
        "volatility_surface_events": len(attached),
        "method": "causal complete minute path through decision bar",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["upside_variance_share"] > 0.70) & (frame["realized_volatility_rank"] > 0.60)
    if family == FAMILIES[1]:
        return (
            (frame["jump_concentration"] < 0.45)
            & (frame["directional_efficiency"] > 0.70)
            & (frame["session_return"] > 0.0)
        )
    if family == FAMILIES[2]:
        return (
            (frame["signed_jump_balance"] > 0.35)
            & (frame["range_pos"] > 0.70)
            & (frame["session_return"] > 0.0)
        )
    if family == FAMILIES[3]:
        return (
            (frame["volatility_acceleration"] > 2.0)
            & (frame["current_upside_variance_share"] > 0.65)
            & (frame["ret1"] > 0.0)
        )
    if family == FAMILIES[4]:
        return (
            (frame["volatility_acceleration"] < 0.50)
            & (frame["directional_efficiency"] > 0.70)
            & (frame["session_return"] > 0.0)
        )
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["upside_variance_share"] + frame["realized_volatility_rank"]
    if family == FAMILIES[1]:
        return frame["directional_efficiency"] - frame["jump_concentration"]
    if family == FAMILIES[2]:
        return frame["signed_jump_balance"] + frame["range_pos"]
    if family == FAMILIES[3]:
        return frame["volatility_acceleration_rank"] + frame["current_upside_variance_share"]
    if family == FAMILIES[4]:
        return frame["directional_efficiency"] - frame["volatility_acceleration_rank"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global VOLATILITY_CONTEXT
    data_root = Path(args.data_root)
    VOLATILITY_CONTEXT = data_root / "research" / "cache" / "v16509_v16608_volatility_surface.parquet"
    cache_evidence = materialize_volatility_context(data_root, VOLATILITY_CONTEXT)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16509,
            "PRIOR_COMPARISONS": 339_383,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_volatility_surface,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16509-v16608-causal-volatility-surface"
    result["volatility_cache_evidence"] = cache_evidence
    result["volatility_surface_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16509-v16608 causal volatility surface\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v16509-v16608-volatility-surface.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
