"""Strict USPTO patent-grant data contract for training feasibility."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

LEGAL_SUFFIXES = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "LLC",
    "LP",
    "PLC",
}
ISSUER_MAP_COLUMNS = (
    "raw_assignee_name",
    "issuer_key",
    "symbol",
    "sec_title",
)


def canonicalize_organization(name: str) -> str:
    """Apply the frozen mechanical organization-name canonicalization."""
    normalized = unicodedata.normalize("NFKC", str(name)).upper()
    tokens = re.sub(r"[^A-Z0-9]+", " ", normalized).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def verify_archive(path: Path, expected_md5: str) -> dict[str, object]:
    """Verify publisher MD5 and return an immutable local file inventory."""
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            md5.update(chunk)
            sha256.update(chunk)
            byte_count += len(chunk)
    actual_md5 = md5.hexdigest()
    if actual_md5 != expected_md5.lower():
        raise RuntimeError(f"USPTO_ARCHIVE_MD5_MISMATCH:{path.name}")
    return {
        "path": str(path),
        "bytes": byte_count,
        "md5": actual_md5,
        "sha256": sha256.hexdigest(),
    }


def build_issuer_map(
    sec_identities: pd.DataFrame,
    assignees: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map raw assignee names to SEC titles only through unique exact keys."""
    if missing := {"symbol", "title"}.difference(sec_identities.columns):
        raise ValueError(f"USPTO_SEC_IDENTITY_COLUMNS_MISSING:{sorted(missing)}")
    if "assignee_organization" not in assignees.columns:
        raise ValueError("USPTO_ASSIGNEE_COLUMNS_MISSING:['assignee_organization']")

    sec = sec_identities[["symbol", "title"]].copy()
    sec["symbol"] = sec["symbol"].astype(str)
    sec["title"] = sec["title"].astype(str).str.strip()
    sec["issuer_key"] = sec["title"].map(canonicalize_organization)
    sec = sec.loc[sec["issuer_key"].ne("")].drop_duplicates()
    raw = assignees[["assignee_organization"]].copy()
    raw["raw_assignee_name"] = raw["assignee_organization"].fillna("").astype(str).str.strip()
    raw["issuer_key"] = raw["raw_assignee_name"].map(canonicalize_organization)
    raw = raw[["raw_assignee_name", "issuer_key"]].drop_duplicates()

    sec_title_counts = sec.groupby("issuer_key", observed=True)["title"].nunique()
    raw_name_counts = raw.loc[raw["issuer_key"].ne("")].groupby(
        "issuer_key", observed=True
    )["raw_assignee_name"].nunique()
    accepted_keys = set(sec_title_counts.loc[sec_title_counts.eq(1)].index).intersection(
        raw_name_counts.loc[raw_name_counts.eq(1)].index
    )
    mapping = (
        raw.loc[raw["issuer_key"].isin(accepted_keys)]
        .merge(
            sec.loc[sec["issuer_key"].isin(accepted_keys)],
            on="issuer_key",
            how="inner",
            validate="one_to_many",
        )
        .rename(columns={"title": "sec_title"})
        .loc[:, list(ISSUER_MAP_COLUMNS)]
        .sort_values(["raw_assignee_name", "symbol"])
        .reset_index(drop=True)
    )

    rejected: list[dict[str, object]] = []
    for row in raw.itertuples(index=False):
        key = row.issuer_key
        if not key:
            reason = "USPTO_ASSIGNEE_ORGANIZATION_BLANK"
        elif raw_name_counts.get(key, 0) > 1:
            reason = "USPTO_ASSIGNEE_KEY_AMBIGUOUS"
        elif sec_title_counts.get(key, 0) > 1:
            reason = "USPTO_SEC_ISSUER_KEY_AMBIGUOUS"
        elif key not in sec_title_counts.index:
            reason = "USPTO_ASSIGNEE_UNMAPPED"
        else:
            continue
        rejected.append(
            {
                "raw_assignee_name": row.raw_assignee_name,
                "issuer_key": key,
                "reason": reason,
            }
        )
    return mapping, pd.DataFrame.from_records(
        rejected, columns=["raw_assignee_name", "issuer_key", "reason"]
    )


def normalize_grants(
    patents: pd.DataFrame,
    assignees: pd.DataFrame,
    issuer_map: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join exact patent IDs and retain only strict mapped 2021-2023 grants."""
    patent_columns = {"patent_id", "patent_type", "patent_date", "patent_title"}
    if missing := patent_columns.difference(patents.columns):
        raise ValueError(f"USPTO_PATENT_COLUMNS_MISSING:{sorted(missing)}")
    assignee_columns = {
        "patent_id",
        "assignee_sequence",
        "assignee_organization",
    }
    if missing := assignee_columns.difference(assignees.columns):
        raise ValueError(f"USPTO_ASSIGNEE_COLUMNS_MISSING:{sorted(missing)}")
    if missing := set(ISSUER_MAP_COLUMNS).difference(issuer_map.columns):
        raise ValueError(f"USPTO_ISSUER_MAP_COLUMNS_MISSING:{sorted(missing)}")

    patent = patents[list(patent_columns)].copy()
    patent["patent_id"] = patent["patent_id"].astype(str)
    patent = patent.drop_duplicates()
    if patent["patent_id"].duplicated().any():
        conflict = patent.loc[patent["patent_id"].duplicated(False), "patent_id"].iat[0]
        raise ValueError(f"USPTO_PATENT_METADATA_CONFLICT:{conflict}")

    assignment = assignees[list(assignee_columns)].copy()
    assignment["patent_id"] = assignment["patent_id"].astype(str)
    assignment["assignee_organization"] = (
        assignment["assignee_organization"].fillna("").astype(str).str.strip()
    )
    assignment = assignment.drop_duplicates()
    if assignment.duplicated(["patent_id", "assignee_sequence"]).any():
        raise ValueError("USPTO_ASSIGNEE_METADATA_CONFLICT")

    joined = assignment.merge(
        patent, how="left", on="patent_id", validate="many_to_one", indicator=True
    )
    rejections: list[dict[str, object]] = []
    for row in joined.loc[joined["_merge"].ne("both")].itertuples(index=False):
        rejections.append(
            {
                "patent_id": row.patent_id,
                "assignee_sequence": row.assignee_sequence,
                "assignee_organization": row.assignee_organization,
                "reason": "USPTO_PATENT_ID_UNMATCHED",
            }
        )
    joined = joined.loc[joined["_merge"].eq("both")].drop(columns="_merge")
    mapped_names = set(issuer_map["raw_assignee_name"].astype(str))
    for row in joined.loc[
        ~joined["assignee_organization"].isin(mapped_names)
    ].itertuples(index=False):
        rejections.append(
            {
                "patent_id": row.patent_id,
                "assignee_sequence": row.assignee_sequence,
                "assignee_organization": row.assignee_organization,
                "reason": "USPTO_ASSIGNEE_UNMAPPED",
            }
        )
    joined = joined.loc[joined["assignee_organization"].isin(mapped_names)]
    joined["patent_date"] = pd.to_datetime(
        joined["patent_date"], errors="raise"
    ).dt.date
    joined = joined.loc[
        joined["patent_date"].map(
            lambda value: date(2021, 1, 1) <= value <= date(2023, 12, 31)
        )
    ]
    grants = (
        joined.merge(
            issuer_map,
            how="inner",
            left_on="assignee_organization",
            right_on="raw_assignee_name",
            validate="many_to_many",
        )
        .loc[
            :,
            [
                "symbol",
                "sec_title",
                "issuer_key",
                "patent_id",
                "patent_type",
                "patent_date",
                "patent_title",
                "assignee_sequence",
                "raw_assignee_name",
            ],
        ]
        .sort_values(["symbol", "patent_date", "patent_id", "assignee_sequence"])
        .reset_index(drop=True)
    )
    rejection_frame = pd.DataFrame.from_records(
        rejections,
        columns=[
            "patent_id",
            "assignee_sequence",
            "assignee_organization",
            "reason",
        ],
    )
    return grants, rejection_frame
