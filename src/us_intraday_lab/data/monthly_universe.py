"""Point-in-time monthly universe construction from coarse daily bars."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import cast

import duckdb
import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd

_XNYS = exchange_calendars.get_calendar("XNYS")


def monthly_cutoffs(start_month: date, end_month: date) -> pd.DataFrame:
    if start_month.day != 1 or end_month.day != 1 or start_month > end_month:
        raise ValueError("month bounds must be ordered first-of-month dates")
    months: list[date] = []
    cursor = start_month
    while cursor <= end_month:
        months.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    rows: list[dict[str, object]] = []
    for month in months:
        prior = _XNYS.date_to_session(pd.Timestamp(month), direction="previous")
        if prior.date() == month:
            prior = _XNYS.previous_session(prior)
        rows.append({"month": month, "information_cutoff": prior.date()})
    return pd.DataFrame(rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_monthly_universe(
    *,
    root: Path,
    start_month: date,
    end_month: date,
    lookback_sessions: int = 60,
    minimum_coverage_ratio: float = 0.95,
    minimum_close: float = 5.0,
    minimum_median_dollar_volume: float = 10_000_000.0,
) -> dict[str, object]:
    """Publish all symbol-month decisions; missing cutoff data fails closed."""
    daily_root = root.resolve() / "data" / "staging" / "alpaca_iex_1day"
    shards = sorted(daily_root.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError("no daily shards are available")
    cutoffs = monthly_cutoffs(start_month, end_month)
    minimum_sessions = int(lookback_sessions * minimum_coverage_ratio + 0.999999)
    connection = duckdb.connect()
    connection.register("cutoffs", cutoffs)
    parquet_glob = (daily_root / "*.parquet").as_posix()
    window_preceding = lookback_sessions - 1
    decisions = connection.execute(
        f"""
        WITH daily AS (
          SELECT upper(symbol) AS symbol,
                 CAST(timestamp AS DATE) AS session_date,
                 max(close) AS close,
                 max(volume) AS volume
          FROM read_parquet(?)
          WHERE close IS NOT NULL AND volume IS NOT NULL
          GROUP BY 1, 2
        ),
        stats AS (
          SELECT symbol, session_date, close,
                 count(*) OVER trailing_window AS observed_sessions,
                 median(close * volume) OVER trailing_window AS median_dollar_volume
          FROM daily
          WINDOW trailing_window AS (
            PARTITION BY symbol ORDER BY session_date
            ROWS BETWEEN {window_preceding:d} PRECEDING AND CURRENT ROW
          )
        ),
        symbols AS (SELECT DISTINCT symbol FROM daily),
        grid AS (
          SELECT symbols.symbol, cutoffs.month, cutoffs.information_cutoff
          FROM symbols CROSS JOIN cutoffs
        )
        SELECT grid.symbol, grid.month, grid.information_cutoff,
               stats.close AS cutoff_close,
               coalesce(stats.observed_sessions, 0) AS observed_sessions,
               stats.median_dollar_volume,
               CASE
                 WHEN stats.symbol IS NULL THEN 'missing_cutoff_bar'
                 WHEN stats.observed_sessions < ? THEN 'insufficient_coverage'
                 WHEN stats.close < ? THEN 'price_below_floor'
                 WHEN stats.median_dollar_volume < ? THEN 'liquidity_below_floor'
                 ELSE 'eligible'
               END AS decision_reason,
               stats.symbol IS NOT NULL
                 AND stats.observed_sessions >= ?
                 AND stats.close >= ?
                 AND stats.median_dollar_volume >= ? AS eligible
        FROM grid
        LEFT JOIN stats
          ON stats.symbol = grid.symbol
         AND stats.session_date = grid.information_cutoff
        ORDER BY grid.month, grid.symbol
        """,
        [
            parquet_glob,
            minimum_sessions,
            minimum_close,
            minimum_median_dollar_volume,
            minimum_sessions,
            minimum_close,
            minimum_median_dollar_volume,
        ],
    ).fetch_df()
    connection.close()
    output_root = root.resolve() / "data" / "catalog" / "monthly_universe"
    output_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".universe-", dir=output_root))
    data_path = temporary_root / "decisions.parquet"
    decisions.to_parquet(data_path, index=False, compression="zstd")
    content_hash = _sha256_file(data_path)
    dataset_id = f"us-market-monthly-universe-{content_hash[:24]}"
    eligible = decisions.loc[decisions["eligible"]]
    counts = {
        str(month): int(count)
        for month, count in eligible.groupby("month", observed=True).size().items()
    }
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "source": "alpaca-iex-1day-shards",
        "start_month": start_month.isoformat(),
        "end_month": end_month.isoformat(),
        "lookback_sessions": lookback_sessions,
        "minimum_sessions": minimum_sessions,
        "minimum_close": minimum_close,
        "minimum_median_dollar_volume": minimum_median_dollar_volume,
        "row_count": len(decisions),
        "eligible_symbol_months": len(eligible),
        "eligible_counts_by_month": counts,
        "content_sha256": content_hash,
        "uses_future_data": False,
        "missing_is_cash": False,
    }
    (temporary_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    final = output_root / dataset_id
    if final.exists():
        retained = cast(dict[str, object], json.loads((final / "manifest.json").read_text("utf-8")))
        if retained != manifest:
            raise ValueError("immutable monthly universe collision")
        for child in temporary_root.iterdir():
            child.unlink()
        temporary_root.rmdir()
        return retained
    temporary_root.rename(final)
    return manifest
