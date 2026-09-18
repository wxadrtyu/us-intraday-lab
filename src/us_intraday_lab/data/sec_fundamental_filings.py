"""Causal SEC filing data contract for the fixed training sample."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from uuid import uuid4

import numpy as np
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
Fetch = Callable[[str], bytes]


def training_sample_symbols(events: pd.DataFrame) -> set[str]:
    """Return symbols present inside the exact 2021-2023 training boundary."""
    required = {"symbol", "session_date"}
    if missing := required.difference(events.columns):
        raise ValueError(f"SEC_SAMPLE_COLUMNS_MISSING:{sorted(missing)}")
    dates = pd.to_datetime(events["session_date"], errors="coerce").dt.date
    if dates.isna().any():
        raise ValueError("SEC_SAMPLE_DATE_INVALID")
    selected = events.loc[
        dates.map(lambda value: TRAIN_START <= value <= TRAIN_END), "symbol"
    ]
    return set(selected.astype(str))


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _load_or_fetch(path: Path, url: str, fetch: Fetch) -> bytes:
    if path.exists():
        return path.read_bytes()
    body = fetch(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(body)
    try:
        if path.exists():
            if path.read_bytes() != body:
                raise RuntimeError(f"SEC_RAW_IMMUTABLE_COLLISION:{path}")
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return body


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
    frame = frame.loc[frame["form"].astype(str).eq("10-Q")].copy()
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
        result["filing_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
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


def acquire_training_snapshot(
    symbols: set[str], fetch: Fetch, raw_root: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Acquire exact-matched SEC sources and normalize original 10-Q facts."""
    ticker_path = raw_root / "company_tickers_exchange.json"
    ticker_body = _load_or_fetch(ticker_path, TICKER_MAP_URL, fetch)
    identities, missing = parse_ticker_map(ticker_body, symbols)
    sources: list[dict[str, object]] = [
        {
            "url": TICKER_MAP_URL,
            "raw_path": str(ticker_path.resolve()),
            "bytes": len(ticker_body),
            "sha256": _sha256(ticker_body),
        }
    ]
    normalized: list[pd.DataFrame] = []
    companyfacts_unavailable: list[str] = []
    for identity in identities.itertuples(index=False):
        cik = int(identity.cik)
        submissions_url = SUBMISSIONS_URL.format(cik=cik)
        facts_url = COMPANYFACTS_URL.format(cik=cik)
        submissions_path = raw_root / "submissions" / f"CIK{cik:010d}.json"
        facts_path = raw_root / "companyfacts" / f"CIK{cik:010d}.json"
        submissions_body = _load_or_fetch(submissions_path, submissions_url, fetch)
        sources.append(
            {
                "url": submissions_url,
                "raw_path": str(submissions_path.resolve()),
                "bytes": len(submissions_body),
                "sha256": _sha256(submissions_body),
            }
        )
        try:
            facts_body = _load_or_fetch(facts_path, facts_url, fetch)
        except HTTPError as error:
            if error.code != 404:
                raise
            companyfacts_unavailable.append(str(identity.symbol))
            sources.append({"url": facts_url, "status": 404})
            continue
        sources.append(
            {
                "url": facts_url,
                "raw_path": str(facts_path.resolve()),
                "bytes": len(facts_body),
                "sha256": _sha256(facts_body),
            }
        )
        filings = parse_submissions(submissions_body, cik)
        facts = parse_companyfacts(facts_body, cik)
        if filings.empty or facts.empty:
            continue
        joined = facts.merge(
            filings,
            how="inner",
            on=["cik", "accession"],
            validate="many_to_one",
            suffixes=("_fact", "_filing"),
        )
        if joined.empty:
            continue
        joined.insert(0, "symbol", str(identity.symbol))
        normalized.append(joined)
    snapshot = (
        pd.concat(normalized, ignore_index=True)
        if normalized
        else pd.DataFrame(
            columns=[
                "symbol",
                "cik",
                "accession",
                "concept",
                "unit",
                "start_date",
                "end_date",
                "filed_date",
                "form_fact",
                "value",
                "filing_date",
                "report_date",
                "form_filing",
            ]
        )
    )
    snapshot = snapshot.sort_values(
        ["symbol", "filing_date", "accession", "concept", "end_date"]
    ).reset_index(drop=True)
    manifest: dict[str, object] = {
        "requested_symbols": len(set(symbols)),
        "matched_symbols": len(identities),
        "unmatched_symbols": missing["symbol"].tolist(),
        "companyfacts_unavailable_symbols": companyfacts_unavailable,
        "normalized_fact_rows": len(snapshot),
        "sources": sources,
        "training_only": True,
    }
    return snapshot, manifest


_REVENUE_PRIORITY = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
_FEATURE_COLUMNS = (
    "revenue_growth_acceleration",
    "gross_margin_expansion",
    "operating_margin_expansion",
    "cash_asset_improvement",
    "deleveraging",
)


def _fact_value(
    facts: pd.DataFrame,
    concepts: tuple[str, ...],
    *,
    duration: bool,
) -> float:
    for concept in concepts:
        selected = facts.loc[facts["concept"].eq(concept)].copy()
        if duration:
            days = (
                pd.to_datetime(selected["end_date"])
                - pd.to_datetime(selected["start_date"])
            ).dt.days
            selected = selected.loc[days.between(70, 110)]
        if selected.empty:
            continue
        values = pd.to_numeric(selected["value"], errors="coerce").dropna().unique()
        if len(values) == 1:
            return float(values[0])
        if len(values) > 1:
            return float("nan")
    return float("nan")


def _nearest_prior_index(
    frame: pd.DataFrame, index: int, minimum_days: int, maximum_days: int
) -> int | None:
    current = frame.loc[index, "report_date"]
    candidates = frame.loc[: index - 1, "report_date"].map(
        lambda prior: (current - prior).days
    )
    candidates = candidates.loc[candidates.between(minimum_days, maximum_days)]
    if candidates.empty:
        return None
    return int((candidates - (minimum_days + maximum_days) / 2).abs().idxmin())


def derive_filing_features(
    filings: pd.DataFrame, facts: pd.DataFrame
) -> pd.DataFrame:
    """Derive frozen issuer accounting changes from exact filing accessions."""
    filing_required = {
        "symbol",
        "cik",
        "accession",
        "filing_date",
        "report_date",
    }
    fact_required = {
        "cik",
        "accession",
        "concept",
        "start_date",
        "end_date",
        "value",
    }
    if missing := filing_required.difference(filings.columns):
        raise ValueError(f"SEC_FILING_COLUMNS_MISSING:{sorted(missing)}")
    if missing := fact_required.difference(facts.columns):
        raise ValueError(f"SEC_FACT_COLUMNS_MISSING:{sorted(missing)}")
    source_filings = filings.copy()
    source_filings["filing_date"] = pd.to_datetime(
        source_filings["filing_date"]
    ).dt.date
    source_filings["report_date"] = pd.to_datetime(
        source_filings["report_date"]
    ).dt.date
    if source_filings.duplicated(["symbol", "accession"]).any():
        raise ValueError("SEC_FILING_ACCESSION_DUPLICATE")
    source_facts = facts.copy()
    source_facts["end_date"] = pd.to_datetime(source_facts["end_date"]).dt.date
    records: list[dict[str, object]] = []
    for filing in source_filings.itertuples(index=False):
        selected = source_facts.loc[
            source_facts["cik"].eq(filing.cik)
            & source_facts["accession"].eq(filing.accession)
            & source_facts["end_date"].eq(filing.report_date)
        ]
        revenue = _fact_value(selected, _REVENUE_PRIORITY, duration=True)
        gross_profit = _fact_value(selected, ("GrossProfit",), duration=True)
        operating_income = _fact_value(
            selected, ("OperatingIncomeLoss",), duration=True
        )
        cash = _fact_value(
            selected, ("CashAndCashEquivalentsAtCarryingValue",), duration=False
        )
        assets = _fact_value(selected, ("Assets",), duration=False)
        liabilities = _fact_value(selected, ("Liabilities",), duration=False)
        records.append(
            {
                "symbol": str(filing.symbol),
                "cik": int(filing.cik),
                "accession": str(filing.accession),
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "revenue": revenue,
                "gross_margin": gross_profit / revenue if revenue > 0 else np.nan,
                "operating_margin": (
                    operating_income / revenue if revenue > 0 else np.nan
                ),
                "cash_assets": cash / assets if assets > 0 else np.nan,
                "liabilities_assets": (
                    liabilities / assets if assets > 0 else np.nan
                ),
            }
        )
    result = pd.DataFrame.from_records(records)
    if result.empty:
        return result
    feature_frames: list[pd.DataFrame] = []
    for _symbol, group in result.groupby("symbol", sort=True, observed=True):
        group = group.sort_values(["report_date", "accession"]).reset_index(drop=True)
        group["revenue_yoy_growth"] = np.nan
        group["gross_margin_expansion"] = np.nan
        group["operating_margin_expansion"] = np.nan
        group["cash_asset_improvement"] = np.nan
        group["deleveraging"] = np.nan
        prior_quarters: dict[int, int | None] = {}
        for index in group.index:
            prior_year = _nearest_prior_index(group, index, 330, 400)
            prior_quarter = _nearest_prior_index(group, index, 70, 110)
            prior_quarters[int(index)] = prior_quarter
            if prior_year is not None:
                prior_revenue = group.loc[prior_year, "revenue"]
                if pd.notna(prior_revenue) and prior_revenue > 0:
                    group.loc[index, "revenue_yoy_growth"] = (
                        group.loc[index, "revenue"] / prior_revenue - 1.0
                    )
                group.loc[index, "gross_margin_expansion"] = (
                    group.loc[index, "gross_margin"]
                    - group.loc[prior_year, "gross_margin"]
                )
                group.loc[index, "operating_margin_expansion"] = (
                    group.loc[index, "operating_margin"]
                    - group.loc[prior_year, "operating_margin"]
                )
            if prior_quarter is not None:
                group.loc[index, "cash_asset_improvement"] = (
                    group.loc[index, "cash_assets"]
                    - group.loc[prior_quarter, "cash_assets"]
                )
                group.loc[index, "deleveraging"] = (
                    group.loc[prior_quarter, "liabilities_assets"]
                    - group.loc[index, "liabilities_assets"]
                )
        group["revenue_growth_acceleration"] = np.nan
        for index, prior_quarter in prior_quarters.items():
            if prior_quarter is not None:
                group.loc[index, "revenue_growth_acceleration"] = (
                    group.loc[index, "revenue_yoy_growth"]
                    - group.loc[prior_quarter, "revenue_yoy_growth"]
                )
        feature_frames.append(group)
    return pd.concat(feature_frames, ignore_index=True)[
        [
            "symbol",
            "cik",
            "accession",
            "filing_date",
            "report_date",
            *_FEATURE_COLUMNS,
        ]
    ]


def build_event_features(
    events: pd.DataFrame,
    filing_features: pd.DataFrame,
    identity: pd.DataFrame,
) -> pd.DataFrame:
    """Activate a filing on the next five event sessions and rank positive changes."""
    required = {"symbol", "session_date", "bar_idx"}
    if missing := required.difference(events.columns):
        raise ValueError(f"SEC_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    result = events.copy()
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    result = result.loc[
        result["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("SEC_EVENT_KEY_DUPLICATE")
    sessions = sorted(result["session_date"].unique())
    session_index = {session: index for index, session in enumerate(sessions)}
    active_records: list[dict[str, object]] = []
    features = filing_features.copy()
    features["filing_date"] = pd.to_datetime(features["filing_date"]).dt.date
    for filing in features.itertuples(index=False):
        available = next(
            (session for session in sessions if session > filing.filing_date), None
        )
        if available is None:
            continue
        start = session_index[available]
        for session in sessions[start : start + 5]:
            active_records.append(
                {
                    "symbol": str(filing.symbol),
                    "session_date": session,
                    "filing_date": filing.filing_date,
                    "accession": filing.accession,
                    **{
                        column: getattr(filing, column)
                        for column in _FEATURE_COLUMNS
                    },
                }
            )
    active = pd.DataFrame.from_records(active_records)
    if not active.empty:
        active = (
            active.sort_values(["symbol", "session_date", "filing_date", "accession"])
            .drop_duplicates(["symbol", "session_date"], keep="last")
            .drop(columns="filing_date")
        )
        result = result.merge(
            active, how="left", on=["symbol", "session_date"], validate="many_to_one"
        )
    else:
        result["accession"] = pd.NA
        for column in _FEATURE_COLUMNS:
            result[column] = np.nan
    for column in _FEATURE_COLUMNS:
        raw = pd.to_numeric(result[column], errors="coerce").where(lambda value: value > 0)
        grouped = raw.groupby(result["session_date"], observed=True)
        lower = grouped.transform(lambda value: value.quantile(0.01))
        upper = grouped.transform(lambda value: value.quantile(0.99))
        winsorized = raw.clip(lower=lower, upper=upper)
        result[column] = winsorized.groupby(
            result["session_date"], observed=True
        ).rank(method="average", pct=True)
    known = result["symbol"].isin(set(identity["symbol"].astype(str)))
    active_filing = result["accession"].notna()
    any_feature = result[list(_FEATURE_COLUMNS)].notna().any(axis=1)
    result["coverage_reason"] = np.select(
        [~known, ~active_filing, ~any_feature],
        [
            "SEC_IDENTITY_UNAVAILABLE",
            "SEC_NO_ACTIVE_FILING",
            "SEC_FEATURE_MISSING",
        ],
        default="COVERED",
    )
    return result
