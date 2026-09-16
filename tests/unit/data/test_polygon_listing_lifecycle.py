from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.polygon_listing_lifecycle import (
    build_lifecycle_coverage,
    derive_lifecycle_history,
    lifecycle_bucket,
    normalize_ticker,
    publish_lifecycle_catalog,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_snapshot(
    root: Path, asof: date, rows: list[tuple[str, bool]]
) -> None:
    directory = (
        root
        / "data"
        / "staging"
        / "polygon_reference_tickers_v1"
        / "snapshots"
        / f"asof={asof.isoformat()}"
    )
    directory.mkdir(parents=True)
    frame = pd.DataFrame(
        {
            "ticker": [row[0] for row in rows],
            "active": [row[1] for row in rows],
            "asof": [asof] * len(rows),
        }
    )
    parquet = directory / "tickers.parquet"
    frame.to_parquet(parquet, index=False)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "source_namespace": "polygon_reference_tickers_v1",
                "provider": "polygon",
                "asof": asof.isoformat(),
                "row_count": len(frame),
                "content_sha256": _sha256(parquet),
                "missing_data_policy": "preserve_nulls_no_fill_no_inference",
                "provider_splicing": "FORBIDDEN",
            }
        ),
        encoding="utf-8",
    )


def _validation(path: Path) -> Path:
    validation = path / "validation.json"
    validation.write_text("{}", encoding="utf-8")
    return validation


def _write_decisions(
    root: Path, rows: list[tuple[str, date, bool, date]]
) -> None:
    directory = (
        root
        / "data"
        / "catalog"
        / "monthly_universe_sip_v2"
        / "test-universe"
    )
    directory.mkdir(parents=True)
    decisions = pd.DataFrame(
        rows, columns=["symbol", "month", "eligible", "information_cutoff"]
    )
    path = directory / "decisions.parquet"
    decisions.to_parquet(path, index=False)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "test-universe",
                "start_month": "2018-04-01",
                "end_month": "2026-03-01",
                "content_sha256": _sha256(path),
            }
        ),
        encoding="utf-8",
    )


def _trust_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "us_intraday_lab.data.polygon_listing_lifecycle."
        "load_historical_master_validation",
        lambda _path: {"validation_report_sha256": "a" * 64},
    )


def test_normalize_ticker_is_ascii_uppercase() -> None:
    assert normalize_ticker(" brk.b ") == "BRK.B"
    with pytest.raises(ValueError, match="LIFECYCLE_TICKER_NOT_ASCII"):
        normalize_ticker("Ａ")


@pytest.mark.parametrize(
    ("tenure", "left_censored", "expected"),
    [
        (0, False, "new_0_3"),
        (3, False, "new_0_3"),
        (4, False, "young_4_12"),
        (12, False, "young_4_12"),
        (13, False, "maturing_13_36"),
        (36, False, "maturing_13_36"),
        (37, False, "seasoned_37_plus"),
        (0, True, "left_censored"),
    ],
)
def test_lifecycle_bucket_boundaries(
    tenure: int, left_censored: bool, expected: str
) -> None:
    assert lifecycle_bucket(tenure=tenure, left_censored=left_censored) == expected


def test_derives_only_observed_monthly_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 1, 31), [("OLD", True), ("RE", False)])
    _write_snapshot(
        tmp_path,
        date(2018, 2, 28),
        [("OLD", True), ("NEW", True), ("RE", True)],
    )
    _write_snapshot(
        tmp_path,
        date(2018, 3, 31),
        [("OLD", True), ("NEW", True), ("RE", True)],
    )

    frame, lineage = derive_lifecycle_history(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    march = frame.loc[frame["snapshot_asof"].eq(date(2018, 3, 31))].set_index(
        "ticker"
    )
    assert bool(march.loc["OLD", "left_censored"])
    assert march.loc["OLD", "lifecycle_bucket"] == "left_censored"
    assert march.loc["NEW", "active_tenure_months"] == 1
    assert march.loc["NEW", "lifecycle_bucket"] == "new_0_3"
    assert not bool(march.loc["RE", "reactivated_this_month"])
    february_re = frame.loc[
        frame["snapshot_asof"].eq(date(2018, 2, 28)) & frame["ticker"].eq("RE")
    ].iloc[0]
    assert bool(february_re["reactivated_this_month"])
    assert len(lineage) == 3


def test_missing_previous_ticker_is_not_reactivation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 1, 31), [("A", True)])
    _write_snapshot(tmp_path, date(2018, 2, 28), [("A", True), ("B", True)])

    frame, _ = derive_lifecycle_history(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    row = frame.loc[frame["ticker"].eq("B")].iloc[0]
    assert not bool(row["reactivated_this_month"])


def test_rejects_normalization_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 1, 31), [("abc", True), ("ABC", False)])

    with pytest.raises(ValueError, match="LIFECYCLE_NORMALIZATION_COLLISION"):
        derive_lifecycle_history(root=tmp_path, validation_path=_validation(tmp_path))


def test_rejects_snapshot_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 1, 31), [("A", True)])
    manifest = next(tmp_path.rglob("manifest.json"))
    payload = json.loads(manifest.read_text("utf-8"))
    payload["content_sha256"] = "f" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="LIFECYCLE_SNAPSHOT_HASH_MISMATCH"):
        derive_lifecycle_history(root=tmp_path, validation_path=_validation(tmp_path))


def test_coverage_uses_latest_snapshot_strictly_before_first_xnys_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("A", True), ("B", True)])
    _write_snapshot(tmp_path, date(2019, 1, 31), [("A", True), ("B", False)])
    _write_decisions(
        tmp_path,
        [
            ("A", date(2019, 1, 1), True, date(2018, 12, 31)),
            ("B", date(2019, 1, 1), True, date(2018, 12, 31)),
        ],
    )

    mapping, audit = build_lifecycle_coverage(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    assert set(mapping["snapshot_asof"]) == {date(2018, 12, 31)}
    assert audit["coverage_ratio"] == 1.0
    assert audit["eligible_rows"] == 2
    assert audit["mapped_rows"] == 2
    assert audit["exception_rows"] == 0
    assert audit["strategy_evaluation_permitted"] is True


def test_one_unmatched_symbol_blocks_entire_campaign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("A", True)])
    _write_decisions(
        tmp_path,
        [
            ("A", date(2019, 1, 1), True, date(2018, 12, 31)),
            ("MISSING", date(2019, 1, 1), True, date(2018, 12, 31)),
            ("IGNORED", date(2019, 1, 1), False, date(2018, 12, 31)),
        ],
    )

    mapping, audit = build_lifecycle_coverage(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    assert list(mapping["symbol"]) == ["A"]
    assert audit["strategy_evaluation_permitted"] is False
    assert audit["rejection_reasons"] == ["BLOCKED_LIFECYCLE_COVERAGE"]
    assert audit["eligible_rows"] == 2
    assert audit["mapped_rows"] == 1
    assert audit["exception_rows"] == 1
    assert audit["exceptions"] == [
        {"month": "2019-01-01", "symbol": "MISSING", "reason": "UNMATCHED"}
    ]


def test_inactive_polygon_record_is_missing_lifecycle_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("A", False)])
    _write_decisions(
        tmp_path,
        [("A", date(2019, 1, 1), True, date(2018, 12, 31))],
    )

    mapping, audit = build_lifecycle_coverage(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    assert mapping.empty
    assert audit["exceptions"][0]["reason"] == "MISSING_LIFECYCLE_STATE"


def test_decision_normalization_collision_blocks_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("ABC", True)])
    _write_decisions(
        tmp_path,
        [
            ("abc", date(2019, 1, 1), True, date(2018, 12, 31)),
            ("ABC", date(2019, 1, 1), True, date(2018, 12, 31)),
        ],
    )

    mapping, audit = build_lifecycle_coverage(
        root=tmp_path, validation_path=_validation(tmp_path)
    )

    assert mapping.empty
    assert {row["reason"] for row in audit["exceptions"]} == {
        "NORMALIZATION_COLLISION"
    }


def test_publish_is_hash_addressed_and_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("A", True)])
    _write_decisions(
        tmp_path,
        [("A", date(2019, 1, 1), True, date(2018, 12, 31))],
    )
    validation = _validation(tmp_path)

    first = publish_lifecycle_catalog(root=tmp_path, validation_path=validation)
    second = publish_lifecycle_catalog(root=tmp_path, validation_path=validation)

    assert first == second
    assert str(first["dataset_id"]).startswith("polygon-listing-lifecycle-v1-")
    assert _sha256(Path(str(first["mapping_path"]))) == first["mapping_sha256"]
    assert _sha256(Path(str(first["exceptions_path"]))) == first["exceptions_sha256"]
    assert first["strategy_evaluation_permitted"] is True


def test_publish_rejects_existing_content_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trust_validation(monkeypatch)
    _write_snapshot(tmp_path, date(2018, 12, 31), [("A", True)])
    _write_decisions(
        tmp_path,
        [("A", date(2019, 1, 1), True, date(2018, 12, 31))],
    )
    validation = _validation(tmp_path)
    manifest = publish_lifecycle_catalog(root=tmp_path, validation_path=validation)
    Path(str(manifest["mapping_path"])).write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="LIFECYCLE_CATALOG_COLLISION"):
        publish_lifecycle_catalog(root=tmp_path, validation_path=validation)
