"""Build the strict USPTO patent-grant snapshot for frozen training."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pandas as pd

from us_intraday_lab.data.sec_fundamental_filings import parse_ticker_map
from us_intraday_lab.data.uspto_patent_grants import (
    build_issuer_map,
    normalize_grants,
    verify_archive,
)

PATENT_MEMBER = "g_patent.tsv"
ASSIGNEE_MEMBER = "g_assignee_not_disambiguated.tsv"


def _chunks(
    archive_path: Path,
    member: str,
    columns: list[str],
):
    with zipfile.ZipFile(archive_path) as archive:
        if member not in archive.namelist():
            raise RuntimeError(f"USPTO_ARCHIVE_MEMBER_MISSING:{member}")
        with archive.open(member) as source:
            yield from pd.read_csv(
                source,
                sep="\t",
                usecols=columns,
                dtype="string",
                chunksize=500_000,
                keep_default_na=False,
            )


def _write_parquet_immutable(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    try:
        if path.exists():
            if path.read_bytes() != temporary.read_bytes():
                raise RuntimeError(f"USPTO_SNAPSHOT_IMMUTABLE_COLLISION:{path.name}")
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_immutable(path: Path, payload: dict[str, object]) -> None:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if path.exists():
        if path.read_bytes() != body:
            raise RuntimeError(f"USPTO_SNAPSHOT_IMMUTABLE_COLLISION:{path.name}")
    else:
        path.write_bytes(body)


def build_snapshot(
    patent_archive: Path,
    assignee_archive: Path,
    sec_identities: pd.DataFrame,
    root: Path,
    expected_patent_md5: str,
    expected_assignee_md5: str,
    sec_unmatched: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Verify, normalize, and atomically publish the training snapshot."""
    sources = [
        verify_archive(patent_archive, expected_patent_md5),
        verify_archive(assignee_archive, expected_assignee_md5),
    ]
    patent_parts: list[pd.DataFrame] = []
    for chunk in _chunks(
        patent_archive,
        PATENT_MEMBER,
        ["patent_id", "patent_type", "patent_date", "patent_title"],
    ):
        dates = pd.to_datetime(chunk["patent_date"], errors="coerce")
        patent_parts.append(
            chunk.loc[dates.between("2021-01-01", "2023-12-31")].copy()
        )
    patents = pd.concat(patent_parts, ignore_index=True)

    names: set[str] = set()
    for chunk in _chunks(
        assignee_archive,
        ASSIGNEE_MEMBER,
        ["assignee_organization"],
    ):
        names.update(
            value.strip()
            for value in chunk["assignee_organization"].astype(str)
        )
    unique_assignees = pd.DataFrame(
        {"assignee_organization": sorted(names)}
    )
    issuer_map, mapping_rejections = build_issuer_map(
        sec_identities, unique_assignees
    )
    mapped_names = set(issuer_map["raw_assignee_name"].astype(str))
    patent_ids = set(patents["patent_id"].astype(str))
    assignee_parts: list[pd.DataFrame] = []
    for chunk in _chunks(
        assignee_archive,
        ASSIGNEE_MEMBER,
        ["patent_id", "assignee_sequence", "assignee_organization"],
    ):
        selected = chunk["patent_id"].astype(str).isin(patent_ids) & chunk[
            "assignee_organization"
        ].astype(str).str.strip().isin(mapped_names)
        assignee_parts.append(chunk.loc[selected].copy())
    assignments = pd.concat(assignee_parts, ignore_index=True)
    grants, grant_rejections = normalize_grants(patents, assignments, issuer_map)
    rejections = pd.concat(
        [
            mapping_rejections.assign(patent_id=pd.NA, assignee_sequence=pd.NA),
            grant_rejections.rename(
                columns={"assignee_organization": "raw_assignee_name"}
            ).assign(issuer_key=pd.NA),
        ],
        ignore_index=True,
        sort=False,
    )
    rejections = rejections[
        [
            "patent_id",
            "assignee_sequence",
            "raw_assignee_name",
            "issuer_key",
            "reason",
        ]
    ]

    root.mkdir(parents=True, exist_ok=True)
    if sec_unmatched is None:
        sec_unmatched = pd.DataFrame(columns=["symbol", "coverage_reason"])
    if sec_unmatched["symbol"].duplicated().any():
        raise ValueError("USPTO_SEC_UNMATCHED_DUPLICATE")
    snapshot_path = root / "uspto_patent_grant_training_v1.parquet"
    map_path = root / "issuer_map.parquet"
    rejection_path = root / "rejections.parquet"
    unmatched_path = root / "sec_unmatched.parquet"
    _write_parquet_immutable(snapshot_path, grants)
    _write_parquet_immutable(map_path, issuer_map)
    _write_parquet_immutable(rejection_path, rejections)
    _write_parquet_immutable(unmatched_path, sec_unmatched)
    manifest = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "training_only": True,
        "source_hashes_verified": True,
        "sources": sources,
        "requested_symbols": int(sec_identities["symbol"].nunique()) + len(sec_unmatched),
        "sec_unmatched_symbols": len(sec_unmatched),
        "mapped_symbols": int(grants["symbol"].nunique()),
        "mapped_issuers": int(issuer_map["issuer_key"].nunique()),
        "qualifying_symbol_patents": len(
            grants[["symbol", "patent_id"]].drop_duplicates()
        ),
        "training_years": sorted(
            pd.to_datetime(grants["patent_date"]).dt.year.unique().tolist()
        ),
        "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "issuer_map_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
        "rejections_sha256": hashlib.sha256(rejection_path.read_bytes()).hexdigest(),
        "sec_unmatched_sha256": hashlib.sha256(unmatched_path.read_bytes()).hexdigest(),
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    _write_json_immutable(root / "manifest.json", manifest)
    return grants, issuer_map, rejections, manifest


def _parse_sec_identities(
    path: Path, symbols: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched, missing = parse_ticker_map(path.read_bytes(), symbols)
    return matched.rename(columns={"name": "title"}), missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--ticker-map", required=True, type=Path)
    parser.add_argument("--patent-archive", required=True, type=Path)
    parser.add_argument("--assignee-archive", required=True, type=Path)
    parser.add_argument("--expected-patent-md5", required=True)
    parser.add_argument("--expected-assignee-md5", required=True)
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    symbols = set(
        pd.read_parquet(arguments.events, columns=["symbol"])["symbol"].astype(str)
    )
    identities, missing = _parse_sec_identities(arguments.ticker_map, symbols)
    _grants, _mapping, _rejections, manifest = build_snapshot(
        arguments.patent_archive,
        arguments.assignee_archive,
        identities,
        arguments.root,
        arguments.expected_patent_md5,
        arguments.expected_assignee_md5,
        sec_unmatched=missing,
    )
    print(json.dumps(manifest, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
