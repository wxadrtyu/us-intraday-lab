"""Immutable Polygon point-in-time US-stock reference data.

This module uses only Polygon's historical reference-data endpoint. It has no
broker, account, position, order, submit, or cancel capability.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import time as time_module
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

import pandas as pd

POLYGON_API_KEY_VARIABLE = "POLYGON_API_KEY"
POLYGON_REFERENCE_NAMESPACE = "polygon_reference_tickers_v1"
POLYGON_REFERENCE_ENDPOINT = "https://api.polygon.io/v3/reference/tickers"

_REFERENCE_COLUMNS = (
    "ticker",
    "name",
    "market",
    "locale",
    "primary_exchange",
    "type",
    "active",
    "currency_name",
    "cik",
    "composite_figi",
    "share_class_figi",
    "delisted_utc",
    "last_updated_utc",
    "asof",
    "provider",
)


class PageTransport(Protocol):
    def __call__(
        self, url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]: ...


def _urllib_transport(
    url: str, headers: Mapping[str, str]
) -> tuple[int, bytes, Mapping[str, str]]:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as error:
        return error.code, error.read(), dict(error.headers.items())


class PolygonReferenceClient:
    """Secret-isolated, read-only client for Polygon reference pages."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: PageTransport = _urllib_transport,
        sleep: Callable[[float], None] = time_module.sleep,
    ) -> None:
        if not api_key:
            raise RuntimeError("POLYGON_API_KEY_MISSING")
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        transport: PageTransport = _urllib_transport,
        sleep: Callable[[float], None] = time_module.sleep,
    ) -> PolygonReferenceClient:
        values = os.environ if environ is None else environ
        return cls(
            values.get(POLYGON_API_KEY_VARIABLE, ""),
            transport=transport,
            sleep=sleep,
        )

    def get_page(self, url: str) -> tuple[bytes, Mapping[str, str]]:
        safe_url = validate_page_url(url)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": "us-intraday-lab-polygon-master/1.0",
        }
        for attempt in range(5):
            try:
                status, body, response_headers = self._transport(safe_url, headers)
            except Exception as error:
                if attempt == 4:
                    raise RuntimeError("POLYGON_TRANSPORT_RETRIES_EXHAUSTED") from error
                self._sleep(float(2**attempt))
                continue
            if status == 200:
                return body, response_headers
            if status in {401, 403}:
                raise RuntimeError("POLYGON_AUTHORIZATION_FAILED")
            if status == 429 or 500 <= status <= 599:
                if attempt == 4:
                    raise RuntimeError(f"POLYGON_HTTP_RETRIES_EXHAUSTED:{status}")
                retry_after = _retry_after_seconds(response_headers)
                self._sleep(retry_after if retry_after is not None else float(2**attempt))
                continue
            raise RuntimeError(f"POLYGON_HTTP_STATUS:{status}")
        raise AssertionError("unreachable")


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    value = next(
        (raw for key, raw in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if value is None:
        return None
    try:
        return min(60.0, max(0.0, float(value)))
    except ValueError:
        return None


def month_end_dates(start: date, end: date) -> tuple[date, ...]:
    """Return one deterministic as-of date for every intersecting month."""
    if start > end:
        raise ValueError("start must not exceed end")
    values: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        values.append(min(month_end, end))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(values)


def initial_request_identity(asof: date, active: bool) -> dict[str, object]:
    """Build the complete, secret-free first-page request identity."""
    return {
        "market": "stocks",
        "locale": "us",
        "date": asof.isoformat(),
        "active": active,
        "limit": 1000,
        "sort": "ticker",
        "order": "asc",
    }


def request_url(identity: Mapping[str, object]) -> str:
    """Encode a redacted request identity as the fixed Polygon endpoint URL."""
    values = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in identity.items()
    }
    return f"{POLYGON_REFERENCE_ENDPOINT}?{urlencode(values)}"


def validate_page_url(url: str) -> str:
    """Reject credentials and pagination redirects outside the frozen endpoint."""
    parsed = urlsplit(url)
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if "apikey" in query_keys:
        raise ValueError("POLYGON_PAGE_URL_CONTAINS_CREDENTIAL")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.polygon.io"
        or parsed.path != "/v3/reference/tickers"
        or parsed.fragment
    ):
        raise ValueError("POLYGON_PAGE_URL_FORBIDDEN")
    return url


def normalize_page(
    payload: Mapping[str, object], *, asof: date, active: bool
) -> pd.DataFrame:
    """Normalize one provider page without inventing absent reference fields."""
    if payload.get("status") != "OK":
        raise ValueError("POLYGON_PAGE_STATUS_NOT_OK")
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raise TypeError("POLYGON_PAGE_RESULTS_NOT_LIST")

    rows: list[dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, Mapping):
            raise TypeError("POLYGON_PAGE_RESULT_NOT_OBJECT")
        ticker = str(raw.get("ticker", "")).strip().upper()
        if not ticker:
            raise ValueError("POLYGON_TICKER_MISSING")
        if raw.get("market") != "stocks" or raw.get("locale") != "us":
            raise ValueError("POLYGON_MARKET_OR_LOCALE_MISMATCH")
        if raw.get("active") is not active:
            raise ValueError("POLYGON_ACTIVE_STATE_MISMATCH")
        row = {column: raw.get(column, pd.NA) for column in _REFERENCE_COLUMNS}
        row.update(
            {
                "ticker": ticker,
                "active": active,
                "asof": asof,
                "provider": "polygon",
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows, columns=_REFERENCE_COLUMNS)
    for column in set(_REFERENCE_COLUMNS).difference({"active", "asof"}):
        result[column] = result[column].astype("string")
    result["active"] = result["active"].astype("boolean")
    if result.empty:
        return result
    return result.sort_values(["ticker", "active"], kind="stable").reset_index(drop=True)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_payload(content: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("POLYGON_PAGE_INVALID_JSON") from error
    if not isinstance(value, Mapping):
        raise TypeError("POLYGON_PAGE_NOT_OBJECT")
    return value


def _raw_root(root: Path, *, asof: date, active: bool) -> Path:
    return (
        root.resolve()
        / "data"
        / "staging"
        / POLYGON_REFERENCE_NAMESPACE
        / "raw"
        / f"asof={asof.isoformat()}"
        / f"active={str(active).lower()}"
    )


def _page_paths(directory: Path, *, page_number: int, url: str) -> tuple[Path, Path]:
    request_hash = _sha256_bytes(url.encode())
    stem = f"page-{page_number:05d}-{request_hash[:16]}"
    return directory / f"{stem}.json", directory / f"{stem}.manifest.json"


def _validate_existing_raw_directory(directory: Path) -> None:
    manifests = {
        path.name.removesuffix(".manifest.json")
        for path in directory.glob("page-*.manifest.json")
    }
    pages = {
        path.stem
        for path in directory.glob("page-*.json")
        if not path.name.endswith(".manifest.json")
    }
    temporary = tuple(directory.glob("*.tmp")) + tuple(directory.glob("*.tmp.*"))
    if manifests != pages or temporary:
        raise ValueError("POLYGON_RAW_PAGE_PAIRING_FAILURE")


def _next_url(payload: Mapping[str, object]) -> str | None:
    raw = payload.get("next_url")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise ValueError("POLYGON_NEXT_URL_INVALID")
    return validate_page_url(raw)


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def acquire_activity_pages(
    *,
    root: Path,
    client: PolygonReferenceClient,
    asof: date,
    active: bool,
    sleep: Callable[[float], None] = time_module.sleep,
    minimum_request_interval_seconds: float = 0.0,
) -> list[dict[str, object]]:
    """Acquire or verify one complete as-of/activity pagination chain."""
    if minimum_request_interval_seconds < 0:
        raise ValueError("minimum request interval must be non-negative")
    directory = _raw_root(root, asof=asof, active=active)
    directory.mkdir(parents=True, exist_ok=True)
    _validate_existing_raw_directory(directory)

    url: str | None = request_url(initial_request_identity(asof, active))
    records: list[dict[str, object]] = []
    page_number = 1
    while url is not None:
        validate_page_url(url)
        page_path, manifest_path = _page_paths(
            directory, page_number=page_number, url=url
        )
        if page_path.is_file() and manifest_path.is_file():
            content = page_path.read_bytes()
            record = json.loads(manifest_path.read_text("utf-8"))
            if (
                not isinstance(record, dict)
                or record.get("request_url") != url
                or record.get("request_identity_sha256")
                != _sha256_bytes(url.encode())
                or record.get("content_sha256") != _sha256_bytes(content)
                or record.get("page_number") != page_number
                or record.get("asof") != asof.isoformat()
                or record.get("active") is not active
            ):
                raise ValueError("POLYGON_RAW_PAGE_PROVENANCE_FAILURE")
            payload = _parse_payload(content)
            normalize_page(payload, asof=asof, active=active)
            if record.get("provider_request_id") != payload.get("request_id"):
                raise ValueError("POLYGON_RAW_PAGE_REQUEST_ID_MISMATCH")
            next_url = _next_url(payload)
            if record.get("next_url") != next_url:
                raise ValueError("POLYGON_RAW_PAGE_CHAIN_MISMATCH")
            records.append(record)
            url = next_url
            page_number += 1
            continue
        if page_path.exists() or manifest_path.exists():
            raise ValueError("POLYGON_RAW_PAGE_PAIRING_FAILURE")

        content, _ = client.get_page(url)
        payload = _parse_payload(content)
        frame = normalize_page(payload, asof=asof, active=active)
        next_url = _next_url(payload)
        record = {
            "schema_version": "1.0.0",
            "source_namespace": POLYGON_REFERENCE_NAMESPACE,
            "provider": "polygon",
            "asof": asof.isoformat(),
            "active": active,
            "page_number": page_number,
            "request_url": url,
            "request_identity_sha256": _sha256_bytes(url.encode()),
            "content_sha256": _sha256_bytes(content),
            "provider_request_id": payload.get("request_id"),
            "result_count": len(frame),
            "next_page_present": next_url is not None,
            "next_url": next_url,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "read_only_reference_data": True,
        }
        _write_atomic(page_path, content)
        _write_atomic(
            manifest_path,
            (json.dumps(record, indent=2, sort_keys=True) + "\n").encode(),
        )
        records.append(record)
        url = next_url
        page_number += 1
        if url is not None and minimum_request_interval_seconds:
            sleep(minimum_request_interval_seconds)

    _validate_existing_raw_directory(directory)
    return records


def _load_activity_chain(
    root: Path, *, asof: date, active: bool
) -> tuple[list[dict[str, object]], list[pd.DataFrame]]:
    directory = _raw_root(root, asof=asof, active=active)
    if not directory.is_dir():
        raise ValueError("ACTIVITY_CHAIN_MISSING")
    _validate_existing_raw_directory(directory)
    url: str | None = request_url(initial_request_identity(asof, active))
    records: list[dict[str, object]] = []
    frames: list[pd.DataFrame] = []
    page_number = 1
    while url is not None:
        page_path, manifest_path = _page_paths(
            directory, page_number=page_number, url=url
        )
        if not page_path.is_file() or not manifest_path.is_file():
            raise ValueError("POLYGON_RAW_PAGE_CHAIN_MISMATCH")
        content = page_path.read_bytes()
        try:
            record = json.loads(manifest_path.read_text("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("POLYGON_RAW_PAGE_MANIFEST_INVALID") from error
        if (
            not isinstance(record, dict)
            or record.get("source_namespace") != POLYGON_REFERENCE_NAMESPACE
            or record.get("provider") != "polygon"
            or record.get("request_url") != url
            or record.get("request_identity_sha256") != _sha256_bytes(url.encode())
            or record.get("content_sha256") != _sha256_bytes(content)
            or record.get("page_number") != page_number
            or record.get("asof") != asof.isoformat()
            or record.get("active") is not active
        ):
            raise ValueError("POLYGON_RAW_PAGE_PROVENANCE_FAILURE")
        payload = _parse_payload(content)
        frame = normalize_page(payload, asof=asof, active=active)
        if record.get("result_count") != len(frame):
            raise ValueError("POLYGON_RAW_PAGE_ROW_COUNT_MISMATCH")
        if record.get("provider_request_id") != payload.get("request_id"):
            raise ValueError("POLYGON_RAW_PAGE_REQUEST_ID_MISMATCH")
        next_url = _next_url(payload)
        if (
            record.get("next_url") != next_url
            or record.get("next_page_present") is not (next_url is not None)
        ):
            raise ValueError("POLYGON_RAW_PAGE_CHAIN_MISMATCH")
        records.append(record)
        frames.append(frame)
        url = next_url
        page_number += 1

    if len(tuple(directory.glob("page-*.manifest.json"))) != len(records):
        raise ValueError("POLYGON_RAW_PAGE_CHAIN_MISMATCH")
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not combined.empty and combined.duplicated(["ticker", "active"]).any():
        raise ValueError("POLYGON_DUPLICATE_TICKER_ACTIVITY")
    return records, frames


def _snapshot_directory(root: Path, asof: date) -> Path:
    return (
        root.resolve()
        / "data"
        / "staging"
        / POLYGON_REFERENCE_NAMESPACE
        / "snapshots"
        / f"asof={asof.isoformat()}"
    )


def _derived_month(
    root: Path, asof: date
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    records: list[dict[str, object]] = []
    frames: list[pd.DataFrame] = []
    for active in (False, True):
        activity_records, activity_frames = _load_activity_chain(
            root, asof=asof, active=active
        )
        records.extend(activity_records)
        frames.extend(activity_frames)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=_REFERENCE_COLUMNS
    )
    if combined.empty:
        raise ValueError("POLYGON_MONTH_EMPTY")
    combined = combined.loc[:, _REFERENCE_COLUMNS].sort_values(
        ["ticker", "active"], kind="stable"
    ).reset_index(drop=True)
    return combined, records


def build_month_snapshot(root: Path, asof: date) -> dict[str, object]:
    """Publish one canonical month only from its verified raw Polygon pages."""
    frame, records = _derived_month(root, asof)
    directory = _snapshot_directory(root, asof)
    directory.mkdir(parents=True, exist_ok=True)
    parquet_path = directory / "tickers.parquet"
    manifest_path = directory / "manifest.json"
    if parquet_path.is_file() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("content_sha256") != _sha256_file(parquet_path)
            or manifest.get("raw_content_sha256")
            != [record["content_sha256"] for record in records]
            or manifest.get("row_count") != len(frame)
        ):
            raise ValueError("POLYGON_SNAPSHOT_PROVENANCE_FAILURE")
        existing = pd.read_parquet(parquet_path)
        pd.testing.assert_frame_equal(existing, frame, check_dtype=False)
        return manifest
    if parquet_path.exists() or manifest_path.exists():
        raise ValueError("POLYGON_SNAPSHOT_PAIRING_FAILURE")

    temporary = parquet_path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(parquet_path)
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "source_namespace": POLYGON_REFERENCE_NAMESPACE,
        "provider": "polygon",
        "asof": asof.isoformat(),
        "row_count": len(frame),
        "active_rows": int(frame["active"].eq(True).sum()),
        "inactive_rows": int(frame["active"].eq(False).sum()),
        "raw_page_count": len(records),
        "raw_content_sha256": [record["content_sha256"] for record in records],
        "content_sha256": _sha256_file(parquet_path),
        "missing_data_policy": "preserve_nulls_no_fill_no_inference",
        "provider_splicing": "FORBIDDEN",
    }
    _write_atomic(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return manifest


def _reason(error: Exception) -> str:
    message = str(error).split(":", maxsplit=1)[0]
    return message if message else type(error).__name__.upper()


def validate_historical_master(
    root: Path, *, start: date, end: date
) -> dict[str, object]:
    """Reconstruct and validate the expected master without trusting completion flags."""
    expected = month_end_dates(start, end)
    source = root.resolve() / "data" / "staging" / POLYGON_REFERENCE_NAMESPACE
    partial_files = sorted(
        path.as_posix()
        for path in source.rglob("*")
        if path.is_file() and (".tmp" in path.name)
    ) if source.exists() else []
    reasons: list[str] = []
    if partial_files:
        reasons.append("PARTIAL_FILES_PRESENT")

    raw_pages = 0
    rows = 0
    active_rows = 0
    inactive_rows = 0
    content_hashes_valid = True
    page_chains_valid = True
    snapshots_reconstructed = True
    for asof in expected:
        try:
            derived, records = _derived_month(root, asof)
            raw_pages += len(records)
        except (OSError, TypeError, ValueError) as error:
            reason = _reason(error)
            if reason not in reasons:
                reasons.append(reason)
            page_chains_valid = False
            snapshots_reconstructed = False
            continue

        rows += len(derived)
        active_rows += int(derived["active"].eq(True).sum())
        inactive_rows += int(derived["active"].eq(False).sum())
        directory = _snapshot_directory(root, asof)
        parquet_path = directory / "tickers.parquet"
        manifest_path = directory / "manifest.json"
        if not parquet_path.is_file() or not manifest_path.is_file():
            if "SNAPSHOT_MISSING" not in reasons:
                reasons.append("SNAPSHOT_MISSING")
            snapshots_reconstructed = False
            continue
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except json.JSONDecodeError:
            if "SNAPSHOT_MANIFEST_INVALID" not in reasons:
                reasons.append("SNAPSHOT_MANIFEST_INVALID")
            content_hashes_valid = False
            snapshots_reconstructed = False
            continue
        if manifest.get("content_sha256") != _sha256_file(parquet_path):
            if "SNAPSHOT_CONTENT_HASH_MISMATCH" not in reasons:
                reasons.append("SNAPSHOT_CONTENT_HASH_MISMATCH")
            content_hashes_valid = False
            snapshots_reconstructed = False
            continue
        if manifest.get("raw_content_sha256") != [
            record["content_sha256"] for record in records
        ]:
            if "SNAPSHOT_RAW_LINEAGE_MISMATCH" not in reasons:
                reasons.append("SNAPSHOT_RAW_LINEAGE_MISMATCH")
            content_hashes_valid = False
            snapshots_reconstructed = False
            continue
        try:
            snapshot = pd.read_parquet(parquet_path)
            pd.testing.assert_frame_equal(snapshot, derived, check_dtype=False)
        except (AssertionError, OSError, TypeError, ValueError):
            if "SNAPSHOT_RECONSTRUCTION_MISMATCH" not in reasons:
                reasons.append("SNAPSHOT_RECONSTRUCTION_MISMATCH")
            snapshots_reconstructed = False

    return {
        "schema_version": "1.0.0",
        "source_namespace": POLYGON_REFERENCE_NAMESPACE,
        "provider": "polygon",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "months": len(expected),
        "raw_pages": raw_pages,
        "rows": rows,
        "active_rows": active_rows,
        "inactive_rows": inactive_rows,
        "content_hashes_valid": content_hashes_valid,
        "page_chains_valid": page_chains_valid,
        "snapshots_reconstructed": snapshots_reconstructed,
        "partial_files": len(partial_files),
        "partial_file_paths": partial_files,
        "provider_splicing": "FORBIDDEN",
        "missing_data_policy": "preserve_nulls_no_fill_no_inference",
        "rejection_reasons": reasons,
        "passed": not reasons,
    }


def load_historical_master_validation(path: Path) -> dict[str, object]:
    """Accept only complete frozen-range evidence emitted by the validator."""
    content = path.read_bytes()
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("HISTORICAL_MASTER_VALIDATION_INCOMPLETE") from error
    if not isinstance(value, dict):
        raise TypeError("HISTORICAL_MASTER_VALIDATION_INCOMPLETE")
    if value.get("passed") is False or value.get("rejection_reasons"):
        raise RuntimeError("HISTORICAL_MASTER_VALIDATION_FAILED")
    complete = (
        value.get("schema_version") == "1.0.0"
        and value.get("source_namespace") == POLYGON_REFERENCE_NAMESPACE
        and value.get("provider") == "polygon"
        and value.get("start") == "2018-01-01"
        and value.get("end") == "2026-03-31"
        and value.get("months") == 99
        and isinstance(value.get("raw_pages"), int)
        and int(value["raw_pages"]) > 0
        and isinstance(value.get("rows"), int)
        and int(value["rows"]) > 0
        and isinstance(value.get("active_rows"), int)
        and int(value["active_rows"]) > 0
        and isinstance(value.get("inactive_rows"), int)
        and int(value["inactive_rows"]) > 0
        and value.get("content_hashes_valid") is True
        and value.get("page_chains_valid") is True
        and value.get("snapshots_reconstructed") is True
        and value.get("partial_files") == 0
        and value.get("provider_splicing") == "FORBIDDEN"
        and value.get("rejection_reasons") == []
        and value.get("passed") is True
    )
    if not complete:
        raise RuntimeError("HISTORICAL_MASTER_VALIDATION_INCOMPLETE")
    result = dict(value)
    result["validation_report_sha256"] = _sha256_bytes(content)
    return result
