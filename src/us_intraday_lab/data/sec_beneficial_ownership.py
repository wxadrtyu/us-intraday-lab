"""SEC Schedule 13D/13G data contract for training feasibility."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import pandas as pd

from us_intraday_lab.data.sec_8k_events import REQUIRED_COLUMNS, validate_submission_response

QUALIFYING_FORMS = ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A")
FORM_FLAGS = {
    "SC 13D": "sc13d",
    "SC 13D/A": "sc13d_amendment",
    "SC 13G": "sc13g",
    "SC 13G/A": "sc13g_amendment",
}


def _recent(payload: dict[str, object]) -> dict[str, list[object]]:
    filings = payload.get("filings")
    if isinstance(filings, dict):
        candidate = filings.get("recent")
    else:
        candidate = payload
    if not isinstance(candidate, dict):
        raise TypeError("SEC_BENEFICIAL_SCHEMA_INVALID")
    return candidate  # type: ignore[return-value]


def normalize_filings(
    responses: Iterable[tuple[str, int, dict[str, object]]],
    identities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize exact Schedule 13D/13G forms and preserve exclusions."""
    if missing := {"symbol", "cik"}.difference(identities.columns):
        raise ValueError(f"SEC_BENEFICIAL_IDENTITY_COLUMNS_MISSING:{sorted(missing)}")
    identity = identities[["symbol", "cik"]].copy()
    identity["symbol"] = identity["symbol"].astype(str)
    identity["cik"] = pd.to_numeric(identity["cik"], errors="raise").astype("int64")
    identity = identity.drop_duplicates().sort_values(["cik", "symbol"])
    records: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    metadata_by_accession: dict[tuple[int, str], tuple[object, ...]] = {}
    accepted: set[tuple[int, str]] = set()
    for source, cik, payload in responses:
        validate_submission_response(payload, source)
        recent = _recent(payload)
        symbols = identity.loc[identity["cik"].eq(int(cik)), "symbol"].tolist()
        for index in range(len(recent["accessionNumber"])):
            accession = str(recent["accessionNumber"][index]).strip()
            form = str(recent["form"][index]).strip()
            metadata = tuple(recent[column][index] for column in REQUIRED_COLUMNS[1:])
            key = (int(cik), accession)
            prior = metadata_by_accession.get(key)
            if prior is not None and prior != metadata:
                raise ValueError(
                    f"SEC_BENEFICIAL_ACCESSION_CONFLICT:{cik}:{accession}"
                )
            metadata_by_accession[key] = metadata
            if key in accepted:
                continue
            rejection = {
                "source": source,
                "cik": int(cik),
                "accession_number": accession,
                "form": form,
            }
            if not symbols:
                rejected.append(
                    {**rejection, "reason": "SEC_BENEFICIAL_CIK_UNMATCHED"}
                )
                continue
            if form not in QUALIFYING_FORMS:
                rejected.append(
                    {
                        **rejection,
                        "reason": "SEC_BENEFICIAL_FORM_NOT_QUALIFYING",
                    }
                )
                continue
            try:
                filing_date = pd.Timestamp(recent["filingDate"][index]).date()
                acceptance_timestamp = pd.to_datetime(
                    str(recent["acceptanceDateTime"][index]),
                    format="mixed",
                    errors="raise",
                    utc=True,
                )
            except (TypeError, ValueError):
                rejected.append(
                    {**rejection, "reason": "SEC_BENEFICIAL_METADATA_INVALID"}
                )
                continue
            if not date(2021, 1, 1) <= filing_date <= date(2023, 12, 31):
                continue
            flags = {flag: form == exact for exact, flag in FORM_FLAGS.items()}
            for symbol in symbols:
                records.append(
                    {
                        "symbol": symbol,
                        "cik": int(cik),
                        "accession_number": accession,
                        "filing_date": filing_date,
                        "acceptance_timestamp": acceptance_timestamp,
                        "form": form,
                        "source": source,
                        **flags,
                    }
                )
            accepted.add(key)
    filings = pd.DataFrame.from_records(records)
    if not filings.empty:
        filings = filings.sort_values(
            ["symbol", "acceptance_timestamp", "accession_number"]
        ).reset_index(drop=True)
    rejection_frame = pd.DataFrame.from_records(
        rejected,
        columns=["source", "cik", "accession_number", "form", "reason"],
    )
    return filings, rejection_frame
