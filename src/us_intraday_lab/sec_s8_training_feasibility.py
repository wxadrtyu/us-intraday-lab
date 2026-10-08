"""Frozen training-only feasibility diagnostic for exact original SEC Form S-8 events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

FAMILIES = (
    "all_event_continuation",
    "all_event_reversal",
    "first_or_renewal_252_continuation",
    "repeat_252_continuation",
    "clustered_repeat_63_reversal",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
TOP_COUNTS = (1, 3, 5, 10)
TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
STANDARD_EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
DELAY_EXITS = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    decision_bar: int
    holding_bars: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, decision, holding, top_count)
        for family in FAMILIES
        for decision in DECISION_BARS
        for holding in HOLDING_BARS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("SEC_S8_GRID_INVALID")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_coverage(
    path: Path, expected_sha256: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Validate and load the frozen metadata-only coverage artifact."""
    if _sha256(path) != expected_sha256:
        raise RuntimeError("SEC_S8_COVERAGE_HASH_MISMATCH")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    coverage = payload.get("coverage", {})
    if (
        payload.get("status") != "ACCEPTANCE_COVERAGE_COMPLETE"
        or coverage.get("passed") is not True
    ):
        raise RuntimeError("SEC_S8_COVERAGE_NOT_PASSED")
    rows = pd.DataFrame(payload.get("admissible_rows", []))
    required = {
        "symbol",
        "cik",
        "accession",
        "accepted",
        "form",
        "next_sample_session",
        "admissible",
    }
    if not required.issubset(rows.columns):
        raise RuntimeError("SEC_S8_COVERAGE_SCHEMA_INVALID")
    if (
        rows.empty
        or not rows["admissible"].eq(True).all()
        or not rows["form"].eq("S-8").all()
        or rows[["symbol", "accession"]].duplicated().any()
        or rows["accepted"].isna().any()
        or rows["next_sample_session"].isna().any()
        or int(coverage.get("issuer_document_pairs", -1)) != len(rows)
    ):
        raise RuntimeError("SEC_S8_COVERAGE_ROWS_INVALID")
    rows = rows.loc[:, sorted(required)].copy()
    rows["symbol"] = rows["symbol"].astype(str)
    rows["accession"] = rows["accession"].astype(str)
    rows["next_sample_session"] = pd.to_datetime(
        rows["next_sample_session"]
    ).dt.date
    rows["accepted"] = pd.to_datetime(rows["accepted"], errors="raise")
    audit: dict[str, object] = {
        "coverage_passed": True,
        "issuer_document_pairs": len(rows),
        "distinct_issuers": int(rows["symbol"].nunique()),
        "requested": int(payload.get("acquisition", {}).get("requested", 0)),
        "missing_or_invalid": int(
            payload.get("acquisition", {}).get("missing_or_invalid", 0)
        ),
        "original_s8": int(payload.get("source", {}).get("original_s8", 0)),
        "excluded_s8_pos": int(
            payload.get("source", {}).get("excluded_s8_pos", 0)
        ),
    }
    return rows, audit


def build_event_states(
    events: pd.DataFrame, symbol_sessions: pd.DataFrame
) -> pd.DataFrame:
    """Build one causal three-session active-state row per symbol and session."""
    event_required = {"symbol", "accession", "accepted", "next_sample_session"}
    session_required = {"symbol", "session_date"}
    if not event_required.issubset(events.columns):
        raise RuntimeError("SEC_S8_EVENT_SCHEMA_INVALID")
    if not session_required.issubset(symbol_sessions.columns):
        raise RuntimeError("SEC_S8_SESSION_SCHEMA_INVALID")

    sessions = symbol_sessions.loc[:, ["symbol", "session_date"]].copy()
    sessions["symbol"] = sessions["symbol"].astype(str)
    sessions["session_date"] = pd.to_datetime(sessions["session_date"]).dt.date
    if sessions.duplicated().any():
        raise RuntimeError("SEC_S8_SYMBOL_SESSION_DUPLICATE")
    sessions = sessions.sort_values(["symbol", "session_date"], kind="stable")
    sessions["session_ordinal"] = sessions.groupby("symbol", observed=True).cumcount()

    normalized = events.loc[:, sorted(event_required)].copy()
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["accession"] = normalized["accession"].astype(str)
    normalized["next_sample_session"] = pd.to_datetime(
        normalized["next_sample_session"]
    ).dt.date
    if normalized[["symbol", "accession"]].duplicated().any():
        raise RuntimeError("SEC_S8_EVENT_DUPLICATE")
    normalized = normalized.merge(
        sessions,
        left_on=["symbol", "next_sample_session"],
        right_on=["symbol", "session_date"],
        how="left",
        validate="many_to_one",
    )
    if normalized["session_ordinal"].isna().any():
        raise RuntimeError("SEC_S8_AVAILABILITY_SESSION_MISSING")
    normalized["session_ordinal"] = normalized["session_ordinal"].astype(int)

    positions_by_symbol = {
        symbol: sorted(set(group["session_ordinal"].astype(int)))
        for symbol, group in normalized.groupby("symbol", observed=True)
    }
    labeled_records: list[dict[str, object]] = []
    for row in normalized.sort_values(
        ["symbol", "session_ordinal", "accession"], kind="stable"
    ).to_dict("records"):
        position = int(row["session_ordinal"])
        prior = [
            value for value in positions_by_symbol[str(row["symbol"])] if value < position
        ]
        prior_252 = [value for value in prior if value >= position - 252]
        prior_63 = [value for value in prior if value >= position - 63]
        labeled_records.append(
            {
                **row,
                "first_or_renewal_252": position >= 252 and not prior_252,
                "repeat_252": bool(prior_252),
                "clustered_repeat_63": bool(prior_63),
            }
        )
    labeled = pd.DataFrame.from_records(labeled_records)

    session_lookup = {
        (str(row.symbol), int(row.session_ordinal)): row.session_date
        for row in sessions.itertuples(index=False)
    }
    active_records: list[dict[str, object]] = []
    for row in labeled.itertuples(index=False):
        for offset in range(3):
            active_date = session_lookup.get(
                (str(row.symbol), int(row.session_ordinal) + offset)
            )
            if active_date is None:
                break
            active_records.append(
                {
                    "symbol": str(row.symbol),
                    "session_date": active_date,
                    "accession": str(row.accession),
                    "first_or_renewal_252": bool(row.first_or_renewal_252),
                    "repeat_252": bool(row.repeat_252),
                    "clustered_repeat_63": bool(row.clustered_repeat_63),
                }
            )
    active = pd.DataFrame.from_records(active_records)
    if active.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "session_date",
                "active_accessions",
                "first_or_renewal_252",
                "repeat_252",
                "clustered_repeat_63",
            ]
        )
    grouped_records: list[dict[str, object]] = []
    for (symbol, session_date), group in active.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        grouped_records.append(
            {
                "symbol": symbol,
                "session_date": session_date,
                "active_accessions": tuple(sorted(set(group["accession"]))),
                "first_or_renewal_252": bool(group["first_or_renewal_252"].any()),
                "repeat_252": bool(group["repeat_252"].any()),
                "clustered_repeat_63": bool(group["clustered_repeat_63"].any()),
            }
        )
    return pd.DataFrame.from_records(grouped_records).sort_values(
        ["symbol", "session_date"], kind="stable", ignore_index=True
    )
