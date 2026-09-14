"""Fail-closed coverage audit for full-market SIP five-minute bars."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import exchange_calendars as xcals
import pandas as pd

DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
COVERAGE_FLOOR = 0.95


def _required_bar_numbers() -> tuple[int, ...]:
    required: set[int] = set()
    for decision in DECISION_BARS:
        required.add(decision)
        for entry_delay in (1, 2):
            entry = decision + entry_delay
            required.add(entry)
            required.update(entry + holding for holding in HOLDING_BARS)
    return tuple(sorted(required))


def _session_opens(expected_sessions: tuple[date, ...]) -> dict[date, pd.Timestamp]:
    if not expected_sessions:
        return {}
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(
        pd.Timestamp(min(expected_sessions)), pd.Timestamp(max(expected_sessions))
    )
    expected = set(expected_sessions)
    return {
        session.date(): calendar.session_open(session).tz_convert("UTC")
        for session in sessions
        if session.date() in expected
    }


def _bar_sources_by_month(
    bars_glob: str, months: tuple[date, ...]
) -> dict[date, str]:
    pattern = Path(bars_glob)
    matched = tuple(pattern.parent.glob(pattern.name))
    if len(months) == 1 and matched and not matched[0].name[:7].replace("-", "").isdigit():
        return {months[0]: bars_glob}
    sources: dict[date, str] = {}
    for month in months:
        candidates = tuple(pattern.parent.glob(f"{month:%Y-%m}-*.parquet"))
        if not candidates:
            raise RuntimeError(f"SIP_FIVE_MINUTE_MONTH_MISSING:{month:%Y-%m}")
        sources[month] = (
            candidates[0].as_posix()
            if len(candidates) == 1
            else (pattern.parent / f"{month:%Y-%m}-*.parquet").as_posix()
        )
    return sources


def audit_sip_five_minute(
    *,
    bars: pd.DataFrame,
    monthly_decisions: pd.DataFrame,
    assets: pd.DataFrame,
    expected_sessions: tuple[date, ...],
    historical_master_validated: bool,
) -> dict[str, Any]:
    """Audit required decision/entry/exit clocks without filling missing bars."""
    reasons: list[str] = []
    required_bar_numbers = _required_bar_numbers()
    required_columns = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    if not required_columns.issubset(bars.columns):
        missing = sorted(required_columns.difference(bars.columns))
        return {
            "schema_version": "1.0.0",
            "strategy_metrics_permitted": False,
            "rejection_reasons": ["REQUIRED_BAR_COLUMNS_MISSING"],
            "missing_columns": missing,
            "required_clock_coverage_ratio": 0.0,
        }

    normalized = bars.loc[:, sorted(required_columns)].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    duplicate_rows = int(normalized.duplicated(["symbol", "timestamp"]).sum())
    if duplicate_rows:
        reasons.append("DUPLICATE_SYMBOL_TIMESTAMP")

    invalid_ohlc = (
        (normalized["high"] < normalized[["open", "close", "low"]].max(axis=1))
        | (normalized["low"] > normalized[["open", "close", "high"]].min(axis=1))
        | (normalized[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (normalized["volume"] < 0)
    )
    invalid_ohlc_rows = int(invalid_ohlc.sum())
    if invalid_ohlc_rows:
        reasons.append("INVALID_OHLCV")

    if not historical_master_validated:
        reasons.append("INDEPENDENT_HISTORICAL_MASTER_MISSING")

    if not expected_sessions:
        reasons.append("EXPECTED_XNYS_SESSION_SET_EMPTY")
    opens = _session_opens(expected_sessions)
    missing_calendar_sessions = sorted(set(expected_sessions).difference(opens))
    if missing_calendar_sessions:
        reasons.append("EXPECTED_XNYS_SESSION_NOT_IN_CALENDAR")

    if not {"symbol", "session_date", "eligible"}.issubset(monthly_decisions.columns):
        reasons.append("ELIGIBILITY_DECISION_COLUMNS_MISSING")
        eligible = pd.DataFrame(columns=["symbol", "session_date"])
    else:
        eligible = monthly_decisions.loc[monthly_decisions["eligible"].astype(bool), ["symbol", "session_date"]].copy()
        eligible["session_date"] = pd.to_datetime(eligible["session_date"]).dt.date
        eligible = eligible.loc[eligible["session_date"].isin(expected_sessions)].drop_duplicates()

    asset_symbols = set(assets.get("symbol", pd.Series(dtype=str)).astype(str))
    unknown_symbols = sorted(set(eligible["symbol"].astype(str)).difference(asset_symbols))
    if unknown_symbols:
        reasons.append("ELIGIBLE_SYMBOL_NOT_IN_ASSET_SNAPSHOT")

    expected_keys: set[tuple[str, pd.Timestamp]] = set()
    for row in eligible.itertuples(index=False):
        session = row.session_date
        session_open = opens.get(session)
        if session_open is None:
            continue
        for bar_number in required_bar_numbers:
            expected_keys.add(
                (str(row.symbol), session_open + pd.Timedelta(minutes=5 * bar_number))
            )
    observed_keys = set(
        zip(normalized["symbol"].astype(str), normalized["timestamp"], strict=False)
    )
    observed_required = len(expected_keys.intersection(observed_keys))
    expected_required = len(expected_keys)
    coverage = observed_required / expected_required if expected_required else 0.0
    if expected_required == 0:
        reasons.append("EXPECTED_REQUIRED_CLOCK_SET_EMPTY")
    elif coverage < COVERAGE_FLOOR:
        reasons.append("REQUIRED_CLOCK_COVERAGE_BELOW_95_PERCENT")

    minute = normalized["timestamp"].dt.minute
    off_grid_rows = int((minute.mod(5) != 0).sum())
    if off_grid_rows:
        reasons.append("OFF_FIVE_MINUTE_GRID")

    return {
        "schema_version": "1.0.0",
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
        "expected_sessions": [session.isoformat() for session in expected_sessions],
        "eligible_symbol_sessions": len(eligible),
        "required_clock_count": expected_required,
        "observed_required_clock_count": observed_required,
        "required_clock_coverage_ratio": coverage,
        "duplicate_rows": duplicate_rows,
        "off_grid_rows": off_grid_rows,
        "invalid_ohlcv_rows": invalid_ohlc_rows,
        "unknown_eligible_symbols": unknown_symbols,
        "historical_master_validated": historical_master_validated,
        "missing_data_policy": "preserve_missing_no_fill_no_cash_substitution",
    }


def audit_sip_five_minute_files(
    *,
    bars_glob: str,
    decisions_path: Path,
    assets_path: Path,
    expected_sessions: tuple[date, ...],
    historical_master_validated: bool,
    source_validation: dict[str, int | bool],
) -> dict[str, Any]:
    """Stream the production Parquet set and audit exact required-clock coverage."""
    required_invariants = (
        source_validation.get("request_grid_valid") is True
        and source_validation.get("partition_pairing_valid") is True
        and source_validation.get("content_hashes_valid") is True
        and int(source_validation.get("partial_partitions", -1)) == 0
    )
    if not required_invariants:
        raise RuntimeError("SOURCE_VALIDATION_INVARIANTS_UNPROVEN")
    opens = _session_opens(expected_sessions)
    sessions = pd.DataFrame(
        {
            "session_date": tuple(opens),
            "month": tuple(date(value.year, value.month, 1) for value in opens),
            "session_open": tuple(opens.values()),
        }
    )
    required = pd.DataFrame({"bar_number": _required_bar_numbers()})
    expected_months = tuple(sorted(set(sessions["month"])))
    bar_sources = _bar_sources_by_month(bars_glob, expected_months)
    connection = duckdb.connect()
    try:
        connection.execute("SET preserve_insertion_order = false")
        connection.register("audit_sessions", sessions)
        connection.register("required_bars", required)
        expected_by_clock = connection.execute(
            """
            WITH eligible AS (
                SELECT DISTINCT upper(symbol) AS symbol, CAST(month AS DATE) AS month
                FROM read_parquet(?)
                WHERE eligible
            )
            SELECT r.bar_number, count(*)::BIGINT AS expected
            FROM eligible AS e
            JOIN audit_sessions AS s USING (month)
            CROSS JOIN required_bars AS r
            GROUP BY r.bar_number
            ORDER BY r.bar_number
            """,
            [decisions_path.as_posix()],
        ).fetch_df()
        observed_parts: list[pd.DataFrame] = []
        finding_parts: list[tuple[int, int, int, int]] = []
        for month, source in bar_sources.items():
            month_sessions = sessions.loc[sessions["month"] == month]
            month_clocks = month_sessions.merge(required, how="cross")
            month_clocks["timestamp"] = month_clocks["session_open"] + pd.to_timedelta(
                month_clocks["bar_number"] * 5, unit="minutes"
            )
            connection.register(
                "month_clocks", month_clocks.loc[:, ["month", "bar_number", "timestamp"]]
            )
            observed_parts.append(
                connection.execute(
                    """
                    WITH eligible AS (
                        SELECT DISTINCT upper(symbol) AS symbol, CAST(month AS DATE) AS month
                        FROM read_parquet(?)
                        WHERE eligible AND CAST(month AS DATE) = ?
                    )
                    SELECT c.bar_number, count(*)::BIGINT AS observed
                    FROM read_parquet(?, union_by_name = true) AS b
                    JOIN month_clocks AS c ON b.timestamp = c.timestamp
                    JOIN eligible AS e
                      ON upper(b.symbol) = e.symbol AND c.month = e.month
                    GROUP BY c.bar_number
                    ORDER BY c.bar_number
                    """,
                    [decisions_path.as_posix(), month, source],
                ).fetch_df()
            )
            finding_parts.append(
                tuple(
                    int(value)
                    for value in connection.execute(
                        """
                        SELECT
                            count(*)::BIGINT AS rows,
                            count_if(provider <> 'alpaca' OR feed <> 'sip')::BIGINT
                                AS wrong_source,
                            count_if(
                                high < greatest(open, close, low)
                                OR low > least(open, close, high)
                                OR least(open, high, low, close) <= 0
                                OR volume < 0
                            )::BIGINT AS invalid_ohlcv,
                            count_if(
                                date_part('minute', timestamp)::INTEGER % 5 <> 0
                                OR date_part('second', timestamp) <> 0
                            )::BIGINT AS off_grid
                        FROM read_parquet(?, union_by_name = true)
                        """,
                        [source],
                    ).fetchone()
                )
            )
        unknown_eligible = connection.execute(
            """
            SELECT DISTINCT upper(d.symbol) AS symbol
            FROM read_parquet(?) AS d
            LEFT JOIN (
                SELECT DISTINCT upper(symbol) AS symbol FROM read_parquet(?)
            ) AS a ON upper(d.symbol) = a.symbol
            WHERE d.eligible AND a.symbol IS NULL
            ORDER BY symbol
            """,
            [decisions_path.as_posix(), assets_path.as_posix()],
        ).fetchall()
    finally:
        connection.close()

    observed_by_clock = (
        pd.concat(observed_parts, ignore_index=True)
        .groupby("bar_number", as_index=False, observed=True)["observed"]
        .sum()
    )
    coverage = expected_by_clock.merge(
        observed_by_clock, on="bar_number", how="left"
    ).fillna({"observed": 0})
    expected_count = int(coverage["expected"].sum())
    observed_count = int(coverage["observed"].sum())
    coverage_ratio = observed_count / expected_count if expected_count else 0.0
    rows, wrong_source, invalid_ohlcv, off_grid = (
        sum(part[index] for part in finding_parts) for index in range(4)
    )
    unknown_symbols = [str(row[0]) for row in unknown_eligible]
    reasons: list[str] = []
    if not historical_master_validated:
        reasons.append("INDEPENDENT_HISTORICAL_MASTER_MISSING")
    if len(opens) != len(expected_sessions):
        reasons.append("EXPECTED_XNYS_SESSION_NOT_IN_CALENDAR")
    if expected_count == 0:
        reasons.append("EXPECTED_REQUIRED_CLOCK_SET_EMPTY")
    elif coverage_ratio < COVERAGE_FLOOR:
        reasons.append("REQUIRED_CLOCK_COVERAGE_BELOW_95_PERCENT")
    if wrong_source:
        reasons.append("NON_SIP_SOURCE_PRESENT")
    if invalid_ohlcv:
        reasons.append("INVALID_OHLCV")
    if off_grid:
        reasons.append("OFF_FIVE_MINUTE_GRID")
    if unknown_symbols:
        reasons.append("ELIGIBLE_SYMBOL_NOT_IN_ASSET_SNAPSHOT")
    if rows > int(source_validation.get("rows", -1)):
        reasons.append("SOURCE_VALIDATION_ROW_COUNT_MISMATCH")

    return {
        "schema_version": "1.0.0",
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
        "source_validation": source_validation,
        "rows": rows,
        "required_clock_count": expected_count,
        "observed_required_clock_count": observed_count,
        "required_clock_coverage_ratio": coverage_ratio,
        "coverage_by_bar_number": coverage.to_dict(orient="records"),
        "duplicate_rows": 0,
        "duplicate_evidence": "validated disjoint request grid and per-partition keys",
        "wrong_source_rows": wrong_source,
        "invalid_ohlcv_rows": invalid_ohlcv,
        "off_grid_rows": off_grid,
        "unknown_eligible_symbols": unknown_symbols,
        "historical_master_validated": historical_master_validated,
        "rows_spliced": 0,
        "missing_data_policy": "preserve_missing_no_fill_no_cash_substitution",
    }
