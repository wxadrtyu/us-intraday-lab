from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.datasets import DatasetManifest, DatasetQuality


def test_manifest_requires_content_hashes_and_versions() -> None:
    manifest = DatasetManifest(
        dataset_id="tiingo-iex-minute-20260702",
        schema_version="1.0.0",
        source_uri="file:///G:/quant-agent-team-us/data/us_stock_data.tar.gz",
        source_sha256="a" * 64,
        content_sha256="b" * 64,
        code_revision="2d48ada",
        calendar_name="XNYS",
        calendar_version="2026a",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        provider="tiingo",
        feed="iex",
        bar_size="1min",
        row_count=1,
        symbols=("SPY",),
        min_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        max_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        quality=DatasetQuality(passed=True),
    )

    assert manifest.dataset_id == "tiingo-iex-minute-20260702"


def test_manifest_rejects_non_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(
            {
                "dataset_id": "bad",
                "schema_version": "1.0.0",
                "source_uri": "file:///bad",
                "source_sha256": "short",
                "content_sha256": "b" * 64,
                "code_revision": "abc",
                "calendar_name": "XNYS",
                "calendar_version": "2026a",
                "created_at": "2026-07-26T00:00:00Z",
                "provider": "tiingo",
                "feed": "iex",
                "bar_size": "1min",
                "row_count": 0,
                "symbols": [],
                "min_timestamp": "2026-07-02T13:30:00Z",
                "max_timestamp": "2026-07-02T13:30:00Z",
                "quality": {"passed": False},
            }
        )


def test_manifest_rejects_inverted_timestamp_range() -> None:
    with pytest.raises(ValidationError, match="min_timestamp must not exceed max_timestamp"):
        DatasetManifest(
            dataset_id="tiingo-iex-minute-20260702",
            schema_version="1.0.0",
            source_uri="file:///data.tar.gz",
            source_sha256="a" * 64,
            content_sha256="b" * 64,
            code_revision="2d48ada",
            calendar_name="XNYS",
            calendar_version="2026a",
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
            provider="tiingo",
            feed="iex",
            bar_size="1min",
            row_count=0,
            symbols=(),
            min_timestamp=datetime(2026, 7, 2, 13, 31, tzinfo=UTC),
            max_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
            quality=DatasetQuality(passed=False),
        )


def test_quality_forbids_extra_fields_and_negative_counts() -> None:
    with pytest.raises(ValidationError):
        DatasetQuality(passed=True, duplicate_rows=-1)

    with pytest.raises(ValidationError):
        DatasetQuality.model_validate({"passed": True, "unexpected": 1})


def test_manifest_json_round_trip_is_immutable() -> None:
    manifest = DatasetManifest(
        dataset_id="tiingo-iex-minute-20260702",
        schema_version="1.0.0",
        source_uri="file:///G:/quant-agent-team-us/data/us_stock_data.tar.gz",
        source_sha256="a" * 64,
        content_sha256="b" * 64,
        code_revision="2d48ada",
        calendar_name="XNYS",
        calendar_version="2026a",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        provider="tiingo",
        feed="iex",
        bar_size="1min",
        row_count=1,
        symbols=("SPY",),
        min_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        max_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        quality=DatasetQuality(passed=True),
    )

    restored = DatasetManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    with pytest.raises(ValidationError):
        manifest.row_count = 2
