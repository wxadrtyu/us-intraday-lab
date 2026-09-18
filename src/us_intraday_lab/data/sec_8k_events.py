"""Strict SEC submissions contract for structured 8-K training events."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "form",
    "items",
    "size",
    "primaryDocument",
)

CATEGORY_ITEMS = {
    "earnings_results": "2.02",
    "material_agreement": "1.01",
    "acquisition_disposition": "2.01",
    "director_officer_change": "5.02",
    "other_material_event": "8.01",
}


def _recent(payload: dict[str, object]) -> dict[str, list[object]]:
    filings = payload.get("filings")
    candidate: object
    if isinstance(filings, dict):
        candidate = filings.get("recent")
    else:
        candidate = payload.get("recent", payload)
    if not isinstance(candidate, dict):
        raise TypeError("SEC_8K_SCHEMA_INVALID")
    return candidate  # type: ignore[return-value]


def validate_submission_response(payload: dict[str, object], source: str) -> None:
    """Validate the parallel-array portion used by the training contract."""
    recent = _recent(payload)
    if any(column not in recent for column in REQUIRED_COLUMNS):
        raise ValueError(f"SEC_8K_SCHEMA_INVALID:{source}")
    values = [recent[column] for column in REQUIRED_COLUMNS]
    if any(not isinstance(value, list) for value in values):
        raise ValueError(f"SEC_8K_SCHEMA_INVALID:{source}")
    if len({len(value) for value in values}) != 1:
        raise ValueError(f"SEC_8K_COLUMN_LENGTH_MISMATCH:{source}")


def select_training_fragments(
    payload: dict[str, object], start: date, end: date
) -> tuple[str, ...]:
    """Select exact declared fragment names whose published ranges intersect."""
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        raise TypeError("SEC_8K_SCHEMA_INVALID")
    declared = filings.get("files", [])
    if not isinstance(declared, list):
        raise TypeError("SEC_8K_FRAGMENT_SCHEMA_INVALID")
    selected: list[str] = []
    for item in declared:
        if not isinstance(item, dict):
            raise TypeError("SEC_8K_FRAGMENT_SCHEMA_INVALID")
        try:
            name = str(item["name"])
            filing_from = pd.Timestamp(item["filingFrom"]).date()
            filing_to = pd.Timestamp(item["filingTo"]).date()
        except (KeyError, TypeError, ValueError):
            raise ValueError("SEC_8K_FRAGMENT_SCHEMA_INVALID") from None
        if not name or filing_from > filing_to:
            raise ValueError("SEC_8K_FRAGMENT_SCHEMA_INVALID")
        if filing_from <= end and filing_to >= start:
            selected.append(name)
    if len(selected) != len(set(selected)):
        raise ValueError("SEC_8K_FRAGMENT_DUPLICATE")
    return tuple(selected)


def parse_items(value: object) -> tuple[str, ...]:
    """Parse the SEC comma-delimited items field without inference."""
    if value is None or pd.isna(value):
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for part in str(value).split(","):
        item = part.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _rejection(
    *, source: str, cik: int, accession: str, reason: str
) -> dict[str, object]:
    return {
        "source": source,
        "cik": cik,
        "accession_number": accession,
        "reason": reason,
    }


def normalize_8k_filings(
    responses: Iterable[tuple[str, dict[str, object]]],
    identities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize original categorized 8-Ks and preserve excluded rows."""
    if missing := {"symbol", "cik"}.difference(identities.columns):
        raise ValueError(f"SEC_8K_IDENTITY_COLUMNS_MISSING:{sorted(missing)}")
    identity = identities[["symbol", "cik"]].copy()
    identity["symbol"] = identity["symbol"].astype(str)
    identity["cik"] = pd.to_numeric(identity["cik"], errors="raise").astype("int64")
    identity = identity.drop_duplicates().sort_values(["cik", "symbol"])
    records: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    accession_metadata: dict[tuple[int, str], tuple[object, ...]] = {}
    accepted_keys: set[tuple[int, str]] = set()
    for source, payload in responses:
        validate_submission_response(payload, source)
        try:
            cik = int(payload["cik"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"SEC_8K_CIK_INVALID:{source}") from None
        recent = _recent(payload)
        issuer_symbols = identity.loc[identity["cik"].eq(cik), "symbol"].tolist()
        for index in range(len(recent["accessionNumber"])):
            accession = str(recent["accessionNumber"][index]).strip()
            form = str(recent["form"][index]).strip()
            items = parse_items(recent["items"][index])
            metadata = tuple(recent[column][index] for column in REQUIRED_COLUMNS[1:])
            key = (cik, accession)
            prior = accession_metadata.get(key)
            if prior is not None and prior != metadata:
                raise ValueError(f"SEC_8K_ACCESSION_CONFLICT:{cik}:{accession}")
            accession_metadata[key] = metadata
            if key in accepted_keys:
                continue
            if not issuer_symbols:
                rejected.append(
                    _rejection(
                        source=source,
                        cik=cik,
                        accession=accession,
                        reason="SEC_8K_CIK_UNMATCHED",
                    )
                )
                continue
            if form == "8-K/A":
                rejected.append(
                    _rejection(
                        source=source,
                        cik=cik,
                        accession=accession,
                        reason="SEC_8K_AMENDMENT_AUDIT_ONLY",
                    )
                )
                continue
            if form != "8-K":
                continue
            categories = {
                category: item in items for category, item in CATEGORY_ITEMS.items()
            }
            if not any(categories.values()):
                rejected.append(
                    _rejection(
                        source=source,
                        cik=cik,
                        accession=accession,
                        reason="SEC_8K_NO_FROZEN_CATEGORY",
                    )
                )
                continue
            try:
                filing_date = pd.Timestamp(recent["filingDate"][index]).date()
                report_value = recent["reportDate"][index]
                report_date = (
                    pd.Timestamp(report_value).date()
                    if str(report_value).strip()
                    else None
                )
                acceptance_timestamp = pd.to_datetime(
                    str(recent["acceptanceDateTime"][index]),
                    format="mixed",
                    errors="raise",
                    utc=True,
                )
                size = int(recent["size"][index])
            except (TypeError, ValueError):
                rejected.append(
                    _rejection(
                        source=source,
                        cik=cik,
                        accession=accession,
                        reason="SEC_8K_METADATA_INVALID",
                    )
                )
                continue
            if not date(2021, 1, 1) <= filing_date <= date(2023, 12, 31):
                continue
            for symbol in issuer_symbols:
                records.append(
                    {
                        "symbol": symbol,
                        "cik": cik,
                        "accession_number": accession,
                        "filing_date": filing_date,
                        "report_date": report_date,
                        "acceptance_timestamp": acceptance_timestamp,
                        "form": form,
                        "items": items,
                        "size": size,
                        "primary_document": str(
                            recent["primaryDocument"][index]
                        ),
                        "source": source,
                        **categories,
                    }
                )
            accepted_keys.add(key)
    filings = pd.DataFrame.from_records(records)
    if not filings.empty:
        filings = filings.sort_values(
            ["symbol", "acceptance_timestamp", "accession_number"]
        ).reset_index(drop=True)
    rejection_frame = pd.DataFrame.from_records(
        rejected, columns=["source", "cik", "accession_number", "reason"]
    )
    return filings, rejection_frame


def build_event_features(
    events: pd.DataFrame,
    filings: pd.DataFrame,
    identities: pd.DataFrame,
) -> pd.DataFrame:
    """Project accepted 8-K categories onto the next three sample sessions."""
    event_required = {"symbol", "session_date", "bar_idx"}
    if missing := event_required.difference(events.columns):
        raise ValueError(f"SEC_8K_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    filing_required = {
        "symbol",
        "cik",
        "accession_number",
        "acceptance_timestamp",
        "items",
        "size",
        *CATEGORY_ITEMS,
    }
    if missing := filing_required.difference(filings.columns):
        raise ValueError(f"SEC_8K_FILING_COLUMNS_MISSING:{sorted(missing)}")
    result = events.copy()
    result["symbol"] = result["symbol"].astype(str)
    identity_map = identities[["symbol", "cik"]].copy()
    identity_map["symbol"] = identity_map["symbol"].astype(str)
    if identity_map["symbol"].duplicated().any():
        raise ValueError("SEC_8K_IDENTITY_SYMBOL_DUPLICATE")
    result["sec_8k_cik"] = result["symbol"].map(
        identity_map.set_index("symbol")["cik"]
    )
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="raise"
    ).dt.date
    result = result.loc[
        result["session_date"].map(
            lambda value: date(2021, 1, 1) <= value <= date(2023, 12, 31)
        )
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("SEC_8K_EVENT_KEY_DUPLICATE")
    source = filings.copy()
    source["symbol"] = source["symbol"].astype(str)
    source["acceptance_timestamp"] = pd.to_datetime(
        source["acceptance_timestamp"], errors="raise", utc=True
    )
    if source.duplicated(["symbol", "accession_number"]).any():
        raise ValueError("SEC_8K_SYMBOL_ACCESSION_DUPLICATE")
    filing_counts = (
        source.groupby("symbol", observed=True)["accession_number"].nunique()
    )
    result["sec_8k_categorized_filing_count"] = (
        result["symbol"].map(filing_counts).fillna(0).astype("int64")
    )
    sessions = sorted(result["session_date"].unique())
    session_positions = {session: index for index, session in enumerate(sessions)}
    active_records: list[dict[str, object]] = []
    for filing in source.itertuples(index=False):
        acceptance_date = filing.acceptance_timestamp.date()
        available = next(
            (session for session in sessions if session > acceptance_date), None
        )
        if available is None:
            continue
        start = session_positions[available]
        for session in sessions[start : start + 3]:
            active_records.append(
                {
                    "symbol": filing.symbol,
                    "session_date": session,
                    "accession_number": filing.accession_number,
                    "acceptance_timestamp": filing.acceptance_timestamp,
                    "item_count": len(filing.items),
                    "size": filing.size,
                    **{
                        category: bool(getattr(filing, category))
                        for category in CATEGORY_ITEMS
                    },
                }
            )
    active = pd.DataFrame.from_records(active_records)
    if not active.empty:
        records: list[dict[str, object]] = []
        for (symbol, session), group in active.groupby(
            ["symbol", "session_date"], sort=True, observed=True
        ):
            latest = group["acceptance_timestamp"].max()
            records.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "sec_8k_active_accessions": tuple(
                        sorted(group["accession_number"].astype(str).unique())
                    ),
                    "sec_8k_latest_acceptance_timestamp": latest,
                    "sec_8k_active_filing_count": int(
                        group["accession_number"].nunique()
                    ),
                    "sec_8k_active_item_count": int(group["item_count"].sum()),
                    "sec_8k_log1p_size": float(
                        np.log1p(pd.to_numeric(group["size"]).sum())
                    ),
                    "sec_8k_days_since_latest_acceptance": int(
                        (session - latest.date()).days
                    ),
                    **{
                        f"sec_8k_{category}": int(group[category].any())
                        for category in CATEGORY_ITEMS
                    },
                }
            )
        aggregated = pd.DataFrame.from_records(records)
        result = result.merge(
            aggregated,
            how="left",
            on=["symbol", "session_date"],
            validate="many_to_one",
        )
    else:
        result["sec_8k_active_accessions"] = pd.NA
        result["sec_8k_latest_acceptance_timestamp"] = pd.NaT
        result["sec_8k_active_filing_count"] = np.nan
        result["sec_8k_active_item_count"] = np.nan
        result["sec_8k_log1p_size"] = np.nan
        result["sec_8k_days_since_latest_acceptance"] = np.nan
        for category in CATEGORY_ITEMS:
            result[f"sec_8k_{category}"] = np.nan
    known = result["symbol"].isin(set(identities["symbol"].astype(str)))
    active_mask = result["sec_8k_active_filing_count"].notna()
    result["coverage_reason"] = np.select(
        [~known, ~active_mask],
        ["SEC_IDENTITY_UNAVAILABLE", "SEC_8K_NO_ACTIVE_FILING"],
        default="COVERED",
    )
    return result
