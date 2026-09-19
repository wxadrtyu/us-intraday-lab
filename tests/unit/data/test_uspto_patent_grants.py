from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_uspto_patent_grant_training_snapshot import (
    _parse_sec_identities,
    _training_symbols,
    build_snapshot,
)
from us_intraday_lab.data.uspto_patent_grants import (
    build_issuer_map,
    canonicalize_organization,
    normalize_grants,
    verify_archive,
)


def test_canonicalization_is_mechanical_and_suffix_limited() -> None:
    assert canonicalize_organization("Acme, Inc.") == "ACME"
    assert canonicalize_organization("A.C.M.E. Holdings") == "A C M E HOLDINGS"


def test_parser_uses_frozen_sec_name_and_retains_unmatched(tmp_path: Path) -> None:
    source = tmp_path / "company_tickers_exchange.json"
    source.write_text(
        json.dumps(
            {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[123, "Acme Incorporated", "AAA", "Nasdaq"]],
            }
        ),
        encoding="utf-8",
    )
    identities, missing = _parse_sec_identities(source, {"AAA", "BBB"})
    assert identities[["symbol", "title"]].to_dict("records") == [
        {"symbol": "AAA", "title": "Acme Incorporated"}
    ]
    assert missing["symbol"].tolist() == ["BBB"]


def test_training_symbols_exclude_later_event_cube_periods(tmp_path: Path) -> None:
    events = tmp_path / "events.parquet"
    pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "session_date": ["2021-01-04", "2023-12-29", "2024-01-02"],
        }
    ).to_parquet(events, index=False)
    assert _training_symbols(events) == {"AAA", "BBB"}


def test_mapping_accepts_unique_key() -> None:
    identities = pd.DataFrame(
        {"symbol": ["AAA"], "title": ["Acme Incorporated"]}
    )
    assignees = pd.DataFrame({"assignee_organization": ["Acme Inc"]})

    mapping, rejected = build_issuer_map(identities, assignees)

    assert mapping.loc[0, "raw_assignee_name"] == "Acme Inc"
    assert mapping.loc[0, "symbol"] == "AAA"
    assert rejected.empty


def test_mapping_preserves_ambiguous_sec_key() -> None:
    identities = pd.DataFrame(
        {
            "symbol": ["AAA", "AAB"],
            "title": ["Acme Incorporated", "Acme Corporation"],
        }
    )
    assignees = pd.DataFrame({"assignee_organization": ["Acme Inc"]})

    mapping, rejected = build_issuer_map(identities, assignees)

    assert mapping.empty
    assert set(rejected["reason"]) == {"USPTO_SEC_ISSUER_KEY_AMBIGUOUS"}


def test_archive_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"patent-data")

    with pytest.raises(RuntimeError, match="USPTO_ARCHIVE_MD5_MISMATCH"):
        verify_archive(archive, "0" * 32)


def test_normalizer_joins_exact_patent_and_assignee() -> None:
    patents = pd.DataFrame(
        {
            "patent_id": ["1", "2"],
            "patent_type": ["utility", "utility"],
            "patent_date": ["2022-01-04", "2020-01-07"],
            "patent_title": ["Useful thing", "Old thing"],
        }
    )
    assignees = pd.DataFrame(
        {
            "patent_id": ["1", "1", "2", "3"],
            "assignee_sequence": [0, 1, 0, 0],
            "assignee_organization": [
                "Acme Inc",
                "Unknown LLC",
                "Acme Inc",
                "Unknown LLC",
            ],
        }
    )
    issuer_map = pd.DataFrame(
        {
            "raw_assignee_name": ["Acme Inc"],
            "issuer_key": ["ACME"],
            "symbol": ["AAA"],
            "sec_title": ["Acme Incorporated"],
        }
    )

    grants, rejected = normalize_grants(patents, assignees, issuer_map)

    assert grants[["symbol", "patent_id"]].to_dict("records") == [
        {"symbol": "AAA", "patent_id": "1"}
    ]
    assert set(rejected["reason"]) == {
        "USPTO_ASSIGNEE_UNMAPPED",
        "USPTO_PATENT_ID_UNMATCHED",
    }


def test_conflicting_patent_metadata_fails_closed() -> None:
    patents = pd.DataFrame(
        {
            "patent_id": ["1", "1"],
            "patent_type": ["utility", "design"],
            "patent_date": ["2022-01-04", "2022-01-04"],
            "patent_title": ["Useful thing", "Useful thing"],
        }
    )
    assignees = pd.DataFrame(
        {
            "patent_id": ["1"],
            "assignee_sequence": [0],
            "assignee_organization": ["Acme Inc"],
        }
    )
    issuer_map = pd.DataFrame(
        {
            "raw_assignee_name": ["Acme Inc"],
            "issuer_key": ["ACME"],
            "symbol": ["AAA"],
            "sec_title": ["Acme Incorporated"],
        }
    )

    with pytest.raises(ValueError, match="USPTO_PATENT_METADATA_CONFLICT"):
        normalize_grants(patents, assignees, issuer_map)


def _write_zip(path: Path, member: str, body: str) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, body)
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def test_snapshot_verifies_archives_and_resumes_identical_output(tmp_path: Path) -> None:
    patent_archive = tmp_path / "g_patent.tsv.zip"
    patent_md5 = _write_zip(
        patent_archive,
        "g_patent.tsv",
        "patent_id\tpatent_type\tpatent_date\tpatent_title\n"
        "1\tutility\t2022-01-04\tUseful thing\n",
    )
    assignee_archive = tmp_path / "g_assignee_not_disambiguated.tsv.zip"
    assignee_md5 = _write_zip(
        assignee_archive,
        "g_assignee_not_disambiguated.tsv",
        "patent_id\tassignee_sequence\tassignee_organization\n"
        "1\t0\tAcme Inc\n",
    )
    identities = pd.DataFrame(
        {"symbol": ["AAA"], "title": ["Acme Incorporated"]}
    )
    root = tmp_path / "output"

    first = build_snapshot(
        patent_archive,
        assignee_archive,
        identities,
        root,
        patent_md5,
        assignee_md5,
        source_fingerprints={"event_cube_sha256": "a" * 64, "sec_ticker_sha256": "b" * 64},
    )
    second = build_snapshot(
        patent_archive,
        assignee_archive,
        identities,
        root,
        patent_md5,
        assignee_md5,
        source_fingerprints={"event_cube_sha256": "a" * 64, "sec_ticker_sha256": "b" * 64},
    )

    assert first[0][["symbol", "patent_id"]].to_dict("records") == [
        {"symbol": "AAA", "patent_id": "1"}
    ]
    assert first[3]["status"] == "COMPLETE"
    assert first[3]["source_hashes_verified"] is True
    assert first[3]["source_fingerprints"] == {
        "event_cube_sha256": "a" * 64,
        "sec_ticker_sha256": "b" * 64,
    }
    assert second[0].equals(first[0])
    assert second[3] == first[3]


def test_snapshot_preserves_sec_unmatched_inventory(tmp_path: Path) -> None:
    patent_archive = tmp_path / "g_patent.tsv.zip"
    patent_md5 = _write_zip(
        patent_archive,
        "g_patent.tsv",
        "patent_id\tpatent_type\tpatent_date\tpatent_title\n"
        "1\tutility\t2022-01-04\tUseful thing\n",
    )
    assignee_archive = tmp_path / "g_assignee_not_disambiguated.tsv.zip"
    assignee_md5 = _write_zip(
        assignee_archive,
        "g_assignee_not_disambiguated.tsv",
        "patent_id\tassignee_sequence\tassignee_organization\n"
        "1\t0\tAcme Inc\n",
    )
    root = tmp_path / "output"
    _grants, _mapping, _rejected, manifest = build_snapshot(
        patent_archive,
        assignee_archive,
        pd.DataFrame({"symbol": ["AAA"], "title": ["Acme Incorporated"]}),
        root,
        patent_md5,
        assignee_md5,
        sec_unmatched=pd.DataFrame(
            {"symbol": ["BBB"], "coverage_reason": ["SEC_IDENTITY_UNAVAILABLE"]}
        ),
    )
    assert manifest["requested_symbols"] == 2
    assert manifest["sec_unmatched_symbols"] == 1
    assert pd.read_parquet(root / "sec_unmatched.parquet")["symbol"].tolist() == [
        "BBB"
    ]


def test_snapshot_rejects_invalid_source_grant_date_before_filter(tmp_path: Path) -> None:
    patent_archive = tmp_path / "g_patent.tsv.zip"
    patent_md5 = _write_zip(
        patent_archive,
        "g_patent.tsv",
        "patent_id\tpatent_type\tpatent_date\tpatent_title\n"
        "1\tutility\t2022-99-04\tUseful thing\n",
    )
    assignee_archive = tmp_path / "g_assignee_not_disambiguated.tsv.zip"
    assignee_md5 = _write_zip(
        assignee_archive,
        "g_assignee_not_disambiguated.tsv",
        "patent_id\tassignee_sequence\tassignee_organization\n"
        "1\t0\tAcme Inc\n",
    )
    with pytest.raises(ValueError, match="USPTO_PATENT_DATE_INVALID"):
        build_snapshot(
            patent_archive,
            assignee_archive,
            pd.DataFrame({"symbol": ["AAA"], "title": ["Acme Incorporated"]}),
            tmp_path / "output",
            patent_md5,
            assignee_md5,
        )
