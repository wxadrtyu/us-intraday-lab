from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit_polygon_historical_master import _write_immutable, compare_symbols


def test_immutable_writer_reuses_identical_and_rejects_collision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "result.json"

    _write_immutable(path, "same\n")
    _write_immutable(path, "same\n")

    with pytest.raises(ValueError, match="immutable audit collision"):
        _write_immutable(path, "different\n")


def test_cross_source_comparison_preserves_unmatched_symbols() -> None:
    result = compare_symbols(
        polygon={"AAA", "OLD"},
        alpaca={"AAA", "NEW"},
        decisions={"AAA", "NEW"},
    )

    assert result == {
        "alpaca_asset_symbols_not_in_polygon": ["NEW"],
        "polygon_symbols_not_in_alpaca_assets": ["OLD"],
        "decision_symbols_not_in_polygon": ["NEW"],
        "polygon_symbols": 2,
        "alpaca_asset_symbols": 2,
        "decision_symbols": 2,
    }


def test_cross_source_comparison_normalizes_case_and_whitespace() -> None:
    result = compare_symbols(
        polygon={"aaa", " BBB "}, alpaca={"AAA", "BBB"}, decisions={"aaa"}
    )

    assert result["alpaca_asset_symbols_not_in_polygon"] == []
    assert result["polygon_symbols_not_in_alpaca_assets"] == []
    assert result["decision_symbols_not_in_polygon"] == []
