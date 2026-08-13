"""Read-only Alpaca IEX acquisition and immutable minute-bar publication.

This module deliberately imports only Alpaca's historical market-data client.
It has no broker, order, account, position, submit, or cancel capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

import exchange_calendars  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
from exchange_calendars.errors import NotSessionError  # type: ignore[import-untyped]

from us_intraday_lab.data.calendar import expected_minute_index

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
BLIND_CUTOFF = date(2026, 4, 1)
HISTORY_START = date(2018, 10, 1)
CORE_SYMBOLS = ("SPY", "QQQ", "IWM", "TQQQ", "SOXL")
SECTOR_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
DEFAULT_SYMBOLS = CORE_SYMBOLS + SECTOR_ETFS
OPTIONAL_BAR_COLUMNS = ("trade_count", "vwap")
_REQUIRED_SOURCE_COLUMNS = ("symbol", "timestamp", "open", "high", "low", "close", "volume")
_NEW_YORK = ZoneInfo("America/New_York")
_XNYS = exchange_calendars.get_calendar("XNYS")


class HistoricalBarsClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


HistoricalClientFactory = Callable[[str, str], HistoricalBarsClient]
Sleep = Callable[[float], None]


def _client_factory(api_key: str, secret_key: str) -> HistoricalBarsClient:
    from alpaca.data.historical import StockHistoricalDataClient

    return cast(
        HistoricalBarsClient,
        StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
    )


@dataclass(frozen=True, slots=True)
class AcquisitionWindow:
    label: str
    start: date
    end: date
    blind_test_candidate: bool

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("acquisition window start must not exceed end")
        if self.blind_test_candidate != (self.start >= BLIND_CUTOFF):
            raise ValueError("blind-test windows must be isolated at the 2026-04-01 cutoff")


def default_windows(available_through: date) -> tuple[AcquisitionWindow, ...]:
    """Return priority-ordered, non-overlapping coverage from late 2018 onward."""
    if available_through < BLIND_CUTOFF:
        raise ValueError("available_through precedes the blind-test cutoff")
    return (
        AcquisitionWindow("blind-current-2026", BLIND_CUTOFF, available_through, True),
        AcquisitionWindow("current-regime-2026q1", date(2026, 1, 1), date(2026, 3, 31), False),
        AcquisitionWindow("mixed-regime-2025", date(2025, 1, 1), date(2025, 12, 31), False),
        AcquisitionWindow("mixed-regime-2024", date(2024, 1, 1), date(2024, 12, 31), False),
        AcquisitionWindow("mixed-regime-2023", date(2023, 1, 1), date(2023, 12, 31), False),
        AcquisitionWindow("bear-market-2022", date(2022, 1, 1), date(2022, 12, 31), False),
        AcquisitionWindow("strong-trend-2021", date(2021, 1, 1), date(2021, 12, 31), False),
        AcquisitionWindow("covid-crash-rebound-2020", date(2020, 1, 1), date(2020, 12, 31), False),
        AcquisitionWindow("late-2018-and-2019-transition", HISTORY_START, date(2019, 12, 31), False),
    )


def latest_completed_session(today: date | None = None) -> date:
    """Find the latest fully completed XNYS session without querying a broker clock."""
    local_now = datetime.now(_NEW_YORK)
    reference = local_now.date() if today is None else today
    sessions = _XNYS.sessions_in_range(pd.Timestamp(reference - timedelta(days=10)), pd.Timestamp(reference))
    if len(sessions) == 0:
        raise RuntimeError("XNYS calendar returned no recent session")
    latest = cast(date, sessions[-1].date())
    if today is None and latest == local_now.date():
        close = _XNYS.session_close(pd.Timestamp(latest)).to_pydatetime().astimezone(_NEW_YORK)
        if local_now < close:
            latest = cast(date, sessions[-2].date())
    return latest


def _month_chunks(window: AcquisitionWindow) -> tuple[tuple[date, date], ...]:
    chunks: list[tuple[date, date]] = []
    cursor = window.start
    while cursor <= window.end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        chunk_end = min(window.end, next_month - timedelta(days=1))
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return tuple(chunks)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_hash(root: Path, files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def _code_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


class ReadOnlyAlpacaIexDownloader:
    """Alpaca IEX minute-bar downloader with bounded retries and no trading client."""

    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: HistoricalClientFactory = _client_factory,
    ) -> ReadOnlyAlpacaIexDownloader:
        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                f"ALPACA_IEX_CREDENTIAL_MISSING: set {API_KEY_VARIABLE} and {SECRET_KEY_VARIABLE}"
            )
        return cls(client_factory(api_key, secret_key))

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: date,
        end: date,
        retries: int = 4,
        sleep: Sleep = time.sleep,
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        if not symbols or len(symbols) != len(set(symbols)) or tuple(sorted(symbols)) != symbols:
            raise ValueError("symbols must be non-empty, unique, and sorted")
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame.Minute,
            start=datetime.combine(start, datetime_time(), _NEW_YORK).astimezone(UTC),
            end=datetime.combine(end + timedelta(days=1), datetime_time(), _NEW_YORK).astimezone(UTC),
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.IEX,
        )
        for attempt in range(retries + 1):
            try:
                response = self._client.get_stock_bars(request)
                return normalize_alpaca_bars(response.df.reset_index())
            except Exception:
                if attempt >= retries:
                    raise
                sleep(min(30.0, 2.0**attempt))
        raise AssertionError("unreachable")


def normalize_alpaca_bars(source: pd.DataFrame, *, ingested_at: datetime | None = None) -> pd.DataFrame:
    """Retain Alpaca bar fields, restrict to XNYS RTH, and never synthesize rows."""
    if source.empty:
        return pd.DataFrame(
            {
                "symbol": pd.Series(dtype="string"),
                "timestamp": pd.Series([], dtype="datetime64[ns, UTC]"),
                "open": pd.Series(dtype="float64"),
                "high": pd.Series(dtype="float64"),
                "low": pd.Series(dtype="float64"),
                "close": pd.Series(dtype="float64"),
                "volume": pd.Series(dtype="float64"),
                "session_date": pd.Series(dtype="object"),
                "provider": pd.Series(dtype="string"),
                "feed": pd.Series(dtype="string"),
                "ingested_at": pd.Series([], dtype="datetime64[ns, UTC]"),
            }
        )
    missing = sorted(set(_REQUIRED_SOURCE_COLUMNS).difference(source.columns))
    if missing:
        raise ValueError(f"Alpaca IEX bar schema is missing columns: {missing}")
    retained_columns = list(_REQUIRED_SOURCE_COLUMNS) + [
        column for column in OPTIONAL_BAR_COLUMNS if column in source.columns
    ]
    frame = source.loc[:, retained_columns].copy()
    frame["symbol"] = frame["symbol"].astype("string").str.strip().str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume") + tuple(
        item for item in OPTIONAL_BAR_COLUMNS if item in frame.columns
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    localized = frame["timestamp"].dt.tz_convert(_NEW_YORK)
    frame["session_date"] = localized.dt.date
    minute = (localized.dt.hour - 9) * 60 + localized.dt.minute - 30
    frame = frame.loc[minute.between(0, 389)].copy()
    frame["provider"] = "alpaca"
    frame["feed"] = "iex"
    observed_at = datetime.now(UTC) if ingested_at is None else ingested_at.astimezone(UTC)
    frame["ingested_at"] = observed_at
    frame, _ = restrict_to_xnys_regular_grid(frame)
    return frame.sort_values(["symbol", "timestamp"], kind="stable", ignore_index=True)


def restrict_to_xnys_regular_grid(bars: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove source rows outside each session's exact XNYS regular-minute grid."""
    if bars.empty:
        return bars.copy(), 0
    session_dates = tuple(sorted(set(bars["session_date"].tolist())))
    expected_parts: list[pd.DatetimeIndex] = []
    for session_date in session_dates:
        try:
            expected_parts.append(expected_minute_index(cast(date, session_date)))
        except NotSessionError:
            continue
    if expected_parts:
        expected = pd.DatetimeIndex(
            [timestamp for part in expected_parts for timestamp in part]
        )
    else:
        expected = pd.DatetimeIndex([], tz="UTC")
    retained = pd.DatetimeIndex(bars["timestamp"]).isin(expected)
    filtered_rows = int((~retained).sum())
    return bars.loc[retained].copy().reset_index(drop=True), filtered_rows


def assess_acquired_bars(
    bars: pd.DataFrame,
    *,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> dict[str, object]:
    """Measure exact XNYS coverage and block corrupt or suspicious adjusted prices."""
    if bars.empty:
        raise ValueError("download returned no Alpaca IEX bars")
    numeric = bars.loc[:, ["open", "high", "low", "close", "volume"]]
    finite = np.isfinite(numeric.to_numpy(dtype="float64")).all(axis=1)
    invalid_ohlc = (
        ~finite
        | numeric[["open", "high", "low", "close"]].le(0).any(axis=1)
        | numeric["high"].lt(numeric[["open", "low", "close"]].max(axis=1))
        | numeric["low"].gt(numeric[["open", "high", "close"]].min(axis=1))
        | numeric["volume"].lt(0)
    )
    duplicates = bars.duplicated(["symbol", "timestamp"], keep=False)
    invalid_optional = pd.Series(False, index=bars.index)
    if "trade_count" in bars.columns:
        trade_count = bars["trade_count"]
        invalid_optional |= ~np.isfinite(trade_count.to_numpy(dtype="float64")) | trade_count.lt(0)
    if "vwap" in bars.columns:
        vwap = bars["vwap"]
        invalid_optional |= ~np.isfinite(vwap.to_numpy(dtype="float64")) | vwap.le(0)
    timestamps = pd.DatetimeIndex(bars["timestamp"])
    if str(timestamps.tz) != "UTC":
        raise ValueError("Alpaca timestamps must be UTC")
    cadence_misaligned = sum(
        value != 0
        for values in (timestamps.second, timestamps.microsecond, timestamps.nanosecond)
        for value in values
    )
    sessions = tuple(
        session.date()
        for session in _XNYS.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    )
    unexpected_symbols = sorted(set(bars["symbol"].astype(str)).difference(symbols))
    unexpected_session_rows = int((~bars["session_date"].isin(sessions)).sum())
    expected_groups = len(symbols) * len(sessions)
    missing_total = 0
    outside_session_total = 0
    expected_minutes_total = 0
    observed_minutes_total = 0
    observed_groups = 0
    group_records: list[dict[str, object]] = []
    for symbol in symbols:
        symbol_rows = bars.loc[bars["symbol"].eq(symbol)]
        for session in sessions:
            expected = expected_minute_index(session)
            observed = pd.DatetimeIndex(
                symbol_rows.loc[symbol_rows["session_date"].eq(session), "timestamp"]
            ).unique()
            missing = len(expected.difference(observed))
            outside_session = len(observed.difference(expected))
            observed_minutes = len(observed.intersection(expected))
            missing_total += missing
            outside_session_total += outside_session
            expected_minutes_total += len(expected)
            observed_minutes_total += observed_minutes
            observed_groups += observed_minutes > 0
            group_records.append(
                {
                    "symbol": symbol,
                    "session_date": session.isoformat(),
                    "expected_minutes": len(expected),
                    "observed_minutes": observed_minutes,
                    "missing_minutes": missing,
                    "outside_session_minutes": outside_session,
                }
            )
    ordered = bars.sort_values(["symbol", "timestamp"]).copy()
    prior_close = ordered.groupby("symbol", observed=True)["close"].shift()
    adjusted_jump = (ordered["open"] / prior_close - 1.0).abs().gt(0.60) & prior_close.notna()
    intrabar_range = (ordered["high"] / ordered["low"] - 1.0).gt(0.50)
    structural_passed = not bool(
        invalid_ohlc.any()
        or invalid_optional.any()
        or duplicates.any()
        or cadence_misaligned
        or unexpected_symbols
        or unexpected_session_rows
        or outside_session_total
    )
    anomaly_passed = not bool(adjusted_jump.any() or intrabar_range.any())
    if not structural_passed or not anomaly_passed:
        raise ValueError("Alpaca IEX bars failed structural or adjusted-price anomaly gates")
    return {
        "structural_passed": structural_passed,
        "adjusted_price_anomaly_passed": anomaly_passed,
        "complete": missing_total == 0,
        "duplicate_rows": int(duplicates.sum()),
        "invalid_ohlcv_rows": int(invalid_ohlc.sum()),
        "invalid_optional_bar_field_rows": int(invalid_optional.sum()),
        "cadence_misaligned_rows": cadence_misaligned,
        "unexpected_symbols": unexpected_symbols,
        "unexpected_session_rows": unexpected_session_rows,
        "outside_session_rows": outside_session_total,
        "adjusted_jump_rows": int(adjusted_jump.sum()),
        "intrabar_range_anomaly_rows": int(intrabar_range.sum()),
        "expected_symbol_sessions": expected_groups,
        "observed_symbol_sessions": observed_groups,
        "expected_minutes": expected_minutes_total,
        "observed_minutes": observed_minutes_total,
        "missing_minutes": missing_total,
        "groups": group_records,
    }


def publish_window_snapshot(
    bars: pd.DataFrame,
    *,
    root: Path,
    window: AcquisitionWindow,
    symbols: tuple[str, ...],
    source_outside_session_rows_filtered: int = 0,
) -> dict[str, object]:
    """Atomically publish one content-addressed snapshot; an existing ID is read-only."""
    root = root.resolve()
    canonical = root / "data" / "lake" / "acquired"
    canonical.mkdir(parents=True, exist_ok=True)
    quality = assess_acquired_bars(bars, symbols=symbols, start=window.start, end=window.end)
    quality["source_outside_session_rows_filtered"] = source_outside_session_rows_filtered
    temporary = Path(tempfile.mkdtemp(prefix=".alpaca-iex-", dir=canonical)).resolve()
    try:
        data_file = temporary / "bars.parquet"
        bars.to_parquet(data_file, index=False, compression="zstd")
        evidence = {
            "schema_version": "1.0.0",
            "provider": "alpaca",
            "feed": "iex",
            "bar_size": "1min",
            "adjustment": "split",
            "calendar": "XNYS",
            "window": {
                "label": window.label,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "blind_test_candidate": window.blind_test_candidate,
                "strategy_metrics_permitted": not window.blind_test_candidate,
            },
            "symbols": list(symbols),
            "retained_optional_bar_fields": [
                column for column in OPTIONAL_BAR_COLUMNS if column in bars.columns
            ],
            "quote_fields": {"retained": [], "reason": "not present in StockBarsRequest response"},
            "no_fill_policy": True,
            "quality": quality,
        }
        evidence_path = temporary / "quality-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", "utf-8")
        content_sha256 = _content_hash(temporary, (data_file, evidence_path))
        code_revision = _code_revision(root)
        identity = {
            "content_sha256": content_sha256,
            "provider": "alpaca",
            "feed": "iex",
            "bar_size": "1min",
            "adjustment": "split",
            "calendar": "XNYS",
            "calendar_version": _package_version("exchange-calendars"),
            "code_revision": code_revision,
            "window": evidence["window"],
            "symbols": list(symbols),
        }
        dataset_id = "alpaca-iex-1min-" + hashlib.sha256(
            _canonical_json(identity).encode()
        ).hexdigest()[:32]
        created_at = pd.Timestamp(bars["ingested_at"].max()).to_pydatetime().astimezone(UTC)
        manifest = {
            "schema_version": "1.0.0",
            "dataset_id": dataset_id,
            **identity,
            "created_at": created_at.isoformat(),
            "row_count": len(bars),
            "min_timestamp": pd.Timestamp(bars["timestamp"].min()).isoformat(),
            "max_timestamp": pd.Timestamp(bars["timestamp"].max()).isoformat(),
            "quality_complete": bool(quality["complete"]),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        final = canonical / dataset_id
        if final.exists():
            retained = verify_window_snapshot(final)
            if retained != manifest:
                raise ValueError("immutable Alpaca snapshot identity collision")
            shutil.rmtree(temporary)
            return retained
        temporary.rename(final)
        return manifest
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def verify_window_snapshot(snapshot_root: Path) -> dict[str, object]:
    snapshot_root = snapshot_root.resolve()
    manifest = cast(
        dict[str, object], json.loads((snapshot_root / "manifest.json").read_text("utf-8"))
    )
    expected_name = str(manifest["dataset_id"])
    if snapshot_root.name != expected_name:
        raise ValueError("snapshot directory does not match dataset identity")
    files = (snapshot_root / "bars.parquet", snapshot_root / "quality-evidence.json")
    if not all(path.is_file() for path in files):
        raise ValueError("snapshot content is incomplete")
    if _content_hash(snapshot_root, files) != manifest["content_sha256"]:
        raise ValueError("snapshot content hash mismatch")
    identity_fields = (
        "content_sha256",
        "provider",
        "feed",
        "bar_size",
        "adjustment",
        "calendar",
        "calendar_version",
        "code_revision",
        "window",
        "symbols",
    )
    identity = {field: manifest[field] for field in identity_fields}
    identity_hash = hashlib.sha256(_canonical_json(identity).encode()).hexdigest()[:32]
    if expected_name != f"alpaca-iex-1min-{identity_hash}":
        raise ValueError("snapshot manifest identity mismatch")
    return manifest


def _verified_existing_window(
    *,
    root: Path,
    window: AcquisitionWindow,
    symbols: tuple[str, ...],
) -> dict[str, object] | None:
    """Reuse a current-format immutable snapshot without reloading staged bars."""
    acquired = root.resolve() / "data" / "lake" / "acquired"
    if not acquired.is_dir():
        return None
    candidates: list[tuple[datetime, dict[str, object]]] = []
    for snapshot_root in acquired.iterdir():
        if not snapshot_root.is_dir():
            continue
        try:
            manifest = verify_window_snapshot(snapshot_root)
            evidence = cast(
                dict[str, object],
                json.loads((snapshot_root / "quality-evidence.json").read_text("utf-8")),
            )
            quality = cast(dict[str, object], evidence["quality"])
            manifest_window = cast(dict[str, object], manifest["window"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
        current_format = "source_outside_session_rows_filtered" in quality
        matches = (
            current_format
            and manifest_window.get("label") == window.label
            and manifest_window.get("start") == window.start.isoformat()
            and manifest_window.get("end") == window.end.isoformat()
            and tuple(cast(list[str], manifest.get("symbols", []))) == symbols
        )
        if matches:
            candidates.append((datetime.fromisoformat(str(manifest["created_at"])), manifest))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def audit_acquisition_environment(
    *,
    root: Path,
    available_through: date,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Audit local manifests and credential presence without reading secret values."""
    root = root.resolve()
    values = os.environ if environ is None else environ
    existing: list[dict[str, object]] = []
    lake = root / "data" / "lake"
    if lake.is_dir():
        for path in sorted(lake.rglob("manifest.json")):
            try:
                manifest = cast(dict[str, object], json.loads(path.read_text("utf-8")))
            except (OSError, json.JSONDecodeError):
                existing.append({"path": path.relative_to(root).as_posix(), "readable": False})
                continue
            existing.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "readable": True,
                    "dataset_id": manifest.get("dataset_id"),
                    "provider": manifest.get("provider"),
                    "feed": manifest.get("feed"),
                    "bar_size": manifest.get("bar_size"),
                    "row_count": manifest.get("row_count"),
                    "symbols": manifest.get("symbols"),
                    "min_timestamp": manifest.get("min_timestamp"),
                    "max_timestamp": manifest.get("max_timestamp"),
                    "quality_complete": manifest.get(
                        "quality_complete", cast(dict[str, object], manifest.get("quality", {})).get("passed")
                    ),
                }
            )
    return {
        "schema_version": "1.0.0",
        "root": root.as_posix(),
        "credentials": {
            API_KEY_VARIABLE: bool(values.get(API_KEY_VARIABLE, "")),
            SECRET_KEY_VARIABLE: bool(values.get(SECRET_KEY_VARIABLE, "")),
            "values_disclosed": False,
        },
        "read_only_boundary": {
            "historical_market_data_only": True,
            "broker_client_available": False,
            "submit_cancel_available": False,
        },
        "planned_symbols": sorted(DEFAULT_SYMBOLS),
        "planned_windows_in_priority_order": [
            {
                "label": window.label,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "blind_test_candidate": window.blind_test_candidate,
            }
            for window in default_windows(available_through)
        ],
        "existing_snapshots": existing,
    }


def _staged_chunk(
    *,
    root: Path,
    downloader: ReadOnlyAlpacaIexDownloader,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> pd.DataFrame:
    """Download one month once and reuse it only when its recorded hash matches."""
    symbol_hash = hashlib.sha256(",".join(symbols).encode()).hexdigest()[:12]
    staging = root.resolve() / "data" / "staging" / "alpaca_iex_1min" / symbol_hash
    staging.mkdir(parents=True, exist_ok=True)
    stem = f"{start.isoformat()}_{end.isoformat()}"
    output = staging / f"{stem}.parquet"
    record_path = staging / f"{stem}.json"
    if output.is_file() and record_path.is_file():
        record = cast(dict[str, object], json.loads(record_path.read_text("utf-8")))
        if record.get("file_sha256") != _sha256_file(output):
            raise ValueError(f"staged Alpaca chunk hash mismatch: {output}")
        return pd.read_parquet(output)
    if output.exists() or record_path.exists():
        raise ValueError(f"partial staged Alpaca chunk requires manual audit: {stem}")
    bars = downloader.fetch(symbols=symbols, start=start, end=end)
    temporary = output.with_suffix(".tmp.parquet")
    bars.to_parquet(temporary, index=False, compression="zstd")
    file_sha256 = _sha256_file(temporary)
    temporary.replace(output)
    record = {
        "schema_version": "1.0.0",
        "provider": "alpaca",
        "feed": "iex",
        "bar_size": "1min",
        "adjustment": "split",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "symbols": list(symbols),
        "rows": len(bars),
        "file_sha256": file_sha256,
    }
    temporary_record = record_path.with_suffix(".tmp")
    temporary_record.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", "utf-8")
    temporary_record.replace(record_path)
    return bars


def _record_unavailable_window(
    *,
    root: Path,
    window: AcquisitionWindow,
    symbols: tuple[str, ...],
) -> dict[str, object]:
    """Write immutable evidence when Alpaca returns no rows for a complete window."""
    payload = {
        "schema_version": "1.0.0",
        "provider": "alpaca",
        "feed": "iex",
        "bar_size": "1min",
        "adjustment": "split",
        "calendar": "XNYS",
        "window": {
            "label": window.label,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "blind_test_candidate": window.blind_test_candidate,
        },
        "symbols": list(symbols),
        "row_count": 0,
        "availability": "provider_returned_no_rows",
        "no_fill_policy": True,
    }
    evidence_sha256 = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
    record = {**payload, "evidence_sha256": evidence_sha256}
    output_root = root.resolve() / "data" / "catalog" / "alpaca_iex_unavailable"
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / f"{window.label}-{evidence_sha256[:16]}.json"
    rendered = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if output.exists() and output.read_text("utf-8") != rendered:
        raise ValueError("Alpaca unavailability evidence identity collision")
    if not output.exists():
        temporary = output.with_suffix(".tmp")
        temporary.write_text(rendered, "utf-8")
        temporary.replace(output)
    return record


def acquire_all_windows(
    *,
    root: Path,
    downloader: ReadOnlyAlpacaIexDownloader,
    symbols: tuple[str, ...] = tuple(sorted(DEFAULT_SYMBOLS)),
    available_through: date | None = None,
) -> list[dict[str, object]]:
    """Download priority windows in monthly requests, then publish one snapshot per window."""
    through = latest_completed_session() if available_through is None else available_through
    manifests: list[dict[str, object]] = []
    for window in default_windows(through):
        existing = _verified_existing_window(root=root, window=window, symbols=symbols)
        if existing is not None:
            manifests.append(existing)
            continue
        frames = [
            _staged_chunk(
                root=root,
                downloader=downloader,
                symbols=symbols,
                start=start,
                end=end,
            )
            for start, end in _month_chunks(window)
        ]
        bars = pd.concat(frames, ignore_index=True).sort_values(
            ["symbol", "timestamp"], kind="stable", ignore_index=True
        )
        bars, source_outside_session_rows_filtered = restrict_to_xnys_regular_grid(bars)
        if bars.empty:
            manifests.append(
                _record_unavailable_window(root=root, window=window, symbols=symbols)
            )
            continue
        manifests.append(
            publish_window_snapshot(
                bars,
                root=root,
                window=window,
                symbols=symbols,
                source_outside_session_rows_filtered=source_outside_session_rows_filtered,
            )
        )
    return manifests
