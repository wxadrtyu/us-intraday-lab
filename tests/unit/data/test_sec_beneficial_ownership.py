from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from scripts.build_sec_beneficial_ownership_training_features import (
    build_feature_cache,
)
from scripts.build_sec_beneficial_ownership_training_snapshot import build_snapshot
from us_intraday_lab.data.sec_beneficial_ownership import (
    build_event_features,
    normalize_filings,
)


def _recent(forms: list[str], accessions: list[str] | None = None) -> dict[str, list[object]]:
    count = len(forms)
    return {
        "accessionNumber": accessions or [f"acc-{index}" for index in range(count)],
        "filingDate": ["2022-02-01"] * count,
        "reportDate": ["2022-01-31"] * count,
        "acceptanceDateTime": ["2022-02-01T16:30:00.000Z"] * count,
        "form": forms,
        "items": [""] * count,
        "size": [1000] * count,
        "primaryDocument": ["ownership.htm"] * count,
    }


def test_normalizer_accepts_only_exact_schedule_forms() -> None:
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    responses = [
        (
            "source",
            1,
            _recent(["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "13F-HR"]),
        )
    ]

    filings, rejected = normalize_filings(responses, identities)

    assert set(filings["form"]) == {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}
    assert rejected.loc[rejected["form"].eq("13F-HR"), "reason"].tolist() == [
        "SEC_BENEFICIAL_FORM_NOT_QUALIFYING"
    ]


def test_normalizer_preserves_shared_cik_and_unmatched_cik() -> None:
    identities = pd.DataFrame({"symbol": ["AAA", "AAB"], "cik": [1, 1]})
    responses = [
        ("matched", 1, _recent(["SC 13D"])),
        ("unmatched", 2, _recent(["SC 13G"])),
    ]

    filings, rejected = normalize_filings(responses, identities)

    assert filings["symbol"].tolist() == ["AAA", "AAB"]
    assert rejected.loc[rejected["source"].eq("unmatched"), "reason"].tolist() == [
        "SEC_BENEFICIAL_CIK_UNMATCHED"
    ]


def test_conflicting_accession_fails_closed() -> None:
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    responses = [
        ("first", 1, _recent(["SC 13D"], ["same"])),
        ("second", 1, _recent(["SC 13G"], ["same"])),
    ]

    with pytest.raises(ValueError, match="SEC_BENEFICIAL_ACCESSION_CONFLICT"):
        normalize_filings(responses, identities)


def _source_manifest(tmp_path) -> dict[str, object]:
    current = {
        "cik": "1",
        "filings": {"recent": _recent(["SC 13D"]), "files": []},
    }
    historical = _recent(["SC 13G/A"], ["historical"])
    sources = []
    for filename, payload in (
        ("CIK0000000001.json", current),
        ("CIK0000000001-submissions-001.json", historical),
    ):
        path = tmp_path / filename
        body = json.dumps(payload).encode()
        path.write_bytes(body)
        sources.append(
            {
                "url": f"https://data.sec.gov/submissions/{filename}",
                "raw_path": str(path),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    return {
        "status": "COMPLETE",
        "required_sources_complete": True,
        "unmatched_symbols": ["QQQ"],
        "sources": sources,
    }


def test_snapshot_verifies_sources_and_resumes_immutable_outputs(tmp_path) -> None:
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    source_manifest = _source_manifest(tmp_path)
    root = tmp_path / "output"

    first = build_snapshot(source_manifest, identities, root)
    second = build_snapshot(source_manifest, identities, root)

    assert set(first[0]["accession_number"]) == {"acc-0", "historical"}
    assert first[2]["status"] == "COMPLETE"
    assert first[2]["source_hashes_verified"] is True
    assert first[2]["unmatched_symbols"] == ["QQQ"]
    assert second[0].equals(first[0])
    assert second[1].equals(first[1])
    assert second[2] == first[2]


def test_snapshot_rejects_source_hash_mismatch(tmp_path) -> None:
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    source_manifest = _source_manifest(tmp_path)
    path = tmp_path / "CIK0000000001.json"
    path.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="SEC_BENEFICIAL_SOURCE_HASH_MISMATCH"):
        build_snapshot(source_manifest, identities, tmp_path / "output")


def _event_sessions(count: int = 7) -> pd.DataFrame:
    sessions = pd.bdate_range("2022-01-03", periods=count).date
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * count + ["QQQ"] * count,
            "session_date": list(sessions) * 2,
            "bar_idx": [2] * (count * 2),
        }
    )


def _filing(
    accession: str = "acc-1",
    acceptance: str = "2022-01-03T12:00:00Z",
    form: str = "SC 13D",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "cik": [1],
            "accession_number": [accession],
            "filing_date": [pd.Timestamp(acceptance).date()],
            "acceptance_timestamp": [pd.Timestamp(acceptance)],
            "form": [form],
            "source": ["source"],
            "sc13d": [form == "SC 13D"],
            "sc13d_amendment": [form == "SC 13D/A"],
            "sc13g": [form == "SC 13G"],
            "sc13g_amendment": [form == "SC 13G/A"],
        }
    )


def test_state_starts_next_session_and_expires_after_five() -> None:
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    result = build_event_features(_event_sessions(), _filing(), identity)

    aaa = result.loc[result["symbol"].eq("AAA")].reset_index(drop=True)
    qqq = result.loc[result["symbol"].eq("QQQ")]
    assert aaa.loc[0, "coverage_reason"] == "SEC_BENEFICIAL_NO_ACTIVE_FILING"
    assert aaa["sec_beneficial_cik"].eq(1).all()
    assert aaa.loc[1:5, "sec_beneficial_sc13d"].eq(1).all()
    assert aaa.loc[6, "coverage_reason"] == "SEC_BENEFICIAL_NO_ACTIVE_FILING"
    assert qqq["coverage_reason"].eq("SEC_IDENTITY_UNAVAILABLE").all()


def test_cluster_uses_only_causally_available_prior_twenty_sessions() -> None:
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    filings = pd.concat(
        [
            _filing("acc-1", "2022-01-03T12:00:00Z", "SC 13D"),
            _filing("acc-2", "2022-01-05T12:00:00Z", "SC 13G/A"),
        ],
        ignore_index=True,
    )

    result = build_event_features(_event_sessions(22), filings, identity)

    aaa = result.loc[result["symbol"].eq("AAA")].reset_index(drop=True)
    assert aaa.loc[1, "sec_beneficial_clustered"] == 0
    assert aaa.loc[3, "sec_beneficial_clustered"] == 1
    assert aaa.loc[3, "sec_beneficial_active_accessions"] == ("acc-1", "acc-2")


def test_feature_cache_resumes_identical_atomic_output(tmp_path) -> None:
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})
    output = tmp_path / "features.parquet"

    first = build_feature_cache(_event_sessions(), _filing(), identity, output)
    second = build_feature_cache(_event_sessions(), _filing(), identity, output)

    assert first["status"] == "COMPLETE"
    assert first["rows"] == 14
    assert first["qualifying_symbol_filings"] == 1
    assert first["output_sha256"] == second["output_sha256"]
