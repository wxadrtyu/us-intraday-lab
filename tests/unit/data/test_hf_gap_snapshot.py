from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.hf_gap_snapshot import (
    publish_hf_gap_snapshot,
    quarantine_duplicate_symbol_sessions,
    sha256_file,
    verify_hf_gap_snapshot,
)


def test_duplicate_minutes_quarantine_whole_symbol_session() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["SPY", "SPY", "SPY", "QQQ"],
            "timestamp": pd.to_datetime(
                [
                    "2020-12-01T14:30Z",
                    "2020-12-01T14:30Z",
                    "2020-12-01T14:31Z",
                    "2020-12-01T14:30Z",
                ]
            ),
            "session_date": [pd.Timestamp("2020-12-01").date()] * 4,
        }
    )

    retained, groups, duplicate_rows = quarantine_duplicate_symbol_sessions(bars)

    assert retained["symbol"].tolist() == ["QQQ"]
    assert groups == (("SPY", pd.Timestamp("2020-12-01").date()),)
    assert duplicate_rows == 2


def _month(root: Path, month: str) -> None:
    raw = root / "data" / "raw" / "hf_finnhub_gap_1min"
    catalog = root / "data" / "catalog" / "hf_finnhub_gap_1min" / "months"
    raw.mkdir(parents=True, exist_ok=True)
    catalog.mkdir(parents=True, exist_ok=True)
    output = raw / f"{month}-bars.parquet"
    pd.DataFrame({"timestamp": [pd.Timestamp(f"{month}-02T14:30:00Z")]}).to_parquet(output)
    digest = sha256_file(output)
    quality = {
        "expected_minutes": 2,
        "observed_minutes": 1,
        "missing_minutes": 1,
        "duplicate_rows": 0,
        "invalid_ohlcv_rows": 0,
        "outside_session_rows": 0,
        "cadence_misaligned_rows": 0,
        "adjusted_jump_rows": 0,
        "intrabar_range_anomaly_rows": 0,
        "source_outside_session_rows_filtered": 0,
        "source_duplicate_rows": 0,
        "adjusted_price_anomaly_passed": True,
        "quarantined_duplicate_groups": [],
    }
    record = {
        "repository": "example/data",
        "revision": "main",
        "source_filename": f"data/{month}.parquet",
        "source_sha256": "a" * 64,
        "output_path": output.as_posix(),
        "output_sha256": digest,
        "output_rows": 1,
        "min_timestamp": f"{month}-02T14:30:00+00:00",
        "max_timestamp": f"{month}-02T14:30:00+00:00",
        "month": month,
        "symbols": ["SPY"],
        "quality": quality,
    }
    (catalog / f"{month}-{digest[:16]}.json").write_text(json.dumps(record), "utf-8")


def test_publish_and_verify_content_addressed_snapshot(tmp_path: Path) -> None:
    _month(tmp_path, "2020-01")
    manifest = publish_hf_gap_snapshot(
        repo=Path.cwd(), root=tmp_path, label="test", months=("2020-01",)
    )
    snapshot = tmp_path / "data" / "lake" / "acquired_hf" / str(manifest["dataset_id"])

    verified = verify_hf_gap_snapshot(snapshot)

    assert verified == manifest
    assert verified["row_count"] == 1
    assert verified["quality_complete"] is False


def test_verify_rejects_mutated_snapshot(tmp_path: Path) -> None:
    _month(tmp_path, "2020-01")
    manifest = publish_hf_gap_snapshot(
        repo=Path.cwd(), root=tmp_path, label="test", months=("2020-01",)
    )
    snapshot = tmp_path / "data" / "lake" / "acquired_hf" / str(manifest["dataset_id"])
    (snapshot / "quality-evidence.json").write_text("{}", "utf-8")

    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_hf_gap_snapshot(snapshot)
