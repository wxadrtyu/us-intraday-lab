from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from us_intraday_lab.data.sec_fundamental_filings import (
    COMPANYFACTS_URL,
    SUBMISSIONS_URL,
    TICKER_MAP_URL,
    acquire_training_snapshot,
    build_event_features,
    derive_filing_features,
    parse_companyfacts,
    parse_submissions,
    parse_ticker_map,
    training_sample_symbols,
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


def test_acquisition_requests_only_exact_identities_and_resumes_raw_bytes(
    tmp_path,
) -> None:
    ticker_body = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
        }
    ).encode()
    submissions_body = json.dumps(
        {
            "cik": "320193",
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-22-000070"],
                    "filingDate": ["2022-07-29"],
                    "reportDate": ["2022-06-25"],
                    "form": ["10-Q"],
                }
            },
        }
    ).encode()
    facts_body = json.dumps(
        {
            "cik": 320193,
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2022-03-27",
                                    "end": "2022-06-25",
                                    "val": 10,
                                    "accn": "0000320193-22-000070",
                                    "form": "10-Q",
                                    "filed": "2022-07-29",
                                }
                            ]
                        }
                    }
                }
            },
        }
    ).encode()
    responses = {
        TICKER_MAP_URL: ticker_body,
        SUBMISSIONS_URL.format(cik=320193): submissions_body,
        COMPANYFACTS_URL.format(cik=320193): facts_body,
    }
    requested: list[str] = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return responses[url]

    snapshot, manifest = acquire_training_snapshot(
        {"AAPL", "QQQ"}, fetch, tmp_path / "raw"
    )

    assert requested == list(responses)
    assert snapshot[["symbol", "accession", "concept", "value"]].to_dict(
        "records"
    ) == [
        {
            "symbol": "AAPL",
            "accession": "0000320193-22-000070",
            "concept": "Revenues",
            "value": 10.0,
        }
    ]
    assert manifest["requested_symbols"] == 2
    assert manifest["matched_symbols"] == 1
    assert manifest["unmatched_symbols"] == ["QQQ"]
    assert len(manifest["sources"]) == 3

    def forbidden_fetch(_url: str) -> bytes:
        raise AssertionError("resume must use frozen raw bytes")

    resumed, resumed_manifest = acquire_training_snapshot(
        {"AAPL", "QQQ"}, forbidden_fetch, tmp_path / "raw"
    )

    assert resumed.equals(snapshot)
    assert resumed_manifest == manifest


def _quarterly_filing_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    filings: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    quarter_ends = [
        date(2021, 3, 31),
        date(2021, 6, 30),
        date(2021, 9, 30),
        date(2022, 3, 31),
        date(2022, 6, 30),
        date(2022, 9, 30),
        date(2023, 3, 31),
        date(2023, 6, 30),
    ]
    revenues = [100.0, 105.0, 110.0, 120.0, 140.0, 150.0, 145.0, 180.0]
    for index, (end, revenue) in enumerate(zip(quarter_ends, revenues, strict=True)):
        accession = f"acc-{index}"
        filing_date = end + timedelta(days=30)
        filings.append(
            {
                "symbol": "AAA",
                "cik": 1,
                "accession": accession,
                "filing_date": filing_date,
                "report_date": end,
            }
        )
        values = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": revenue,
            "GrossProfit": revenue * (0.40 + index * 0.005),
            "OperatingIncomeLoss": revenue * (0.15 + index * 0.002),
            "CashAndCashEquivalentsAtCarryingValue": 20.0 + index * 2,
            "Assets": 100.0 + index * 3,
            "Liabilities": 60.0 - index,
        }
        for concept, value in values.items():
            duration = concept in {
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "GrossProfit",
                "OperatingIncomeLoss",
            }
            facts.append(
                {
                    "cik": 1,
                    "accession": accession,
                    "concept": concept,
                    "start_date": end - timedelta(days=89) if duration else None,
                    "end_date": end,
                    "value": value,
                }
            )
    return pd.DataFrame(filings), pd.DataFrame(facts)


def test_filing_features_use_exact_period_comparisons() -> None:
    filings, facts = _quarterly_filing_inputs()

    result = derive_filing_features(filings, facts)

    row = result.loc[result["accession"].eq("acc-4")].iloc[0]
    assert row["gross_margin_expansion"] == pytest.approx(0.015)
    assert row["operating_margin_expansion"] == pytest.approx(0.006)
    assert row["cash_asset_improvement"] > 0
    assert row["deleveraging"] > 0
    assert row["revenue_growth_acceleration"] > 0


def test_event_features_start_next_session_and_expire_after_five_sessions() -> None:
    filings, facts = _quarterly_filing_inputs()
    filing_features = derive_filing_features(filings, facts)
    target = filing_features.loc[filing_features["accession"].eq("acc-4")].copy()
    filing_day = target["filing_date"].iat[0]
    sessions = [filing_day + timedelta(days=offset) for offset in range(7)]
    events = pd.DataFrame(
        {
            "symbol": ["AAA"] * len(sessions) + ["QQQ"] * len(sessions),
            "session_date": sessions * 2,
            "bar_idx": [2] * (2 * len(sessions)),
        }
    )
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    result = build_event_features(events, target, identity)

    aaa = result.loc[result["symbol"].eq("AAA")].reset_index(drop=True)
    qqq = result.loc[result["symbol"].eq("QQQ")]
    assert aaa.loc[0, "coverage_reason"] == "SEC_NO_ACTIVE_FILING"
    assert aaa.loc[1:5, "coverage_reason"].eq("COVERED").all()
    assert aaa.loc[6, "coverage_reason"] == "SEC_NO_ACTIVE_FILING"
    assert qqq["coverage_reason"].eq("SEC_IDENTITY_UNAVAILABLE").all()


def test_training_sample_symbols_excludes_later_event_periods() -> None:
    events = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "session_date": ["2021-01-04", "2023-12-29", "2024-01-02"],
        }
    )

    assert training_sample_symbols(events) == {"AAA", "BBB"}
