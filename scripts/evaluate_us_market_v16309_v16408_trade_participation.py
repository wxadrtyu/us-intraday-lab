"""Evaluate causal trade-count participation microstructure hypotheses."""

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
    "block_participation_acceptance",
    "broad_participation_acceptance",
    "trade_count_reacceleration",
    "size_count_alignment",
    "opening_intensity_persistence",
)
TRADE_CONTEXT: Path | None = None


def materialize_trade_context(data_root: Path, output: Path) -> dict[str, int | str]:
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
    con.execute(f"PRAGMA temp_directory='{output.parent.as_posix()}/duckdb_trade_tmp'")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute(
        """
        CREATE OR REPLACE TABLE five_minute AS
        SELECT symbol, session_date,
          CAST(FLOOR((EXTRACT(hour FROM timezone('America/New_York', timestamp)) * 60
            + EXTRACT(minute FROM timezone('America/New_York', timestamp)) - 570) / 5)
            AS INTEGER) AS bar_idx,
          sum(volume) AS volume,
          sum(trade_count) AS trade_count,
          count(*) AS minute_count
        FROM read_parquet(?, union_by_name=true)
        WHERE session_date BETWEEN DATE '2021-01-01' AND DATE '2026-03-31'
        GROUP BY symbol, session_date, bar_idx
        """,
        [[str(path) for path in files]],
    )
    con.execute(
        """
        COPY (
          WITH enriched AS (
            SELECT *,
              lag(bar_idx) OVER w AS lag_bar_idx,
              lag(volume) OVER w AS lag_volume,
              lag(trade_count) OVER w AS lag_trade_count,
              first_value(trade_count) OVER wr AS opening_trade_count
            FROM five_minute
            WINDOW w AS (PARTITION BY symbol, session_date ORDER BY bar_idx),
              wr AS (PARTITION BY symbol, session_date ORDER BY bar_idx
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          )
          SELECT symbol, session_date, bar_idx, trade_count, lag_trade_count,
            opening_trade_count,
            trade_count / nullif(lag_trade_count, 0) AS trade_count_to_prior,
            trade_count / nullif(opening_trade_count, 0) AS trade_count_to_open,
            volume / nullif(trade_count, 0) AS average_trade_size,
            (volume / nullif(trade_count, 0)) /
              nullif(lag_volume / nullif(lag_trade_count, 0), 0) AS average_trade_size_to_prior
          FROM enriched
          WHERE bar_idx IN (2, 5, 11, 17, 23)
            AND minute_count = 5 AND lag_bar_idx = bar_idx - 1
            AND trade_count > 0 AND lag_trade_count > 0 AND opening_trade_count > 0
            AND volume > 0 AND lag_volume > 0
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(temporary)],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(temporary)]).fetchone()[0]
    con.close()
    os.replace(temporary, output)
    return {"cache": str(output), "rows": int(rows), "shards": len(files), "reused": "no"}


def attach_trade_context(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if TRADE_CONTEXT is None:
        raise RuntimeError("trade-count context cache was not bound")
    con = duckdb.connect()
    context = con.execute("SELECT * FROM read_parquet(?)", [str(TRADE_CONTEXT)]).fetch_df()
    con.close()
    context["session_date"] = pd.to_datetime(context["session_date"])
    keys = ["session_date", "bar_idx"]
    for column in ("trade_count", "average_trade_size", "trade_count_to_open"):
        context[f"{column}_rank"] = context.groupby(keys, sort=False)[column].rank(pct=True)
    attached = events.merge(
        context, on=["symbol", "session_date", "bar_idx"], how="inner", validate="one_to_one"
    )
    return attached, {
        "trade_context_events": len(attached),
        "method": "causal completed-bar trade count and average-trade-size decomposition",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (
            (frame["average_trade_size_rank"] > 0.90)
            & (frame["ret1"] > 0.0)
            & (frame["vwap_dev"] > 0.0)
        )
    if family == FAMILIES[1]:
        return (
            (frame["trade_count_rank"] > 0.90)
            & (frame["average_trade_size_rank"] < 0.60)
            & (frame["ret1"] > 0.0)
            & (frame["session_return"] > 0.0)
        )
    if family == FAMILIES[2]:
        return (
            (frame["trade_count_to_prior"] > 1.50)
            & (frame["volume_to_prior"] > 1.25)
            & (frame["ret1"] > 0.0)
        )
    if family == FAMILIES[3]:
        return (
            (frame["average_trade_size_rank"] > 0.80)
            & (frame["trade_count_rank"] > 0.80)
            & (frame["directional_efficiency"] > 0.60)
            & (frame["session_return"] > 0.0)
        )
    if family == FAMILIES[4]:
        return (
            (frame["trade_count_to_open_rank"] > 0.90)
            & (frame["session_return"] > 0.0)
            & (frame["range_pos"] > 0.60)
        )
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["average_trade_size_rank"] + frame["ret1_rank"]
    if family == FAMILIES[1]:
        return frame["trade_count_rank"] + frame["session_return"]
    if family == FAMILIES[2]:
        return frame["trade_count_to_prior"] + frame["volume_to_prior"] + frame["ret1_rank"]
    if family == FAMILIES[3]:
        return frame["average_trade_size_rank"] + frame["trade_count_rank"] + frame["session_return"]
    if family == FAMILIES[4]:
        return frame["trade_count_to_open_rank"] + frame["range_pos"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global TRADE_CONTEXT
    data_root = Path(args.data_root)
    TRADE_CONTEXT = data_root / "research" / "cache" / "v16309_v16408_trade_context.parquet"
    cache_evidence = materialize_trade_context(data_root, TRADE_CONTEXT)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16309,
            "PRIOR_COMPARISONS": 339_183,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_trade_context,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16309-v16408-trade-participation-microstructure"
    result["trade_count_cache_evidence"] = cache_evidence
    result["trade_participation_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16309-v16408 trade-participation microstructure\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, "
        f"hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD "
            f"{value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
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
    parser.add_argument(
        "--output",
        default="research/results/2026-09-07-v16309-v16408-trade-participation.json",
    )
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "status",
                    "versions_completed",
                    "pre_null_candidates",
                    "admitted_candidates",
                    "elapsed_seconds",
                )
            },
            indent=2,
        )
    )
