from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.long_horizon.hf_snapshot import (
    HfFiveMinuteSnapshotError,
    HfFiveMinuteSnapshotStore,
    publish_hf_five_minute_snapshot,
)
from us_intraday_lab.long_horizon.orchestrator import LocalFiveMinuteResearchBackend


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(
    root: Path,
    *,
    slug: str = "spy-iwm",
    symbols: tuple[str, str] = ("SPY", "IWM"),
) -> None:
    source_name = f"hf_{slug.replace('-', '_')}_5min"
    raw = root / "data" / "raw" / source_name
    catalog = root / "data" / "catalog" / source_name / "months"
    raw.mkdir(parents=True)
    catalog.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for session in (date(2024, 1, 2), date(2024, 1, 3)):
        start = datetime.combine(session, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=14, minutes=30
        )
        for index in range(78):
            for symbol in symbols:
                price = 100.0 + index / 10
                timestamp = start + timedelta(minutes=index * 5)
                rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": timestamp,
                        "available_at": timestamp + timedelta(minutes=5),
                        "open": price,
                        "high": price + 0.1,
                        "low": price - 0.1,
                        "close": price + 0.05,
                        "volume": 1000.0,
                        "session_date": session,
                    }
                )
    output = raw / f"{slug}-2024-01.parquet"
    pd.DataFrame(rows).to_parquet(output, index=False)
    record = {
        "accepted_sessions": ["2024-01-02", "2024-01-03"],
        "bar_size": "5min",
        "month": "2024-01",
        "output_sha256": _sha256(output),
        "rejected_sessions": [],
        "repository": "mito0o852/OHLCV-1m",
        "revision": "main",
        "source_filename": "data/ohlcv_2024-01.parquet",
        "source_sha256": "a" * 64,
        "symbols": list(symbols),
    }
    (catalog / f"{slug}-2024-01.json").write_text(json.dumps(record), encoding="utf-8")


def test_hf_snapshot_reads_only_explicitly_requested_sessions(tmp_path: Path) -> None:
    _source(tmp_path)
    manifest = publish_hf_five_minute_snapshot(
        root=tmp_path,
        start_month="2024-01",
        end_month="2024-01",
        code_revision="test",
        created_at=datetime(2024, 2, 1, tzinfo=UTC),
    )
    store = HfFiveMinuteSnapshotStore(root=tmp_path, dataset_id=manifest.dataset_id)
    assert store.accepted_sessions == (date(2024, 1, 2), date(2024, 1, 3))

    sealed = (
        tmp_path
        / "data"
        / "lake"
        / "long_horizon"
        / "canonical"
        / manifest.dataset_id
        / "sessions"
        / "2024-01-03.parquet"
    )
    sealed.write_bytes(sealed.read_bytes() + b"tampered")

    train = store.read_sessions((date(2024, 1, 2),))
    assert set(train["session_date"]) == {date(2024, 1, 2)}
    backend = LocalFiveMinuteResearchBackend(root=tmp_path, dataset_id=manifest.dataset_id)
    assert backend.accepted_sessions(manifest.dataset_id) == (
        date(2024, 1, 2),
        date(2024, 1, 3),
    )
    with pytest.raises(HfFiveMinuteSnapshotError, match="session hash mismatch"):
        store.read_sessions((date(2024, 1, 3),))


def test_hf_snapshot_supports_an_explicit_alternate_pair(tmp_path: Path) -> None:
    _source(tmp_path, slug="tqqq-upro", symbols=("TQQQ", "UPRO"))

    manifest = publish_hf_five_minute_snapshot(
        root=tmp_path,
        start_month="2024-01",
        end_month="2024-01",
        code_revision="test",
        created_at=datetime(2024, 2, 1, tzinfo=UTC),
        slug="tqqq-upro",
        symbols=("TQQQ", "UPRO"),
    )
    store = HfFiveMinuteSnapshotStore(root=tmp_path, dataset_id=manifest.dataset_id)

    assert store.symbols == ("TQQQ", "UPRO")
    assert set(store.read_sessions((date(2024, 1, 2),))["symbol"]) == {
        "TQQQ",
        "UPRO",
    }
