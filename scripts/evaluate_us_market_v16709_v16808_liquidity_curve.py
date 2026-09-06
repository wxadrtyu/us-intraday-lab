"""Evaluate complete-path intrabar liquidity timing hypotheses."""

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
    "backloaded_positive_volume",
    "backload_transition",
    "participation_reacceleration",
    "opening_decay_stabilization",
    "late_minute_confirmation",
)
LIQUIDITY_CONTEXT: Path | None = None


def materialize_liquidity_context(data_root: Path, output: Path) -> dict[str, int | str]:
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
    con.execute(f"PRAGMA temp_directory='{output.parent.as_posix()}/duckdb_liquidity_tmp'")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute(
        """
        CREATE OR REPLACE TABLE minute_participation AS
        WITH ordered AS (
          SELECT symbol, session_date, timestamp, volume, trade_count,
            CAST(EXTRACT(hour FROM timezone('America/New_York', timestamp)) * 60
              + EXTRACT(minute FROM timezone('America/New_York', timestamp)) - 570 AS INTEGER)
              AS minute_from_open,
            close / nullif(lag(close) OVER (
              PARTITION BY symbol, session_date ORDER BY timestamp), 0) - 1 AS minute_return
          FROM read_parquet(?, union_by_name=true)
          WHERE session_date BETWEEN DATE '2021-01-01' AND DATE '2026-03-31'
        )
        SELECT *, CAST(FLOOR(minute_from_open / 5) AS INTEGER) AS bar_idx,
          minute_from_open % 5 AS minute_slot
        FROM ordered WHERE minute_from_open BETWEEN 0 AND 389
        """,
        [[str(path) for path in files]],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE five_minute_participation AS
        SELECT symbol, session_date, bar_idx,
          count(*) AS minute_count,
          sum(volume) AS bar_volume,
          sum(trade_count) AS bar_trade_count,
          sum(CASE WHEN minute_slot >= 3 THEN volume ELSE 0 END) / nullif(sum(volume), 0)
            AS backload_volume_share,
          sum(CASE WHEN minute_slot >= 3 THEN trade_count ELSE 0 END) /
            nullif(sum(trade_count), 0) AS backload_trade_share,
          sum(sign(minute_return) * volume) / nullif(sum(volume), 0) AS signed_volume_imbalance,
          sum(sign(minute_return) * trade_count) / nullif(sum(trade_count), 0)
            AS signed_trade_imbalance,
          sum(CASE WHEN minute_slot >= 3 AND minute_return > 0 THEN volume ELSE 0 END) /
            nullif(sum(volume), 0) AS positive_backload_volume_share,
          arg_max(minute_return, timestamp) AS final_minute_return,
          sum((minute_slot - 2) * volume) / nullif(2 * sum(volume), 0) AS volume_slope
        FROM minute_participation
        GROUP BY symbol, session_date, bar_idx
        """
    )
    con.execute(
        """
        COPY (
          WITH enriched AS (
            SELECT *,
              lag(bar_idx, 1) OVER w AS prior_bar_idx,
              lag(bar_idx, 2) OVER w AS prior2_bar_idx,
              lag(bar_volume, 1) OVER w AS prior_bar_volume,
              lag(bar_volume, 2) OVER w AS prior2_bar_volume,
              lag(bar_trade_count, 1) OVER w AS prior_bar_trade_count,
              lag(backload_volume_share, 1) OVER w AS prior_backload_volume_share,
              first_value(bar_volume) OVER wr AS opening_bar_volume,
              sum(minute_count) OVER wr AS running_minute_count
            FROM five_minute_participation
            WINDOW w AS (PARTITION BY symbol, session_date ORDER BY bar_idx),
              wr AS (PARTITION BY symbol, session_date ORDER BY bar_idx
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          )
          SELECT symbol, session_date, bar_idx, backload_volume_share,
            backload_trade_share, signed_volume_imbalance, signed_trade_imbalance,
            positive_backload_volume_share, final_minute_return, volume_slope,
            backload_volume_share - prior_backload_volume_share AS backload_transition,
            bar_volume / nullif(prior_bar_volume, 0) AS volume_to_prior,
            bar_trade_count / nullif(prior_bar_trade_count, 0) AS count_to_prior,
            bar_volume / nullif(opening_bar_volume, 0) AS volume_to_open,
            bar_volume / nullif(prior_bar_volume, 0) -
              prior_bar_volume / nullif(prior2_bar_volume, 0) AS volume_reacceleration
          FROM enriched
          WHERE bar_idx IN (2, 5, 11, 17, 23)
            AND minute_count = 5 AND running_minute_count = (bar_idx + 1) * 5
            AND prior_bar_idx = bar_idx - 1 AND prior2_bar_idx = bar_idx - 2
            AND bar_volume > 0 AND prior_bar_volume > 0 AND prior2_bar_volume > 0
            AND bar_trade_count > 0 AND prior_bar_trade_count > 0
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(temporary)],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(temporary)]).fetchone()[0]
    con.close()
    os.replace(temporary, output)
    return {"cache": str(output), "rows": int(rows), "shards": len(files), "reused": "no"}


def attach_liquidity_curve(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    if LIQUIDITY_CONTEXT is None:
        raise RuntimeError("liquidity curve context cache was not bound")
    con = duckdb.connect()
    context = con.execute("SELECT * FROM read_parquet(?)", [str(LIQUIDITY_CONTEXT)]).fetch_df()
    con.close()
    context["session_date"] = pd.to_datetime(context["session_date"])
    keys = ["session_date", "bar_idx"]
    for column in ("positive_backload_volume_share", "volume_reacceleration", "signed_trade_imbalance"):
        context[f"{column}_rank"] = context.groupby(keys, sort=False)[column].rank(pct=True)
    attached = events.merge(context, on=["symbol", "session_date", "bar_idx"], how="inner", validate="one_to_one")
    return attached, {"liquidity_curve_events": len(attached), "method": "complete causal minute participation path"}


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return (frame["backload_volume_share"] > 0.50) & (frame["signed_volume_imbalance"] > 0.25)
    if family == FAMILIES[1]:
        return (frame["backload_transition"] > 0.20) & (frame["signed_volume_imbalance"] > 0.20)
    if family == FAMILIES[2]:
        return (
            (frame["volume_to_prior"] > 1.50)
            & (frame["count_to_prior"] > 1.20)
            & (frame["signed_trade_imbalance"] > 0.20)
        )
    if family == FAMILIES[3]:
        return (
            frame["volume_to_open"].between(0.20, 0.60)
            & frame["volume_to_prior"].between(0.80, 1.20)
            & (frame["signed_volume_imbalance"] > 0.20)
        )
    if family == FAMILIES[4]:
        return (frame["positive_backload_volume_share"] > 0.45) & (frame["final_minute_return"] > 0.0)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["positive_backload_volume_share_rank"] + frame["signed_volume_imbalance"]
    if family == FAMILIES[1]:
        return frame["backload_transition"] + frame["signed_volume_imbalance"]
    if family == FAMILIES[2]:
        return frame["volume_reacceleration_rank"] + frame["signed_trade_imbalance_rank"]
    if family == FAMILIES[3]:
        return frame["signed_volume_imbalance"] - abs(frame["volume_to_prior"] - 1.0)
    if family == FAMILIES[4]:
        return frame["positive_backload_volume_share_rank"] + frame["final_minute_return"]
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    global LIQUIDITY_CONTEXT
    data_root = Path(args.data_root)
    LIQUIDITY_CONTEXT = data_root / "research" / "cache" / "v16709_v16808_liquidity_curve.parquet"
    cache_evidence = materialize_liquidity_context(data_root, LIQUIDITY_CONTEXT)
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16709,
            "PRIOR_COMPARISONS": 339_583,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_liquidity_curve,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16709-v16808-intrabar-liquidity-curve"
    result["liquidity_cache_evidence"] = cache_evidence
    result["liquidity_curve_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16709-v16808 intrabar liquidity curve\n\n"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v16709-v16808-liquidity-curve.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
