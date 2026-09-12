"""Immutable, market-data-only Alpaca SIP five-minute acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time as time_module
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import exchange_calendars  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from us_intraday_lab.data.us_market_acquisition import primary_exchange_symbols

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
SIP_FIVE_MINUTE_NAMESPACE = "alpaca_sip_5min_v1"
_REQUIRED_COLUMNS = ("symbol", "timestamp", "open", "high", "low", "close", "volume")
_OPTIONAL_COLUMNS = ("trade_count", "vwap")
_OUTPUT_COLUMNS = (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS, "asof", "provider", "feed")
_INVALID_SYMBOL_RESPONSE = re.compile(r'invalid symbol:\s*([^"}]+)', re.IGNORECASE)
_XNYS = exchange_calendars.get_calendar("XNYS")


class HistoricalBarsClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


HistoricalClientFactory = Callable[[str, str], HistoricalBarsClient]


def _client_factory(api_key: str, secret_key: str) -> HistoricalBarsClient:
    from alpaca.data.historical import StockHistoricalDataClient

    return cast(
        HistoricalBarsClient,
        StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
    )


class ReadOnlyAlpacaSipFiveMinuteDownloader:
    """Fetch consolidated five-minute bars without importing trading APIs."""

    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: HistoricalClientFactory = _client_factory,
    ) -> ReadOnlyAlpacaSipFiveMinuteDownloader:
        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                "ALPACA_SIP_FIVE_MINUTE_CREDENTIAL_MISSING: set "
                f"{API_KEY_VARIABLE} and {SECRET_KEY_VARIABLE}"
            )
        return cls(client_factory(api_key, secret_key))

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: date,
        end: date,
        asof: date,
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        _validate_symbol_request(symbols)
        if start > end:
            raise ValueError("start must not exceed end")
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=datetime.combine(start, time(), UTC),
            end=datetime.combine(end + timedelta(days=1), time(), UTC),
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.SIP,
            asof=asof.isoformat(),
        )
        response = self._client.get_stock_bars(request)
        return _normalize_five_minute_bars(response.df.reset_index(), asof=asof)


def _validate_symbol_request(symbols: tuple[str, ...]) -> None:
    if not symbols or tuple(sorted(set(symbols))) != symbols:
        raise ValueError("symbols must be non-empty, unique, and sorted")


def load_frozen_candidate_symbols(
    *, assets_path: Path, protocol_path: Path
) -> tuple[str, ...]:
    """Load assets only when they match the candidate universe frozen in protocol."""
    protocol = cast(dict[str, object], json.loads(protocol_path.read_text("utf-8")))
    symbols = primary_exchange_symbols(pd.read_parquet(assets_path))
    symbol_hash = hashlib.sha256("\n".join(symbols).encode()).hexdigest()
    if (
        assets_path.resolve().parent.name != protocol.get("candidate_asset_snapshot")
        or len(symbols) != protocol.get("candidate_symbols")
        or symbol_hash != protocol.get("candidate_symbols_sha256")
    ):
        raise ValueError(
            "SIP five-minute frozen candidate universe mismatch: "
            f"snapshot={assets_path.resolve().parent.name}, "
            f"symbols={len(symbols)}, symbols_sha256={symbol_hash}"
        )
    return symbols


def _normalize_five_minute_bars(frame: pd.DataFrame, *, asof: date) -> pd.DataFrame:
    if frame.empty:
        result = pd.DataFrame(columns=_OUTPUT_COLUMNS)
        result.attrs["provider_source_rows"] = 0
        result.attrs["excluded_out_of_session_rows"] = 0
        return result
    provider_source_rows = len(frame)
    missing = sorted(set(_REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"Alpaca SIP five-minute response missing columns: {missing}")
    columns = [column for column in (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS) if column in frame]
    result = frame.loc[:, columns].copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume", *_OPTIONAL_COLUMNS):
        if column not in result:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["asof"] = asof
    result["provider"] = "alpaca"
    result["feed"] = "sip"
    result = result.loc[_regular_session_mask(result["timestamp"])]
    normalized = (
        result.loc[:, _OUTPUT_COLUMNS]
        .sort_values(["timestamp", "symbol"], kind="stable")
        .reset_index(drop=True)
    )
    normalized.attrs["provider_source_rows"] = provider_source_rows
    normalized.attrs["excluded_out_of_session_rows"] = provider_source_rows - len(normalized)
    return normalized


def _regular_session_mask(timestamps: pd.Series) -> pd.Series:
    """Return whether each timestamp is inside its actual XNYS regular session."""
    parsed = pd.to_datetime(timestamps, utc=True, errors="raise")
    if parsed.empty:
        return pd.Series(False, index=timestamps.index, dtype=bool)
    local_dates = parsed.dt.tz_convert("America/New_York").dt.date
    sessions = _XNYS.sessions_in_range(
        pd.Timestamp(min(local_dates)), pd.Timestamp(max(local_dates))
    )
    opens = {session.date(): _XNYS.session_open(session) for session in sessions}
    closes = {session.date(): _XNYS.session_close(session) for session in sessions}
    market_open = pd.to_datetime(local_dates.map(opens), utc=True, errors="coerce")
    market_close = pd.to_datetime(local_dates.map(closes), utc=True, errors="coerce")
    return market_open.notna() & parsed.ge(market_open) & parsed.lt(market_close)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _month_ranges(start: date, end: date) -> tuple[tuple[date, date], ...]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        period_end = min(end, next_month - timedelta(days=1))
        ranges.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return tuple(ranges)


def _request_identity(
    *,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    asof: date,
    batch_size: int,
) -> dict[str, object]:
    return {
        "provider": "alpaca",
        "feed": "sip",
        "bar_size": "5min",
        "adjustment": "split",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "asof": asof.isoformat(),
        "batch_size": batch_size,
        "symbols": list(symbols),
    }


def _identity_hash(identity: dict[str, object]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _acquisition_contract(
    *, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> dict[str, object]:
    symbol_payload = "\n".join(symbols).encode()
    specs = _partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
    return {
        "schema_version": "1.0.0",
        "source_namespace": SIP_FIVE_MINUTE_NAMESPACE,
        "provider": "alpaca",
        "feed": "sip",
        "bar_size": "5min",
        "adjustment": "split",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "batch_size": batch_size,
        "candidate_symbol_count": len(symbols),
        "candidate_symbols_sha256": hashlib.sha256(symbol_payload).hexdigest(),
        "total_shards": len(specs),
        "read_only_market_data": True,
    }


def _ensure_acquisition_contract(
    *, output_root: Path, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> dict[str, object]:
    expected = _acquisition_contract(
        symbols=symbols, start=start, end=end, batch_size=batch_size
    )
    path = output_root / "acquisition_contract.json"
    content = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    if not path.exists() and any(
        item.name != path.name for item in output_root.iterdir()
    ):
        raise ValueError("SIP five-minute acquisition contract missing for populated namespace")
    try:
        with path.open("x", encoding="utf-8") as target:
            target.write(content)
    except FileExistsError:
        pass
    actual = cast(dict[str, object], json.loads(path.read_text("utf-8")))
    if actual != expected:
        raise ValueError("SIP five-minute acquisition contract mismatch")
    return expected


def _partition_stem(*, period_start: date, batch_index: int, identity_hash: str) -> str:
    return f"{period_start:%Y-%m}-batch-{batch_index:04d}-{identity_hash[:16]}"


def _partition_specs(
    *, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    global_index = 0
    for period_start, period_end in _month_ranges(start, end):
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            identity = _request_identity(
                symbols=batch,
                start=period_start,
                end=period_end,
                asof=period_end,
                batch_size=batch_size,
            )
            request_hash = _identity_hash(identity)
            specs.append(
                {
                    "global_shard_index": global_index,
                    "period_start": period_start,
                    "period_end": period_end,
                    "batch": batch,
                    "batch_index": offset // batch_size,
                    "request": identity,
                    "request_hash": request_hash,
                    "stem": _partition_stem(
                        period_start=period_start,
                        batch_index=offset // batch_size,
                        identity_hash=request_hash,
                    ),
                }
            )
            global_index += 1
    return tuple(specs)


def _quality(
    frame: pd.DataFrame, *, requested: tuple[str, ...], start: date, end: date, asof: date
) -> dict[str, int]:
    if frame.empty:
        return {
            "returned_rows": 0,
            "returned_symbols": 0,
            "duplicate_symbol_timestamps": 0,
            "missing_required_values": 0,
            "outside_regular_session": 0,
        }
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]]
    invalid_ohlc = (
        numeric[["open", "high", "low", "close"]].le(0).any(axis=1)
        | numeric["high"].lt(numeric[["open", "low", "close"]].max(axis=1))
        | numeric["low"].gt(numeric[["open", "high", "close"]].min(axis=1))
        | numeric["volume"].lt(0)
    )
    numeric_columns = ("open", "high", "low", "close", "volume", *_OPTIONAL_COLUMNS)
    nonfinite_numeric = sum(
        int((~np.isfinite(frame[column].dropna().astype(float))).sum())
        for column in numeric_columns
        if column in frame
    )
    invalid_trade_count = int(frame["trade_count"].dropna().lt(0).sum())
    invalid_vwap = int(frame["vwap"].dropna().le(0).sum())
    duplicates = int(frame.duplicated(["symbol", "timestamp"]).sum())
    missing = int(frame.loc[:, _REQUIRED_COLUMNS].isna().any(axis=1).sum())
    off_grid = (
        timestamps.dt.minute.mod(5).ne(0)
        | timestamps.dt.second.ne(0)
        | timestamps.dt.microsecond.ne(0)
    )
    source_bad = (
        set(frame["provider"].astype(str)) != {"alpaca"}
        or set(frame["feed"].astype(str)) != {"sip"}
        or set(frame["asof"].astype(str)) != {asof.isoformat()}
    )
    unexpected = sorted(set(frame["symbol"].astype(str).str.upper()).difference(requested))
    outside = (timestamps.dt.date < start) | (timestamps.dt.date > end)
    outside_regular_session = ~_regular_session_mask(timestamps)
    if (
        unexpected
        or outside.any()
        or outside_regular_session.any()
        or duplicates
        or missing
        or invalid_ohlc.any()
        or nonfinite_numeric
        or invalid_trade_count
        or invalid_vwap
        or off_grid.any()
        or source_bad
    ):
        raise ValueError(
            "SIP five-minute quality failure: "
            f"unexpected_symbols={unexpected}, outside_bounds={int(outside.sum())}, "
            f"outside_regular_session={int(outside_regular_session.sum())}, "
            f"duplicates={duplicates}, missing_required={missing}, "
            f"invalid_ohlc={int(invalid_ohlc.sum())}, off_grid={int(off_grid.sum())}, "
            f"nonfinite_numeric={nonfinite_numeric}, "
            f"invalid_trade_count={invalid_trade_count}, invalid_vwap={invalid_vwap}, "
            f"source_bad={source_bad}"
        )
    return {
        "returned_rows": len(frame),
        "returned_symbols": frame["symbol"].nunique(),
        "duplicate_symbol_timestamps": duplicates,
        "missing_required_values": missing,
        "outside_regular_session": int(outside_regular_session.sum()),
    }


def _validate_partition(
    *, parquet: Path, record: dict[str, object], spec: dict[str, object]
) -> int:
    """Validate one immutable partition deeply enough for both resume and audit."""
    stem = str(spec["stem"])
    request = cast(dict[str, object], spec["request"])
    request_hash = str(spec["request_hash"])
    if (
        record.get("request") != request
        or record.get("request_identity_sha256") != request_hash
        or _identity_hash(cast(dict[str, object], record.get("request", {})))
        != request_hash
    ):
        raise ValueError(f"SIP five-minute request identity mismatch: {stem}")
    if (
        record.get("source_namespace") != SIP_FIVE_MINUTE_NAMESPACE
        or record.get("provider") != "alpaca"
        or record.get("feed") != "sip"
        or record.get("bar_size") != "5min"
        or record.get("adjustment") != "split"
        or record.get("content_sha256") != _sha256_file(parquet)
        or record.get("global_shard_index") != spec["global_shard_index"]
    ):
        raise ValueError(f"SIP five-minute provenance failure: {stem}")

    rows = int(pq.ParquetFile(parquet).metadata.num_rows)
    if rows != int(record.get("row_count", -1)):
        raise ValueError(f"SIP five-minute row-count failure: {stem}")
    provider_rows = int(record.get("provider_source_rows", -1))
    excluded_rows = int(record.get("excluded_out_of_session_rows", -1))
    if provider_rows < rows or excluded_rows < 0 or provider_rows - excluded_rows != rows:
        raise ValueError(f"SIP five-minute source-row accounting failure: {stem}")

    frame = pq.read_table(parquet).to_pandas()
    observed_quality = _quality(
        frame,
        requested=tuple(cast(list[str], request["symbols"])),
        start=date.fromisoformat(str(request["start"])),
        end=date.fromisoformat(str(request["end"])),
        asof=date.fromisoformat(str(request["asof"])),
    )
    if record.get("quality") != observed_quality:
        raise ValueError(f"SIP five-minute quality-manifest mismatch: {stem}")
    return rows


def acquire_sip_five_minute_shards(
    *,
    root: Path,
    downloader: ReadOnlyAlpacaSipFiveMinuteDownloader,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    batch_size: int = 100,
    shard_start: int = 0,
    shard_stop: int | None = None,
    sleep: Callable[[float], None] = time_module.sleep,
) -> list[dict[str, object]]:
    """Write a deterministic slice of the month/batch request grid."""
    _validate_symbol_request(symbols)
    if start > end:
        raise ValueError("five-minute acquisition start must not exceed end")
    if batch_size < 1 or shard_start < 0 or (shard_stop is not None and shard_stop < shard_start):
        raise ValueError("invalid batch size or shard bounds")
    output_root = root.resolve() / "data" / "staging" / SIP_FIVE_MINUTE_NAMESPACE
    output_root.mkdir(parents=True, exist_ok=True)
    _ensure_acquisition_contract(
        output_root=output_root,
        symbols=symbols,
        start=start,
        end=end,
        batch_size=batch_size,
    )
    specs = _partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
    selected = specs[shard_start:shard_stop]
    records: list[dict[str, object]] = []
    for spec in selected:
        stem = str(spec["stem"])
        parquet = output_root / f"{stem}.parquet"
        manifest = output_root / f"{stem}.json"
        temporary_parquet = parquet.with_suffix(".tmp.parquet")
        temporary_manifest = manifest.with_suffix(".tmp")
        if temporary_parquet.exists() or temporary_manifest.exists():
            raise ValueError(f"temporary SIP five-minute partition requires audit: {stem}")
        request = cast(dict[str, object], spec["request"])
        request_hash = str(spec["request_hash"])
        if parquet.is_file() and manifest.is_file():
            record = cast(dict[str, object], json.loads(manifest.read_text("utf-8")))
            _validate_partition(parquet=parquet, record=record, spec=spec)
            records.append(record)
            continue
        if parquet.exists() or manifest.exists():
            raise ValueError(f"partial SIP five-minute shard requires audit: {stem}")

        batch = cast(tuple[str, ...], spec["batch"])
        remaining = list(batch)
        rejected: list[str] = []
        attempt = 0
        while remaining:
            try:
                frame = downloader.fetch(
                    symbols=tuple(remaining),
                    start=cast(date, spec["period_start"]),
                    end=cast(date, spec["period_end"]),
                    asof=cast(date, spec["period_end"]),
                )
                if frame.empty:
                    raise RuntimeError(
                        "ALPACA_SIP_FIVE_MINUTE_EMPTY_RESPONSE: "
                        f"request_identity={request_hash}"
                    )
                break
            except Exception as error:
                invalid = _INVALID_SYMBOL_RESPONSE.search(str(error))
                if invalid and invalid.group(1).strip().upper() in remaining:
                    symbol = invalid.group(1).strip().upper()
                    remaining.remove(symbol)
                    rejected.append(symbol)
                    continue
                if attempt >= 4:
                    raise
                sleep(min(30.0, 2.0**attempt))
                attempt += 1
        else:
            frame = pd.DataFrame(columns=_OUTPUT_COLUMNS)

        quality = _quality(
            frame,
            requested=tuple(remaining),
            start=cast(date, spec["period_start"]),
            end=cast(date, spec["period_end"]),
            asof=cast(date, spec["period_end"]),
        )
        provider_source_rows = int(frame.attrs.get("provider_source_rows", len(frame)))
        excluded_out_of_session_rows = int(
            frame.attrs.get("excluded_out_of_session_rows", 0)
        )
        frame.to_parquet(temporary_parquet, index=False, compression="zstd")
        temporary_parquet.replace(parquet)
        record = {
            "schema_version": "1.0.0",
            "source_namespace": SIP_FIVE_MINUTE_NAMESPACE,
            "provider": "alpaca",
            "feed": "sip",
            "bar_size": "5min",
            "adjustment": "split",
            "start": cast(date, spec["period_start"]).isoformat(),
            "end": cast(date, spec["period_end"]).isoformat(),
            "asof": cast(date, spec["period_end"]).isoformat(),
            "symbols": list(batch),
            "provider_rejected_symbols": sorted(rejected),
            "row_count": len(frame),
            "provider_source_rows": provider_source_rows,
            "excluded_out_of_session_rows": excluded_out_of_session_rows,
            "quality": quality,
            "read_only_market_data": True,
            "request": request,
            "request_identity_sha256": request_hash,
            "content_sha256": _sha256_file(parquet),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "global_shard_index": int(spec["global_shard_index"]),
            "manifest_path": str(manifest.resolve()),
        }
        temporary_manifest.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_manifest.replace(manifest)
        records.append(record)
    return records


def validate_sip_five_minute_source(
    *, root: Path, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> dict[str, int]:
    """Reconstruct and verify the complete immutable request grid."""
    _validate_symbol_request(symbols)
    source = root.resolve() / "data" / "staging" / SIP_FIVE_MINUTE_NAMESPACE
    parquet_by_stem = {path.stem: path for path in source.glob("*.parquet")}
    manifest_by_stem = {
        path.stem: path
        for path in source.glob("*.json")
        if path.name != "acquisition_contract.json"
    }
    partials = tuple(source.glob("*.tmp")) + tuple(source.glob("*.tmp.parquet"))
    if parquet_by_stem.keys() != manifest_by_stem.keys() or partials:
        raise ValueError("SIP five-minute partition pairing failure")
    _ensure_acquisition_contract(
        output_root=source,
        symbols=symbols,
        start=start,
        end=end,
        batch_size=batch_size,
    )
    specs = _partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
    expected = {str(spec["stem"]): spec for spec in specs}
    if parquet_by_stem.keys() != expected.keys():
        raise ValueError("SIP five-minute expected acquisition grid mismatch")

    total_rows = 0
    for stem, spec in sorted(expected.items()):
        parquet = parquet_by_stem[stem]
        record = cast(
            dict[str, object], json.loads(manifest_by_stem[stem].read_text("utf-8"))
        )
        rows = _validate_partition(parquet=parquet, record=record, spec=spec)
        total_rows += rows
    return {"partitions": len(expected), "rows": total_rows}
