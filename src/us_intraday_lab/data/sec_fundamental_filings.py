"""Causal SEC filing data contract for the fixed training sample."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "GrossProfit",
    "OperatingIncomeLoss",
    "CashAndCashEquivalentsAtCarryingValue",
    "Assets",
    "Liabilities",
)


def parse_ticker_map(
    body: bytes, symbols: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return exact SEC company identities plus explicit unmatched symbols."""
    payload = json.loads(body)
    if payload.get("fields") != ["cik", "name", "ticker", "exchange"]:
        raise ValueError("SEC_TICKER_MAP_SCHEMA_INVALID")
    frame = pd.DataFrame(payload.get("data", []), columns=payload["fields"])
    if frame.empty:
        raise ValueError("SEC_TICKER_MAP_EMPTY")
    frame["ticker"] = frame["ticker"].astype(str)
    requested = {str(symbol) for symbol in symbols}
    selected = frame.loc[frame["ticker"].isin(requested)].copy()
    if selected["ticker"].duplicated().any():
        raise ValueError("SEC_TICKER_MAP_DUPLICATE")
    selected["cik"] = pd.to_numeric(selected["cik"], errors="raise").astype("int64")
    matched = (
        selected.rename(columns={"ticker": "symbol"})[
            ["symbol", "cik", "name", "exchange"]
        ]
        .sort_values("symbol")
        .reset_index(drop=True)
    )
    missing = pd.DataFrame(
        {
            "symbol": sorted(requested.difference(matched["symbol"])),
            "coverage_reason": "SEC_IDENTITY_UNAVAILABLE",
        }
    )
    return matched, missing


def parse_submissions(body: bytes, cik: int) -> pd.DataFrame:
    """Normalize original training-period 10-Q accessions for one exact CIK."""
    payload = json.loads(body)
    if int(payload.get("cik", -1)) != int(cik):
        raise ValueError("SEC_SUBMISSIONS_CIK_MISMATCH")
    recent = payload.get("filings", {}).get("recent", {})
    columns = ("accessionNumber", "filingDate", "reportDate", "form")
    if not all(column in recent for column in columns):
        raise ValueError("SEC_SUBMISSIONS_SCHEMA_INVALID")
    lengths = {len(recent[column]) for column in columns}
    if len(lengths) != 1:
        raise ValueError("SEC_SUBMISSIONS_COLUMN_LENGTH_MISMATCH")
    frame = pd.DataFrame({column: recent[column] for column in columns})
    filing_dates = pd.to_datetime(frame["filingDate"], errors="coerce")
    report_dates = pd.to_datetime(frame["reportDate"], errors="coerce")
    if filing_dates.isna().any() or report_dates.isna().any():
        raise ValueError("SEC_SUBMISSIONS_DATE_INVALID")
    result = pd.DataFrame(
        {
            "cik": int(cik),
            "accession": frame["accessionNumber"].astype(str),
            "filing_date": filing_dates.dt.date,
            "report_date": report_dates.dt.date,
            "form": frame["form"].astype(str),
        }
    )
    result = result.loc[
        result["form"].eq("10-Q")
        & result["filing_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result["accession"].duplicated().any():
        raise ValueError("SEC_SUBMISSIONS_ACCESSION_DUPLICATE")
    return result.sort_values(["filing_date", "accession"]).reset_index(drop=True)


def parse_companyfacts(body: bytes, cik: int) -> pd.DataFrame:
    """Flatten frozen USD US-GAAP facts for the canonical concept set."""
    payload = json.loads(body)
    if int(payload.get("cik", -1)) != int(cik):
        raise ValueError("SEC_COMPANYFACTS_CIK_MISMATCH")
    taxonomy = payload.get("facts", {}).get("us-gaap", {})
    records: list[dict[str, object]] = []
    for concept in CONCEPTS:
        for fact in taxonomy.get(concept, {}).get("units", {}).get("USD", []):
            if fact.get("form") not in {"10-Q", "10-Q/A"}:
                continue
            try:
                value = float(fact["val"])
                end = pd.Timestamp(fact["end"]).date()
                filed = pd.Timestamp(fact["filed"]).date()
            except (KeyError, TypeError, ValueError):
                raise ValueError("SEC_COMPANYFACTS_VALUE_INVALID") from None
            start_value = fact.get("start")
            start = pd.Timestamp(start_value).date() if start_value else None
            records.append(
                {
                    "cik": int(cik),
                    "accession": str(fact["accn"]),
                    "concept": concept,
                    "unit": "USD",
                    "start_date": start,
                    "end_date": end,
                    "filed_date": filed,
                    "form": str(fact["form"]),
                    "value": value,
                }
            )
    result = pd.DataFrame.from_records(
        records,
        columns=[
            "cik",
            "accession",
            "concept",
            "unit",
            "start_date",
            "end_date",
            "filed_date",
            "form",
            "value",
        ],
    )
    if result.empty:
        return result
    return (
        result.drop_duplicates()
        .sort_values(["accession", "concept", "end_date"])
        .reset_index(drop=True)
    )
