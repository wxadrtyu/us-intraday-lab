"""Acquire the frozen TwelveData final interval without reading strategy data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

CHUNK_SIZE = 8 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_existing(
    destination: Path,
    manifest_path: Path,
    *,
    source_url: str,
    period: str,
) -> dict[str, Any]:
    if destination.exists() != manifest_path.exists():
        raise ValueError("final file and acquisition manifest must exist together")
    if not destination.exists():
        raise FileNotFoundError(destination)
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0.0":
        raise ValueError("unsupported acquisition manifest schema")
    if manifest.get("source_url") != source_url or manifest.get("period") != period:
        raise ValueError("existing final acquisition scope mismatch")
    if manifest.get("file_size_bytes") != destination.stat().st_size:
        raise ValueError("existing final file size mismatch")
    if manifest.get("file_sha256") != _sha256(destination):
        raise ValueError("existing final file hash mismatch")
    return manifest


def _stream_copy(source: BinaryIO, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        while chunk := source.read(CHUNK_SIZE):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest(), size


def acquire(proposal_path: Path) -> dict[str, Any]:
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    sealed = proposal["sealed_final"]
    source_url = str(sealed["source_url"])
    period = str(sealed["period"])
    destination = Path(sealed["local_file"]).resolve()
    manifest_path = destination.with_suffix(".manifest.json")
    if destination.exists() or manifest_path.exists():
        return validate_existing(
            destination,
            manifest_path,
            source_url=source_url,
            period=period,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"stale partial acquisition requires inspection: {partial}")
    expected_url = (
        "https://huggingface.co/datasets/twelvedata/financial-world-model/"
        "resolve/main/bars_1min/test.parquet"
    )
    if source_url != expected_url:
        raise ValueError("sealed final source is outside the frozen Hugging Face object")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import hf_hub_download

    try:
        cached = Path(
            hf_hub_download(
                repo_id="twelvedata/financial-world-model",
                repo_type="dataset",
                filename="bars_1min/test.parquet",
                revision="main",
                cache_dir=destination.parent.parent / ".hf-cache",
            )
        ).resolve()
        with cached.open("rb") as source:
            file_sha256, file_size = _stream_copy(source, partial)
        partial.replace(destination)
        manifest: dict[str, Any] = {
            "schema_version": "1.0.0",
            "source_url": source_url,
            "repository_id": "twelvedata/financial-world-model",
            "repository_type": "dataset",
            "revision": "main",
            "repository_file": "bars_1min/test.parquet",
            "period": period,
            "local_file": destination.as_posix(),
            "file_sha256": file_sha256,
            "file_size_bytes": file_size,
            "downloaded_at": datetime.now(UTC).isoformat(),
        }
        _write_json(manifest_path, manifest)
        return validate_existing(
            destination,
            manifest_path,
            source_url=source_url,
            period=period,
        )
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True, type=Path)
    args = parser.parse_args()
    manifest = acquire(args.proposal.resolve())
    print(
        json.dumps(
            {
                "file_sha256": manifest["file_sha256"],
                "file_size_bytes": manifest["file_size_bytes"],
                "local_file": manifest["local_file"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
