from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from us_intraday_lab.data.sec_8k_events import (
    build_event_features,
    normalize_8k_filings,
    parse_items,
    select_training_fragments,
    validate_submission_response,
)

REQUIRED_RECENT = {
    "accessionNumber": ["0000000001-22-000001"],
    "filingDate": ["2022-02-01"],
    "reportDate": ["2022-01-31"],
    "acceptanceDateTime": ["20220201163000"],
    "form": ["8-K"],
    "items": ["2.02, 9.01"],
    "size": [1234],
    "primaryDocument": ["event.htm"],
}


def submission_payload(
    *,
    cik: int = 1,
    recent: dict[str, list[object]] | None = None,
    files: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "cik": str(cik),
        "filings": {
            "recent": recent if recent is not None else REQUIRED_RECENT,
            "files": files or [],
        },
    }


def test_fragment_selection_uses_only_declared_training_intersections() -> None:
    payload = submission_payload(
        files=[
            {
                "name": "old.json",
                "filingFrom": "2018-01-01",
                "filingTo": "2020-12-31",
            },
            {
                "name": "train.json",
                "filingFrom": "2021-01-01",
                "filingTo": "2022-06-30",
            },
            {
                "name": "later.json",
                "filingFrom": "2024-01-01",
                "filingTo": "2025-01-01",
            },
        ]
    )

    assert select_training_fragments(
        payload, date(2021, 1, 1), date(2023, 12, 31)
    ) == ("train.json",)


def test_item_parser_is_exact_trimmed_and_deduplicated() -> None:
    assert parse_items("2.02, 9.01,2.02") == ("2.02", "9.01")
    assert parse_items("") == ()
    assert parse_items(None) == ()


def test_submission_validation_rejects_parallel_array_mismatch() -> None:
    recent = {key: list(value) for key, value in REQUIRED_RECENT.items()}
    recent["form"] = []

    with pytest.raises(ValueError, match="SEC_8K_COLUMN_LENGTH_MISMATCH"):
        validate_submission_response(submission_payload(recent=recent), "current")


def test_normalizer_keeps_original_and_preserves_amendment_as_rejection() -> None:
    recent = {
        key: [value[0], value[0]] for key, value in REQUIRED_RECENT.items()
    }
    recent["accessionNumber"] = ["acc-original", "acc-amended"]
    recent["form"] = ["8-K", "8-K/A"]
    recent["items"] = ["2.02,8.01", "2.02"]
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    filings, rejected = normalize_8k_filings(
        [("current", submission_payload(recent=recent))], identities
    )

    assert filings[["symbol", "accession_number"]].to_dict("records") == [
        {"symbol": "AAA", "accession_number": "acc-original"}
    ]
    assert filings.loc[0, "earnings_results"]
    assert filings.loc[0, "other_material_event"]
    assert rejected[["accession_number", "reason"]].to_dict("records") == [
        {"accession_number": "acc-amended", "reason": "SEC_8K_AMENDMENT_AUDIT_ONLY"}
    ]


def test_normalizer_duplicates_explicit_shared_cik_and_not_unmatched_cik() -> None:
    identities = pd.DataFrame(
        {"symbol": ["AAA", "AAB"], "cik": [1, 1]}
    )

    filings, rejected = normalize_8k_filings(
        [
            ("matched", submission_payload(cik=1)),
            ("unmatched", submission_payload(cik=2)),
        ],
        identities,
    )

    assert filings["symbol"].tolist() == ["AAA", "AAB"]
    assert rejected.loc[rejected["source"].eq("unmatched"), "reason"].tolist() == [
        "SEC_8K_CIK_UNMATCHED"
    ]


def test_normalizer_rejects_conflicting_duplicate_accession() -> None:
    first = submission_payload()
    second_recent = {key: list(value) for key, value in REQUIRED_RECENT.items()}
    second_recent["items"] = ["1.01"]
    second = submission_payload(recent=second_recent)
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    with pytest.raises(ValueError, match="SEC_8K_ACCESSION_CONFLICT"):
        normalize_8k_filings([("first", first), ("second", second)], identities)


def test_normalizer_accepts_official_iso_acceptance_timestamp() -> None:
    recent = {key: list(value) for key, value in REQUIRED_RECENT.items()}
    recent["acceptanceDateTime"] = ["2022-02-01T16:30:00.000Z"]
    identities = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    filings, rejected = normalize_8k_filings(
        [("current", submission_payload(recent=recent))], identities
    )

    assert len(filings) == 1
    assert filings.loc[0, "acceptance_timestamp"].isoformat() == (
        "2022-02-01T16:30:00+00:00"
    )
    assert rejected.empty


def _event_sessions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 5 + ["QQQ"] * 5,
            "session_date": pd.to_datetime(
                [
                    "2022-01-03",
                    "2022-01-04",
                    "2022-01-05",
                    "2022-01-06",
                    "2022-01-07",
                ]
                * 2
            ).date,
            "bar_idx": [2] * 10,
        }
    )


def _filing(accession: str = "acc-1") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "cik": [1],
            "accession_number": [accession],
            "filing_date": [date(2022, 1, 3)],
            "report_date": [date(2022, 1, 3)],
            "acceptance_timestamp": [pd.Timestamp("2022-01-03T12:00:00Z")],
            "items": [("2.02", "8.01")],
            "size": [999],
            "earnings_results": [True],
            "material_agreement": [False],
            "acquisition_disposition": [False],
            "director_officer_change": [False],
            "other_material_event": [True],
        }
    )


def test_event_state_starts_next_session_and_expires_after_three() -> None:
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    result = build_event_features(_event_sessions(), _filing(), identity)

    aaa = result.loc[result["symbol"].eq("AAA")].reset_index(drop=True)
    qqq = result.loc[result["symbol"].eq("QQQ")]
    assert aaa.loc[0, "coverage_reason"] == "SEC_8K_NO_ACTIVE_FILING"
    assert aaa["sec_8k_cik"].eq(1).all()
    assert aaa.loc[1:3, "sec_8k_earnings_results"].eq(1).all()
    assert aaa.loc[1:3, "sec_8k_other_material_event"].eq(1).all()
    assert aaa.loc[4, "coverage_reason"] == "SEC_8K_NO_ACTIVE_FILING"
    assert qqq["coverage_reason"].eq("SEC_IDENTITY_UNAVAILABLE").all()


def test_raw_filing_inventory_survives_event_projection() -> None:
    filings = pd.concat(
        [_filing("acc-1"), _filing("acc-2"), _filing("acc-3")],
        ignore_index=True,
    )
    identity = pd.DataFrame({"symbol": ["AAA"], "cik": [1]})

    result = build_event_features(_event_sessions(), filings, identity)

    aaa = result.loc[result["symbol"].eq("AAA")]
    assert aaa["sec_8k_categorized_filing_count"].eq(3).all()
    active = aaa.loc[aaa["coverage_reason"].eq("COVERED")].iloc[0]
    assert active["sec_8k_active_filing_count"] == 3
    assert active["sec_8k_active_item_count"] == 6
    assert active["sec_8k_active_accessions"] == ("acc-1", "acc-2", "acc-3")
