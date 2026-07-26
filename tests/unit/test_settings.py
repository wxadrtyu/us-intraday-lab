from pathlib import Path

from us_intraday_lab.settings import LabPaths


def test_lab_paths_stay_under_configured_root(tmp_path: Path) -> None:
    paths = LabPaths.from_root(tmp_path)

    assert paths.raw == tmp_path / "data" / "raw"
    assert paths.canonical == tmp_path / "data" / "lake" / "canonical"
    assert paths.catalog == tmp_path / "data" / "catalog" / "research.duckdb"
    assert paths.manifests == tmp_path / "data" / "manifests"
