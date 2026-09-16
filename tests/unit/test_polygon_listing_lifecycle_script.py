from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import audit_polygon_listing_lifecycle as script


def _manifest(tmp_path: Path, *, permitted: bool) -> dict[str, object]:
    mapping = tmp_path / "mapping.parquet"
    exceptions = tmp_path / "exceptions.parquet"
    mapping.write_bytes(b"mapping")
    exceptions.write_bytes(b"exceptions")
    return {
        "schema_version": "1.0.0",
        "dataset_id": "polygon-listing-lifecycle-v1-test",
        "mapping_path": str(mapping),
        "exceptions_path": str(exceptions),
        "mapping_sha256": "a" * 64,
        "exceptions_sha256": "b" * 64,
        "historical_master_validation_report_sha256": "c" * 64,
        "universe_dataset_id": "universe-test",
        "universe_sha256": "d" * 64,
        "eligible_rows": 2,
        "mapped_rows": 2 if permitted else 1,
        "exception_rows": 0 if permitted else 1,
        "coverage_ratio": 1.0 if permitted else 0.5,
        "exception_reason_counts": {} if permitted else {"UNMATCHED": 1},
        "source_normalization_collision_rows": 0,
        "provider_splicing": "FORBIDDEN",
        "order_route": "FORBIDDEN",
        "strategy_evaluation_permitted": permitted,
        "paper_activation": False,
        "rejection_reasons": [] if permitted else ["BLOCKED_LIFECYCLE_COVERAGE"],
    }


def test_markdown_states_gate_and_no_paper(tmp_path: Path) -> None:
    markdown = script.render_markdown(_manifest(tmp_path, permitted=False))

    assert "Strategy evaluation permitted: **NO**" in markdown
    assert "Coverage: 1 / 2 (50.000000%)" in markdown
    assert "Provider splicing: FORBIDDEN" in markdown
    assert "Paper activation: false" in markdown


@pytest.mark.parametrize(("permitted", "exit_code"), [(True, 0), (False, 2)])
def test_main_writes_immutable_outputs_and_exits_by_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    permitted: bool,
    exit_code: int,
) -> None:
    output_json = tmp_path / "audit.json"
    output_md = tmp_path / "audit.md"
    manifest = _manifest(tmp_path, permitted=permitted)
    monkeypatch.setattr(script, "publish_lifecycle_catalog", lambda **_kwargs: manifest)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_polygon_listing_lifecycle.py",
            "--root",
            str(tmp_path),
            "--historical-master-audit",
            str(tmp_path / "master.json"),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )

    with pytest.raises(SystemExit) as result:
        script.main()

    assert result.value.code == exit_code
    assert json.loads(output_json.read_text("utf-8"))["dataset_id"] == manifest[
        "dataset_id"
    ]
    assert "Paper activation: false" in output_md.read_text("utf-8")
