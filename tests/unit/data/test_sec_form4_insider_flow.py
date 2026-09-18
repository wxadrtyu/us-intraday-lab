from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from us_intraday_lab.data.sec_form4_insider_flow import (
    build_event_features,
    normalize_form4_filings,
    parse_quarter_zip,
    quarter_urls,
)


def _tables(
    *,
    document_type: str = "4",
    code: str = "P",
    direction: str = "A",
    equity_swap: str = "0",
    price: str = "50",
) -> dict[str, pd.DataFrame]:
    return {
        "submission": pd.DataFrame(
            {
                "ACCESSION_NUMBER": ["0000000001-21-000001"],
                "FILING_DATE": ["05-JAN-2021"],
                "PERIOD_OF_REPORT": ["04-JAN-2021"],
                "DOCUMENT_TYPE": [document_type],
                "ISSUERCIK": ["0000000001"],
                "ISSUERNAME": ["Alpha Corp"],
                "ISSUERTRADINGSYMBOL": ["AAA"],
            }
        ),
        "reportingowner": pd.DataFrame(
            {
                "ACCESSION_NUMBER": ["0000000001-21-000001"],
                "RPTOWNERCIK": ["0000000002"],
                "RPTOWNERNAME": ["Jane Doe"],
                "RPTOWNER_RELATIONSHIP": ["Officer,Director"],
                "RPTOWNER_TITLE": ["CEO"],
            }
        ),
        "nonderiv_trans": pd.DataFrame(
            {
                "ACCESSION_NUMBER": ["0000000001-21-000001"],
                "NONDERIV_TRANS_SK": [1],
                "TRANS_DATE": ["04-JAN-2021"],
                "TRANS_CODE": [code],
                "EQUITY_SWAP_INVOLVED": [equity_swap],
                "TRANS_TIMELINESS": [""],
                "TRANS_SHARES": ["100"],
                "TRANS_PRICEPERSHARE": [price],
                "TRANS_ACQUIRED_DISP_CD": [direction],
                "SHRS_OWND_FOLWNG_TRANS": ["1000"],
                "DIRECT_INDIRECT_OWNERSHIP": ["D"],
            }
        ),
    }


def _zip_bytes(tables: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    names = {
        "submission": "SUBMISSION.tsv",
        "reportingowner": "REPORTINGOWNER.tsv",
        "nonderiv_trans": "NONDERIV_TRANS.tsv",
    }
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for key, name in names.items():
            archive.writestr(name, tables[key].to_csv(sep="\t", index=False))
    return output.getvalue()


def _identities() -> pd.DataFrame:
    return pd.DataFrame({"symbol": ["AAA", "AAB"], "cik": [1, 1]})


def test_quarter_urls_are_exactly_2021_through_2023() -> None:
    urls = quarter_urls()

    assert len(urls) == 12
    assert urls[0].endswith("2021q1_form345.zip")
    assert urls[-1].endswith("2023q4_form345.zip")


def test_quarter_zip_requires_documented_tables() -> None:
    body = _zip_bytes(_tables())

    parsed = parse_quarter_zip(body, "2021q1_form345.zip")

    assert set(parsed) == {"submission", "reportingowner", "nonderiv_trans"}
    assert parsed["submission"].loc[0, "ACCESSION_NUMBER"] == (
        "0000000001-21-000001"
    )

    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\nA\n")
    with pytest.raises(ValueError, match="SEC_FORM4_ZIP_TABLES_MISSING"):
        parse_quarter_zip(output.getvalue(), "broken.zip")


def test_quarter_zip_rejects_duplicate_primary_keys() -> None:
    tables = _tables()
    tables["nonderiv_trans"] = pd.concat(
        [tables["nonderiv_trans"], tables["nonderiv_trans"]], ignore_index=True
    )

    with pytest.raises(ValueError, match="SEC_FORM4_NONDERIV_TRANS_KEY_DUPLICATE"):
        parse_quarter_zip(_zip_bytes(tables), "duplicate.zip")


def test_normalizer_accepts_original_purchase_and_preserves_shared_cik() -> None:
    filings, rejected = normalize_form4_filings(_tables(), _identities())

    assert rejected.empty
    assert filings["symbol"].tolist() == ["AAA", "AAB"]
    assert filings["purchase_notional"].tolist() == [5000.0, 5000.0]
    assert filings["sale_notional"].tolist() == [0.0, 0.0]
    assert filings["net_open_market_balance"].tolist() == [1.0, 1.0]
    assert filings["unique_purchasing_owners"].tolist() == [1, 1]
    assert filings["officer_director_purchase_share"].tolist() == [1.0, 1.0]
    assert filings["purchase_to_post_holding"].tolist() == [0.1, 0.1]


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"document_type": "4/A"}, "SEC_FORM4_NOT_ORIGINAL_FORM4"),
        ({"code": "P", "direction": "D"}, "SEC_FORM4_DIRECTION_MISMATCH"),
        ({"equity_swap": "1"}, "SEC_FORM4_EQUITY_SWAP"),
        ({"price": ""}, "SEC_FORM4_VALUE_MISSING"),
    ],
)
def test_normalizer_preserves_rejection_reasons(arguments, reason) -> None:
    filings, rejected = normalize_form4_filings(_tables(**arguments), _identities())

    assert filings.empty
    assert rejected["reason"].tolist() == [reason]


def test_normalizer_rejects_broken_accession_relationship() -> None:
    tables = _tables()
    tables["nonderiv_trans"].loc[0, "ACCESSION_NUMBER"] = "orphan"

    with pytest.raises(ValueError, match="SEC_FORM4_TRANSACTION_ACCESSION_ORPHAN"):
        normalize_form4_filings(tables, _identities())


def _filing(accession: str = "acc-1", filing_date: date = date(2022, 7, 29)):
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "cik": [1],
            "accession": [accession],
            "filing_date": [filing_date],
            "period_of_report": [filing_date - timedelta(days=1)],
            "purchase_notional": [10_000.0],
            "sale_notional": [0.0],
            "net_open_market_balance": [1.0],
            "unique_purchasing_owners": [2],
            "officer_director_purchase_share": [1.0],
            "purchase_to_post_holding": [0.2],
            "transaction_filing_lag_days": [1],
            "late_reported": [False],
            "qualifying_transaction_count": [2],
            "source": ["2022q3_form345.zip"],
        }
    )


def test_event_features_start_next_session_and_expire_after_five() -> None:
    filing_day = date(2022, 7, 29)
    sessions = [filing_day + timedelta(days=offset) for offset in range(7)]
    events = pd.DataFrame(
        {
            "symbol": ["AAA"] * 7 + ["QQQ"] * 7,
            "session_date": sessions * 2,
            "bar_idx": [2] * 14,
        }
    )

    result = build_event_features(events, _filing(), _identities())

    aaa = result.loc[result["symbol"].eq("AAA")].reset_index(drop=True)
    qqq = result.loc[result["symbol"].eq("QQQ")]
    assert aaa.loc[0, "coverage_reason"] == "SEC_FORM4_NO_ACTIVE_FILING"
    assert aaa.loc[1:5, "coverage_reason"].eq("COVERED").all()
    assert aaa.loc[6, "coverage_reason"] == "SEC_FORM4_NO_ACTIVE_FILING"
    assert aaa.loc[1:5, "active_accessions"].eq("acc-1").all()
    assert qqq["coverage_reason"].eq("SEC_FORM4_IDENTITY_UNAVAILABLE").all()


def test_raw_inventory_survives_lossy_event_projection() -> None:
    filings = pd.concat(
        [
            _filing(f"acc-{index}", date(2022, 7, 25) + timedelta(days=index))
            for index in range(4)
        ],
        ignore_index=True,
    )
    events = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "session_date": [date(2022, 8, 1)],
            "bar_idx": [2],
        }
    )

    result = build_event_features(events, filings, _identities())

    assert result.loc[0, "sec_form4_qualifying_filing_count"] == 4
    assert result.loc[0, "active_accessions"] == "acc-0|acc-1|acc-2|acc-3"


def test_event_features_exclude_dates_after_training_boundary() -> None:
    events = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "session_date": ["2023-12-29", "2024-01-02"],
            "bar_idx": [2, 2],
        }
    )

    result = build_event_features(events, _filing(), _identities())

    assert result["session_date"].tolist() == [date(2023, 12, 29)]
