"""Seal an exact-2025 snapshot from the acquired upstream test object."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _scope(path: Path) -> dict[str, Any]:
    connection = duckdb.connect()
    row = connection.execute(
        """
        SELECT count(*) AS rows,
               count(DISTINCT CAST(timezone('America/New_York', datetime) AS DATE)) AS sessions,
               min(CAST(timezone('America/New_York', datetime) AS DATE)) AS first_date,
               max(CAST(timezone('America/New_York', datetime) AS DATE)) AS last_date,
               list_sort(list(DISTINCT date_part('year', timezone('America/New_York', datetime))))
                   AS years
        FROM read_parquet(?)
        """,
        [path.as_posix()],
    ).fetchone()
    connection.close()
    assert row is not None
    return {
        "rows": int(row[0]),
        "sessions": int(row[1]),
        "first_date": row[2].isoformat(),
        "last_date": row[3].isoformat(),
        "years": [int(value) for value in row[4]],
    }


def seal(
    source: Path,
    destination: Path,
    *,
    source_manifest: Path,
    minimum_sessions: int = 240,
    period: str = "2025",
    start_date: str = "2025-01-01",
    end_date: str = "2026-01-01",
) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    manifest_path = destination.with_suffix(".manifest.json")
    parent = json.loads(source_manifest.read_text(encoding="utf-8"))
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start >= end or not period:
        raise ValueError("snapshot period boundaries are invalid")
    filter_contract = (
        "CAST(timezone('America/New_York', datetime) AS DATE) "
        f">= DATE '{start.isoformat()}' AND "
        "CAST(timezone('America/New_York', datetime) AS DATE) "
        f"< DATE '{end.isoformat()}'"
    )
    if parent.get("file_size_bytes") != source.stat().st_size:
        raise ValueError("parent acquisition size mismatch")
    parent_hash = _sha256(source)
    if parent.get("file_sha256") != parent_hash:
        raise ValueError("parent acquisition hash mismatch")
    if destination.exists() or manifest_path.exists():
        if not destination.exists() or not manifest_path.exists():
            raise ValueError("snapshot and manifest must exist together")
        retained = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            retained.get("parent_file_sha256") != parent_hash
            or retained.get("period") != period
            or retained.get("file_size_bytes") != destination.stat().st_size
            or retained.get("file_sha256") != _sha256(destination)
        ):
            raise ValueError("retained 2025 snapshot provenance mismatch")
        return retained
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"stale snapshot partial requires inspection: {partial}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    source_sql = source.as_posix().replace("'", "''")
    partial_sql = partial.as_posix().replace("'", "''")
    try:
        connection.execute(
            f"""
            COPY (
                SELECT *
                FROM read_parquet('{source_sql}')
                WHERE CAST(timezone('America/New_York', datetime) AS DATE)
                          >= DATE '{start.isoformat()}'
                  AND CAST(timezone('America/New_York', datetime) AS DATE)
                          < DATE '{end.isoformat()}'
                ORDER BY datetime, symbol
            ) TO '{partial_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise
    finally:
        connection.close()
    scope = _scope(partial)
    if (
        date.fromisoformat(scope["first_date"]) < start
        or date.fromisoformat(scope["last_date"]) >= end
        or scope["sessions"] < minimum_sessions
    ):
        partial.unlink()
        raise ValueError("sealed snapshot does not exactly cover a viable 2025 interval")
    file_hash = _sha256(partial)
    file_size = partial.stat().st_size
    partial.replace(destination)
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_url": parent["source_url"],
        "period": period,
        "local_file": destination.as_posix(),
        "parent_file": source.as_posix(),
        "parent_file_sha256": parent_hash,
        "filter_contract": filter_contract,
        "sort_contract": ["datetime", "symbol"],
        "file_sha256": file_hash,
        "file_size_bytes": file_size,
        "scope": scope,
        "sealed_at": datetime.now(UTC).isoformat(),
    }
    _write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--period", default="2025")
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default="2026-01-01")
    parser.add_argument("--minimum-sessions", default=240, type=int)
    args = parser.parse_args()
    manifest = seal(
        args.source,
        args.destination,
        source_manifest=args.source_manifest,
        period=args.period,
        start_date=args.start_date,
        end_date=args.end_date,
        minimum_sessions=args.minimum_sessions,
    )
    print(
        json.dumps(
            {
                "file_sha256": manifest["file_sha256"],
                "file_size_bytes": manifest["file_size_bytes"],
                "scope": manifest["scope"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
