"""Immutable, training-only FINRA Consolidated NMS short-volume acquisition."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

TRAINING_START = date(2021, 1, 1)
TRAINING_END = date(2023, 12, 31)
BASE_URL = "https://cdn.finra.org/equity/regsho/daily"
HEADER = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"
TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
Sleep = Callable[[float], None]


@dataclass(frozen=True)
class HttpPayload:
    body: bytes
    status: int
    headers: Mapping[str, str]
    url: str


class DailyTransport(Protocol):
    def __call__(self, trade_date: date) -> HttpPayload: ...


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_daily_file(body: bytes, expected_date: date) -> pd.DataFrame:
    """Parse and validate one complete provider body without symbol rewriting."""
    try:
        lines = body.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("FINRA_BODY_ENCODING_INVALID") from error
    if len(lines) < 2 or lines[0].rstrip("\r") != HEADER:
        raise ValueError("FINRA_HEADER_INVALID")
    try:
        footer_count = int(lines[-1].strip())
    except ValueError as error:
        raise ValueError("FINRA_FOOTER_INVALID") from error
    records = [line.rstrip("\r") for line in lines[1:-1] if line.strip()]
    if footer_count != len(records):
        raise ValueError("FINRA_FOOTER_COUNT_MISMATCH")
    parsed: list[dict[str, object]] = []
    for line in records:
        fields = line.split("|")
        if len(fields) != 6:
            raise ValueError("FINRA_ROW_FIELD_COUNT_INVALID")
        raw_date, symbol, short, exempt, total, market = fields
        if raw_date != expected_date.strftime("%Y%m%d"):
            raise ValueError("FINRA_TRADE_DATE_MISMATCH")
        try:
            short_volume = float(short)
            short_exempt_volume = float(exempt)
            total_volume = float(total)
        except ValueError as error:
            raise ValueError("FINRA_VOLUME_INVALID") from error
        if min(short_volume, short_exempt_volume, total_volume) < 0:
            raise ValueError("FINRA_VOLUME_NEGATIVE")
        if short_volume > total_volume:
            raise ValueError("FINRA_SHORT_OVER_TOTAL")
        parsed.append(
            {
                "trade_date": expected_date,
                "symbol": symbol,
                "short_volume": short_volume,
                "short_exempt_volume": short_exempt_volume,
                "total_volume": total_volume,
                "market": market,
            }
        )
    frame = pd.DataFrame.from_records(parsed)
    if frame.duplicated(["trade_date", "symbol"]).any():
        raise ValueError("FINRA_DUPLICATE_DATE_SYMBOL")
    frame.attrs["footer_count"] = footer_count
    return frame


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def fetch_daily_file(
    transport: DailyTransport,
    trade_date: date,
    *,
    sleep: Sleep = time.sleep,
    max_attempts: int = 5,
    base_backoff_seconds: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fetch one complete file and expose its conservative availability time."""
    if max_attempts < 1:
        raise ValueError("FINRA_RETRY_ATTEMPTS_INVALID")
    payload: HttpPayload | None = None
    for attempt in range(max_attempts):
        try:
            payload = transport(trade_date)
            break
        except HTTPError as error:
            if error.code not in TRANSIENT_HTTP_CODES or attempt + 1 >= max_attempts:
                raise
            sleep(base_backoff_seconds * 2**attempt)
        except (URLError, TimeoutError):
            if attempt + 1 >= max_attempts:
                raise
            sleep(base_backoff_seconds * 2**attempt)
    if payload is None:  # pragma: no cover - loop guarantees a return or raise
        raise RuntimeError("FINRA_FETCH_UNREACHABLE")
    modified_raw = _header(payload.headers, "Last-Modified")
    if not modified_raw:
        raise ValueError("FINRA_LAST_MODIFIED_MISSING")
    try:
        modified = parsedate_to_datetime(modified_raw)
    except (TypeError, ValueError) as error:
        raise ValueError("FINRA_LAST_MODIFIED_INVALID") from error
    if modified.tzinfo is None:
        raise ValueError("FINRA_LAST_MODIFIED_INVALID")
    modified = modified.astimezone(UTC)
    frame = parse_daily_file(payload.body, trade_date)
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "provider": "finra",
        "source_type": "consolidated_nms_daily_short_sale_volume",
        "trade_date": trade_date.isoformat(),
        "url": payload.url,
        "http_status": payload.status,
        "last_modified": modified.isoformat(),
        "etag": _header(payload.headers, "ETag"),
        "response_sha256": _sha256_bytes(payload.body),
        "row_count": len(frame),
        "footer_count": int(frame.attrs["footer_count"]),
        "complete": True,
        "training_only": True,
    }
    return frame, manifest


def acquire_sessions(
    root: Path,
    sessions: Sequence[date],
    transport: DailyTransport,
) -> list[dict[str, object]]:
    """Write hash-verified Parquet/manifest pairs for training sessions."""
    if any(day < TRAINING_START or day > TRAINING_END for day in sessions):
        raise ValueError("FINRA_SHORT_VOLUME_ACQUISITION_TRAINING_ONLY")
    output_root = root / "data/staging/finra_short_volume_v1"
    results: list[dict[str, object]] = []
    for day in sorted(set(sessions)):
        day_root = output_root / f"{day:%Y}"
        day_root.mkdir(parents=True, exist_ok=True)
        parquet = day_root / f"{day.isoformat()}.parquet"
        manifest_path = day_root / f"{day.isoformat()}.json"
        if parquet.is_file() and manifest_path.is_file():
            manifest = cast(
                dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8"))
            )
            if manifest.get("complete") is not True:
                raise ValueError(f"PARTIAL_FINRA_DAY:{day.isoformat()}")
            if manifest.get("content_sha256") != _sha256_file(parquet):
                raise ValueError(f"FINRA_DAY_HASH_MISMATCH:{day.isoformat()}")
            results.append(manifest)
            continue
        if parquet.exists() or manifest_path.exists():
            raise ValueError(f"PARTIAL_FINRA_DAY:{day.isoformat()}")
        frame, manifest = fetch_daily_file(transport, day)
        temporary_parquet = parquet.with_suffix(".tmp.parquet")
        frame.to_parquet(temporary_parquet, index=False, compression="zstd")
        manifest["content_sha256"] = _sha256_file(temporary_parquet)
        manifest["acquired_at"] = datetime.now(UTC).isoformat()
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=day_root, delete=False
        ) as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_manifest = Path(handle.name)
        temporary_parquet.replace(parquet)
        temporary_manifest.replace(manifest_path)
        results.append(manifest)
    return results


class FinraShortVolumeHttpTransport:
    """Unauthenticated official-CDN transport."""

    def __call__(self, trade_date: date) -> HttpPayload:
        url = f"{BASE_URL}/CNMSshvol{trade_date:%Y%m%d}.txt"
        request = Request(
            url,
            headers={"User-Agent": "us-intraday-lab-research/1.0"},
            method="GET",
        )
        with urlopen(request, timeout=30) as response:
            headers = {str(key): str(value) for key, value in response.headers.items()}
            return HttpPayload(
                body=response.read(),
                status=int(response.status),
                headers=headers,
                url=url,
            )
