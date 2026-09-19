"""SEC Schedule 13D/13G data contract for training feasibility."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import numpy as np
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


def build_event_features(
    events: pd.DataFrame,
    filings: pd.DataFrame,
    identities: pd.DataFrame,
) -> pd.DataFrame:
    """Project accepted ownership filings onto five causal sample sessions."""
    event_required = {"symbol", "session_date", "bar_idx"}
    if missing := event_required.difference(events.columns):
        raise ValueError(f"SEC_BENEFICIAL_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    filing_required = {
        "symbol",
        "cik",
        "accession_number",
        "acceptance_timestamp",
        *FORM_FLAGS.values(),
    }
    if missing := filing_required.difference(filings.columns):
        raise ValueError(f"SEC_BENEFICIAL_FILING_COLUMNS_MISSING:{sorted(missing)}")
    if missing := {"symbol", "cik"}.difference(identities.columns):
        raise ValueError(f"SEC_BENEFICIAL_IDENTITY_COLUMNS_MISSING:{sorted(missing)}")

    result = events.copy()
    result["symbol"] = result["symbol"].astype(str)
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="raise"
    ).dt.date
    result = result.loc[
        result["session_date"].map(
            lambda value: date(2021, 1, 1) <= value <= date(2023, 12, 31)
        )
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("SEC_BENEFICIAL_EVENT_KEY_DUPLICATE")

    identity = identities[["symbol", "cik"]].copy()
    identity["symbol"] = identity["symbol"].astype(str)
    identity["cik"] = pd.to_numeric(identity["cik"], errors="raise").astype("int64")
    if identity["symbol"].duplicated().any():
        raise ValueError("SEC_BENEFICIAL_IDENTITY_SYMBOL_DUPLICATE")
    identity_map = identity.set_index("symbol")["cik"]
    result["sec_beneficial_cik"] = result["symbol"].map(identity_map)

    source = filings.copy()
    source["symbol"] = source["symbol"].astype(str)
    source["cik"] = pd.to_numeric(source["cik"], errors="raise").astype("int64")
    source["acceptance_timestamp"] = pd.to_datetime(
        source["acceptance_timestamp"], errors="raise", utc=True
    )
    if source.duplicated(["symbol", "accession_number"]).any():
        raise ValueError("SEC_BENEFICIAL_SYMBOL_ACCESSION_DUPLICATE")
    expected_cik = source["symbol"].map(identity_map)
    if expected_cik.isna().any() or not expected_cik.astype("int64").equals(source["cik"]):
        raise ValueError("SEC_BENEFICIAL_FILING_IDENTITY_MISMATCH")

    filing_counts = source.groupby("symbol", observed=True)[
        "accession_number"
    ].nunique()
    result["sec_beneficial_qualifying_filing_count"] = (
        result["symbol"].map(filing_counts).fillna(0).astype("int64")
    )
    sessions = sorted(result["session_date"].unique())
    session_positions = {session: index for index, session in enumerate(sessions)}
    availability: dict[str, list[int]] = {}
    active_records: list[dict[str, object]] = []
    for filing in source.itertuples(index=False):
        available = next(
            (
                session
                for session in sessions
                if session > filing.acceptance_timestamp.date()
            ),
            None,
        )
        if available is None:
            continue
        start = session_positions[available]
        availability.setdefault(str(filing.symbol), []).append(start)
        for session in sessions[start : start + 5]:
            active_records.append(
                {
                    "symbol": filing.symbol,
                    "session_date": session,
                    "accession_number": filing.accession_number,
                    "acceptance_timestamp": filing.acceptance_timestamp,
                    **{
                        flag: bool(getattr(filing, flag))
                        for flag in FORM_FLAGS.values()
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
            position = session_positions[session]
            prior_count = sum(
                position - 19 <= value <= position
                for value in availability[str(symbol)]
            )
            records.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "sec_beneficial_active_accessions": tuple(
                        sorted(group["accession_number"].astype(str).unique())
                    ),
                    "sec_beneficial_latest_acceptance_timestamp": latest,
                    "sec_beneficial_active_filing_count": int(
                        group["accession_number"].nunique()
                    ),
                    "sec_beneficial_days_since_latest_acceptance": int(
                        (session - latest.date()).days
                    ),
                    "sec_beneficial_prior_20_session_filing_count": prior_count,
                    "sec_beneficial_clustered": int(prior_count >= 2),
                    **{
                        f"sec_beneficial_{flag}": int(group[flag].any())
                        for flag in FORM_FLAGS.values()
                    },
                }
            )
        result = result.merge(
            pd.DataFrame.from_records(records),
            how="left",
            on=["symbol", "session_date"],
            validate="many_to_one",
        )
    else:
        result["sec_beneficial_active_accessions"] = pd.NA
        result["sec_beneficial_latest_acceptance_timestamp"] = pd.NaT
        result["sec_beneficial_active_filing_count"] = np.nan
        result["sec_beneficial_days_since_latest_acceptance"] = np.nan
        result["sec_beneficial_prior_20_session_filing_count"] = np.nan
        result["sec_beneficial_clustered"] = np.nan
        for flag in FORM_FLAGS.values():
            result[f"sec_beneficial_{flag}"] = np.nan

    known = result["symbol"].isin(set(identity["symbol"]))
    active_mask = result["sec_beneficial_active_filing_count"].notna()
    result["coverage_reason"] = np.select(
        [~known, ~active_mask],
        ["SEC_IDENTITY_UNAVAILABLE", "SEC_BENEFICIAL_NO_ACTIVE_FILING"],
        default="COVERED",
    )
    return result
