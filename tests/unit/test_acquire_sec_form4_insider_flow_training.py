from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from scripts.acquire_sec_form4_insider_flow_training import acquire_training_snapshot
from us_intraday_lab.data.sec_form4_insider_flow import quarter_urls


def _identity() -> pd.DataFrame:
    return pd.DataFrame({"symbol": ["AAA"], "cik": [1]})


def _quarter_body(index: int) -> bytes:
    accession = f"0000000001-21-{index:06d}"
    submission = pd.DataFrame(
        {
            "ACCESSION_NUMBER": [accession],
            "FILING_DATE": ["05-JAN-2021"],
            "PERIOD_OF_REPORT": ["04-JAN-2021"],
            "DOCUMENT_TYPE": ["4"],
            "ISSUERCIK": ["0000000001"],
            "ISSUERNAME": ["Alpha Corp"],
            "ISSUERTRADINGSYMBOL": ["AAA"],
        }
    )
    owner = pd.DataFrame(
        {
            "ACCESSION_NUMBER": [accession],
            "RPTOWNERCIK": ["0000000002"],
            "RPTOWNERNAME": ["Jane Doe"],
            "RPTOWNER_RELATIONSHIP": ["Officer"],
            "RPTOWNER_TITLE": ["CEO"],
        }
    )
    transaction = pd.DataFrame(
        {
            "ACCESSION_NUMBER": [accession],
            "NONDERIV_TRANS_SK": [index],
            "TRANS_DATE": ["04-JAN-2021"],
            "TRANS_CODE": ["P"],
            "EQUITY_SWAP_INVOLVED": ["0"],
            "TRANS_TIMELINESS": [""],
            "TRANS_SHARES": ["100"],
            "TRANS_PRICEPERSHARE": ["50"],
            "TRANS_ACQUIRED_DISP_CD": ["A"],
            "SHRS_OWND_FOLWNG_TRANS": ["1000"],
            "DIRECT_INDIRECT_OWNERSHIP": ["D"],
        }
    )
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("SUBMISSION.tsv", submission.to_csv(sep="\t", index=False))
        archive.writestr(
            "REPORTINGOWNER.tsv", owner.to_csv(sep="\t", index=False)
        )
        archive.writestr(
            "NONDERIV_TRANS.tsv", transaction.to_csv(sep="\t", index=False)
        )
    return output.getvalue()


def test_acquisition_fetches_twelve_quarters_and_resumes(tmp_path) -> None:
    bodies = {
        url: _quarter_body(index)
        for index, url in enumerate(quarter_urls(), start=1)
    }
    requested: list[str] = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return bodies[url]

    filings, rejected, manifest = acquire_training_snapshot(
        fetch=fetch, root=tmp_path, identities=_identity(), request_interval=0
    )

    assert requested == list(quarter_urls())
    assert len(filings) == 12
    assert rejected.empty
    assert manifest["status"] == "COMPLETE"
    assert len(manifest["sources"]) == 12
    assert manifest["training_only"] is True
    assert manifest["paper_activation"] is False
    assert manifest["order_route"] == "FORBIDDEN"

    def forbidden_fetch(_url: str) -> bytes:
        raise AssertionError("resume must use immutable raw files")

    resumed = acquire_training_snapshot(
        fetch=forbidden_fetch,
        root=tmp_path,
        identities=_identity(),
        request_interval=0,
    )
    assert resumed[0].equals(filings)
    assert resumed[1].equals(rejected)
    assert resumed[2] == manifest


def test_acquisition_refuses_manifest_hash_collision(tmp_path) -> None:
    bodies = {
        url: _quarter_body(index)
        for index, url in enumerate(quarter_urls(), start=1)
    }
    acquire_training_snapshot(
        fetch=lambda url: bodies[url],
        root=tmp_path,
        identities=_identity(),
        request_interval=0,
    )
    first_raw = tmp_path / "raw" / "2021q1_form345.zip"
    first_raw.write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="SEC_FORM4_RAW_IMMUTABLE_COLLISION"):
        acquire_training_snapshot(
            fetch=lambda url: bodies[url],
            root=tmp_path,
            identities=_identity(),
            request_interval=0,
        )
