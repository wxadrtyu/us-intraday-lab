from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from us_intraday_lab.research_shadow import ResearchShadowStore


def _start(store: ResearchShadowStore) -> str:
    return store.start_campaign(
        proposal_sha256="a" * 64,
        selection_sha256="b" * 64,
        winner_id="v4-winner",
        parameters={"stock_weight": 0.5},
        start_session_not_before=date(2026, 8, 11),
        minimum_sessions=120,
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_research_shadow_is_idempotent_append_only_and_has_no_order_route(
    tmp_path: Path,
) -> None:
    store = ResearchShadowStore(tmp_path / "research_shadow.sqlite3")
    campaign_id = _start(store)
    assert _start(store) == campaign_id

    observed = {"stock_signal": "AMD", "spy_signal": True, "theoretical_return": 0.01}
    digest = store.record_observation(
        campaign_id=campaign_id,
        session_date=date(2026, 8, 11),
        observation=observed,
        recorded_at=datetime(2026, 8, 11, 21, tzinfo=UTC),
    )
    assert (
        store.record_observation(
            campaign_id=campaign_id,
            session_date=date(2026, 8, 11),
            observation=observed,
            recorded_at=datetime(2026, 8, 12, tzinfo=UTC),
        )
        == digest
    )
    status = store.status(campaign_id)
    assert status.observed_sessions == 1
    assert not status.forward_gate_eligible
    assert status.order_route == "FORBIDDEN"

    with pytest.raises(ValueError, match="append-only"):
        store.record_observation(
            campaign_id=campaign_id,
            session_date=date(2026, 8, 11),
            observation={"stock_signal": "NVDA"},
            recorded_at=datetime(2026, 8, 12, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="order fields"):
        store.record_observation(
            campaign_id=campaign_id,
            session_date=date(2026, 8, 12),
            observation={"order_id": "forbidden"},
            recorded_at=datetime(2026, 8, 12, tzinfo=UTC),
        )


def test_research_shadow_requires_prospective_boundary_and_120_sessions(
    tmp_path: Path,
) -> None:
    store = ResearchShadowStore(tmp_path / "research_shadow.sqlite3")
    campaign_id = _start(store)
    with pytest.raises(ValueError, match="predates"):
        store.record_observation(
            campaign_id=campaign_id,
            session_date=date(2026, 8, 10),
            observation={"stock_signal": None},
            recorded_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="at least 120"):
        store.start_campaign(
            proposal_sha256="c" * 64,
            selection_sha256="d" * 64,
            winner_id="invalid",
            parameters={},
            start_session_not_before=date(2026, 8, 11),
            minimum_sessions=119,
            created_at=datetime(2026, 8, 10, tzinfo=UTC) + timedelta(seconds=1),
        )
