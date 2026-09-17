from __future__ import annotations

import json

import pytest

from us_intraday_lab.data.sec_fundamental_filings import (
    parse_companyfacts,
    parse_submissions,
    parse_ticker_map,
)


def test_ticker_map_uses_exact_case_sensitive_identity_and_preserves_missing() -> None:
    body = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [320193, "Apple Inc.", "AAPL", "Nasdaq"],
                [789019, "Microsoft Corp.", "MSFT", "Nasdaq"],
                [999999, "Wrong case", "fb", "NYSE"],
            ],
        }
    ).encode()

    matched, missing = parse_ticker_map(body, {"AAPL", "MSFT", "FB"})

    assert matched[["symbol", "cik"]].to_dict("records") == [
        {"symbol": "AAPL", "cik": 320193},
        {"symbol": "MSFT", "cik": 789019},
    ]
    assert missing.to_dict("records") == [
        {"symbol": "FB", "coverage_reason": "SEC_IDENTITY_UNAVAILABLE"}
    ]


def test_submissions_retains_only_original_training_ten_q() -> None:
    body = json.dumps(
        {
            "cik": "320193",
            "filings": {
                "recent": {
                    "accessionNumber": [
                        "0000320193-22-000070",
                        "0000320193-22-000071",
                        "0000320193-24-000001",
                    ],
                    "filingDate": ["2022-07-29", "2022-08-01", "2024-01-02"],
                    "reportDate": ["2022-06-25", "2022-06-25", "2023-12-30"],
                    "form": ["10-Q", "10-Q/A", "10-Q"],
                }
            },
        }
    ).encode()

    result = parse_submissions(body, 320193)

    assert result.to_dict("records") == [
        {
            "cik": 320193,
            "accession": "0000320193-22-000070",
            "filing_date": result.loc[0, "filing_date"],
            "report_date": result.loc[0, "report_date"],
            "form": "10-Q",
        }
    ]
    assert result.loc[0, "filing_date"].isoformat() == "2022-07-29"
    assert result.loc[0, "report_date"].isoformat() == "2022-06-25"


def test_companyfacts_normalizes_exact_accession_usd_facts() -> None:
    body = json.dumps(
        {
            "cik": 320193,
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2022-03-27",
                                    "end": "2022-06-25",
                                    "val": 82_959_000_000,
                                    "accn": "0000320193-22-000070",
                                    "form": "10-Q",
                                    "filed": "2022-07-29",
                                }
                            ]
                        }
                    },
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "end": "2022-06-25",
                                    "val": 1,
                                    "accn": "0000320193-22-000070",
                                    "form": "10-Q",
                                    "filed": "2022-07-29",
                                }
                            ]
                        }
                    },
                }
            },
        }
    ).encode()

    result = parse_companyfacts(body, 320193)

    assert result[["cik", "accession", "concept", "unit", "value"]].to_dict(
        "records"
    ) == [
        {
            "cik": 320193,
            "accession": "0000320193-22-000070",
            "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
            "unit": "USD",
            "value": 82_959_000_000.0,
        }
    ]


def test_companyfacts_rejects_cik_mismatch() -> None:
    body = json.dumps({"cik": 789019, "facts": {"us-gaap": {}}}).encode()

    with pytest.raises(ValueError, match="SEC_COMPANYFACTS_CIK_MISMATCH"):
        parse_companyfacts(body, 320193)
