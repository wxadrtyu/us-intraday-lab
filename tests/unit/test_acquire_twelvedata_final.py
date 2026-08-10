import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "acquire_twelvedata_final.py"
SPEC = importlib.util.spec_from_file_location("acquire_twelvedata_final", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_validate_existing_accepts_exact_manifest(tmp_path: Path) -> None:
    destination = tmp_path / "test.parquet"
    destination.write_bytes(b"sealed bytes")
    manifest_path = destination.with_suffix(".manifest.json")
    manifest = {
        "schema_version": "1.0.0",
        "source_url": "https://example.test/test.parquet",
        "period": "2025",
        "local_file": destination.as_posix(),
        "file_sha256": hashlib.sha256(b"sealed bytes").hexdigest(),
        "file_size_bytes": len(b"sealed bytes"),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    observed = MODULE.validate_existing(
        destination,
        manifest_path,
        source_url=manifest["source_url"],
        period="2025",
    )

    assert observed == manifest


def test_validate_existing_rejects_mutated_final(tmp_path: Path) -> None:
    destination = tmp_path / "test.parquet"
    destination.write_bytes(b"mutated")
    manifest_path = destination.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "source_url": "https://example.test/test.parquet",
                "period": "2025",
                "file_sha256": "0" * 64,
                "file_size_bytes": len(b"mutated"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.validate_existing(
            destination,
            manifest_path,
            source_url="https://example.test/test.parquet",
            period="2025",
        )
