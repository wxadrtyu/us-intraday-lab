from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from scripts.acquire_sec_8k_event_training import acquire_training_snapshot


def _recent(accession: str, filing_date: str, item: str) -> dict[str, list[object]]:
    compact = filing_date.replace("-", "")
    return {
        "accessionNumber": [accession],
        "filingDate": [filing_date],
        "reportDate": [filing_date],
        "acceptanceDateTime": [f"{compact}163000"],
        "form": ["8-K"],
        "items": [item],
        "size": [1000],
        "primaryDocument": ["event.htm"],
    }


def _sources(tmp_path):
    current_root = tmp_path / "prior" / "raw" / "submissions"
    current_root.mkdir(parents=True)
    current = {
        "cik": "1",
        "filings": {
            "recent": _recent("current", "2023-05-01", "2.02"),
            "files": [
                {
                    "name": "CIK0000000001-submissions-001.json",
                    "filingFrom": "2020-01-01",
                    "filingTo": "2022-12-31",
                }
            ],
        },
    }
    body = json.dumps(current).encode()
    current_path = current_root / "CIK0000000001.json"
    current_path.write_bytes(body)
    prior_manifest = {
        "status": "COMPLETE",
        "sources": [
            {
                "url": "https://data.sec.gov/submissions/CIK0000000001.json",
                "raw_path": str(current_path),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ],
    }
    historical = json.dumps(
        _recent("historical", "2022-04-01", "1.01")
    ).encode()
    url = (
        "https://data.sec.gov/submissions/"
        "CIK0000000001-submissions-001.json"
    )
    return current_root, prior_manifest, {url: historical}


def _identity() -> pd.DataFrame:
    return pd.DataFrame({"symbol": ["AAA"], "cik": [1]})


def test_acquisition_reuses_verified_current_and_historical_bytes(tmp_path) -> None:
    current_root, prior_manifest, bodies = _sources(tmp_path)
    requested: list[str] = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return bodies[url]

    first = acquire_training_snapshot(
        fetch=fetch,
        root=tmp_path / "output",
        identities=_identity(),
        current_root=current_root,
        current_manifest=prior_manifest,
        request_interval=0,
        unmatched_symbols=["QQQ"],
    )

    assert requested == list(bodies)
    assert set(first[0]["accession_number"]) == {"current", "historical"}
    assert first[2]["status"] == "COMPLETE"
    assert first[2]["matched_symbols"] == 1
    assert first[2]["unmatched_symbols"] == ["QQQ"]
    assert first[2]["required_sources_complete"] is True
    assert first[2]["paper_activation"] is False
    assert first[2]["order_route"] == "FORBIDDEN"

    def forbidden_fetch(_url: str) -> bytes:
        raise AssertionError("resume must use immutable source bytes")

    second = acquire_training_snapshot(
        fetch=forbidden_fetch,
        root=tmp_path / "output",
        identities=_identity(),
        current_root=current_root,
        current_manifest=prior_manifest,
        request_interval=0,
        unmatched_symbols=["QQQ"],
    )
    assert second[0].equals(first[0])
    assert second[1].equals(first[1])
    assert second[2] == first[2]


def test_acquisition_refuses_historical_fragment_collision(tmp_path) -> None:
    current_root, prior_manifest, bodies = _sources(tmp_path)
    output = tmp_path / "output"
    acquire_training_snapshot(
        fetch=lambda url: bodies[url],
        root=output,
        identities=_identity(),
        current_root=current_root,
        current_manifest=prior_manifest,
        request_interval=0,
    )
    fragment = output / "raw" / "historical" / next(iter(bodies)).rsplit("/", 1)[-1]
    fragment.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="SEC_8K_RAW_IMMUTABLE_COLLISION"):
        acquire_training_snapshot(
            fetch=lambda url: bodies[url],
            root=output,
            identities=_identity(),
            current_root=current_root,
            current_manifest=prior_manifest,
            request_interval=0,
        )


def test_acquisition_refuses_reused_current_hash_mismatch(tmp_path) -> None:
    current_root, prior_manifest, bodies = _sources(tmp_path)
    (current_root / "CIK0000000001.json").write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="SEC_8K_CURRENT_HASH_MISMATCH"):
        acquire_training_snapshot(
            fetch=lambda url: bodies[url],
            root=tmp_path / "output",
            identities=_identity(),
            current_root=current_root,
            current_manifest=prior_manifest,
            request_interval=0,
        )
