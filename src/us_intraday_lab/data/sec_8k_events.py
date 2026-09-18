"""Strict SEC submissions contract for structured 8-K training events."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

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
