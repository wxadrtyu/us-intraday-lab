import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).parents[2] / "scripts" / "seal_twelvedata_2025.py"
SPEC = importlib.util.spec_from_file_location("seal_twelvedata_2025", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_seal_filters_by_new_york_calendar_year_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "test.parquet"
    pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [
                    "2024-12-31 15:59:00-05:00",
                    "2025-01-02 09:30:00-05:00",
                    "2025-12-31 15:59:00-05:00",
                    "2026-01-02 09:30:00-05:00",
                ]
            ),
            "symbol": ["A", "A", "B", "A"],
            "close": [1.0, 2.0, 3.0, 4.0],
        }
    ).to_parquet(source, index=False)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    source_manifest = source.with_suffix(".manifest.json")
    source_manifest.write_text(
        json.dumps(
            {
                "source_url": "https://example.test/test.parquet",
                "file_sha256": source_hash,
                "file_size_bytes": source.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "test-2025.parquet"

    first = MODULE.seal(source, destination, source_manifest=source_manifest, minimum_sessions=2)
    second = MODULE.seal(source, destination, source_manifest=source_manifest, minimum_sessions=2)

    observed = pd.read_parquet(destination)
    assert first == second
    assert first["scope"]["years"] == [2025]
    assert len(observed) == 2
    assert observed["close"].tolist() == [2.0, 3.0]
