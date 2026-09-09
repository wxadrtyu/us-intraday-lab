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

from us_intraday_lab.data.alpaca_sip_daily import validate_sip_daily_source

_XNYS = exchange_calendars.get_calendar("XNYS")
_DAILY_SOURCES = {
    "alpaca_iex_1day_v2": ("alpaca-iex-1day-v2-shards", "monthly_universe", "iex", ""),
    "alpaca_sip_1day_v1": (
        "alpaca-sip-1day-v1-shards",
        "monthly_universe_sip_v1",
        "sip",
        "sip-",
    ),
    "alpaca_sip_1day_v2": (
        "alpaca-sip-1day-v2-shards",
        "monthly_universe_sip_v2",
        "sip",
        "sip-v2-",
    ),
}


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
    source: str = "alpaca_iex_1day_v2",
    candidate_symbols: tuple[str, ...] | None = None,
    verify_source: bool = True,
    source_start: date | None = None,
    source_end: date | None = None,
    source_batch_size: int | None = None,
) -> dict[str, object]:
    """Publish all symbol-month decisions; missing cutoff data fails closed."""
    if source not in _DAILY_SOURCES:
        raise ValueError(f"unsupported daily source: {source}")
    source_label, output_namespace, source_feed, dataset_infix = _DAILY_SOURCES[source]
    if source == "alpaca_sip_1day_v2" and verify_source:
        if candidate_symbols is None:
            raise ValueError("candidate_symbols are required for verified SIP v2")
        validate_sip_daily_source(
            root=root,
            symbols=candidate_symbols,
            start=source_start,
            end=source_end,
            batch_size=source_batch_size,
        )
    daily_root = root.resolve() / "data" / "staging" / source
    shards = sorted(daily_root.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError("no daily shards are available")
    cutoffs = monthly_cutoffs(start_month, end_month)
    cutoffs["window_start"] = [
        _XNYS.sessions_window(pd.Timestamp(cutoff), -lookback_sessions)[0].date()
        for cutoff in cutoffs["information_cutoff"]
    ]
    minimum_sessions = int(lookback_sessions * minimum_coverage_ratio + 0.999999)
    connection = duckdb.connect()
    connection.register("cutoffs", cutoffs)
    if candidate_symbols is not None:
        normalized = tuple(sorted(set(candidate_symbols)))
        if not normalized or normalized != candidate_symbols:
            raise ValueError("candidate_symbols must be non-empty, unique, and sorted")
        connection.register("candidate_symbols", pd.DataFrame({"symbol": normalized}))
        symbols_sql = "SELECT symbol FROM candidate_symbols"
    else:
        symbols_sql = "SELECT DISTINCT symbol FROM daily"
    parquet_glob = (daily_root / "*.parquet").as_posix()
    decisions = connection.execute(
        f"""
        WITH daily AS (
          SELECT upper(symbol) AS symbol,
                 CAST(timestamp AS DATE) AS session_date,
                 max(close) AS close,
                 max(volume) AS volume
          FROM read_parquet(?, union_by_name = true)
          WHERE close IS NOT NULL AND volume IS NOT NULL
          GROUP BY 1, 2
        ),
        symbols AS ({symbols_sql}),
        grid AS (
          SELECT symbols.symbol, cutoffs.month, cutoffs.information_cutoff
                 , cutoffs.window_start
          FROM symbols CROSS JOIN cutoffs
        ),
        stats AS (
          SELECT grid.symbol, grid.month, grid.information_cutoff,
                 count(daily.session_date) AS observed_sessions,
                 median(daily.close * daily.volume) AS median_dollar_volume
          FROM grid
          LEFT JOIN daily
            ON daily.symbol = grid.symbol
           AND daily.session_date BETWEEN grid.window_start AND grid.information_cutoff
          GROUP BY 1, 2, 3
        ),
        cutoff_bar AS (
          SELECT grid.symbol, grid.month, max(daily.close) AS close
          FROM grid
          LEFT JOIN daily
            ON daily.symbol = grid.symbol
           AND daily.session_date = grid.information_cutoff
          GROUP BY 1, 2
        )
        SELECT grid.symbol, grid.month, grid.information_cutoff,
               cutoff_bar.close AS cutoff_close,
               coalesce(stats.observed_sessions, 0) AS observed_sessions,
               stats.median_dollar_volume,
               CASE
                 WHEN cutoff_bar.close IS NULL THEN 'missing_cutoff_bar'
                 WHEN stats.observed_sessions < ? THEN 'insufficient_coverage'
                 WHEN cutoff_bar.close < ? THEN 'price_below_floor'
                 WHEN stats.median_dollar_volume < ? THEN 'liquidity_below_floor'
                 ELSE 'eligible'
               END AS decision_reason,
               cutoff_bar.close IS NOT NULL
                 AND stats.observed_sessions >= ?
                 AND cutoff_bar.close >= ?
                 AND stats.median_dollar_volume >= ? AS eligible
        FROM grid
        LEFT JOIN stats USING (symbol, month, information_cutoff)
        LEFT JOIN cutoff_bar USING (symbol, month)
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
    output_root = root.resolve() / "data" / "catalog" / output_namespace
    output_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".universe-", dir=output_root))
    data_path = temporary_root / "decisions.parquet"
    decisions.to_parquet(data_path, index=False, compression="zstd")
    content_hash = _sha256_file(data_path)
    dataset_id = f"us-market-monthly-universe-{dataset_infix}{content_hash[:24]}"
    eligible = decisions.loc[decisions["eligible"]]
    counts = {
        str(month): int(count)
        for month, count in eligible.groupby("month", observed=True).size().items()
    }
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "source": source_label,
        "source_dataset": source,
        "source_feed": source_feed,
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
        "uses_current_asset_status": False,
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
