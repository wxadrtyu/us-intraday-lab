from pathlib import Path

import pytest

from us_intraday_lab.long_horizon.final_ledger import (
    CampaignFinalLedger,
    FinalTestIsolationError,
)


def test_campaign_final_cannot_be_consumed_by_second_proposal(tmp_path: Path) -> None:
    ledger = CampaignFinalLedger(tmp_path / "state" / "long_horizon_final.sqlite3")
    token = ledger.reserve(
        dataset_id="dataset-a",
        split_id="split-a",
        survivor_ids=("strategy-a",),
    )
    ledger.consume(token=token, proposal_id="proposal-a", evidence_sha256="a" * 64)

    with pytest.raises(FinalTestIsolationError, match="CAMPAIGN_FINAL_ALREADY_CONSUMED"):
        ledger.reserve(
            dataset_id="dataset-a",
            split_id="split-a",
            survivor_ids=("strategy-b",),
        )


def test_exact_reservation_and_consumption_are_idempotent(tmp_path: Path) -> None:
    ledger = CampaignFinalLedger(tmp_path / "state" / "long_horizon_final.sqlite3")
    expected = ledger.reserve(
        dataset_id="dataset-a",
        split_id="split-a",
        survivor_ids=("strategy-a", "strategy-b"),
    )

    assert ledger.reserve(
        dataset_id="dataset-a",
        split_id="split-a",
        survivor_ids=("strategy-a", "strategy-b"),
    ) == expected
    first = ledger.consume(
        token=expected,
        proposal_id="proposal-a",
        evidence_sha256="b" * 64,
    )
    second = ledger.consume(
        token=expected,
        proposal_id="proposal-a",
        evidence_sha256="b" * 64,
    )
    assert first == second


def test_concurrent_identity_change_cannot_replace_reservation(tmp_path: Path) -> None:
    path = tmp_path / "state" / "long_horizon_final.sqlite3"
    first = CampaignFinalLedger(path)
    second = CampaignFinalLedger(path)
    first.reserve(
        dataset_id="dataset-a",
        split_id="split-a",
        survivor_ids=("strategy-a",),
    )

    with pytest.raises(FinalTestIsolationError, match="CAMPAIGN_FINAL_RESERVATION_MISMATCH"):
        second.reserve(
            dataset_id="dataset-a",
            split_id="split-a",
            survivor_ids=("strategy-b",),
        )

