from datetime import date

import pytest

from us_intraday_lab.v45_research_shadow import V45ShadowObservation
from us_intraday_lab.v247_research_shadow import V247ShadowObservation


def test_v247_shadow_record_preserves_every_exception_and_has_no_order_fields() -> None:
    anchor = V45ShadowObservation(
        session_date=date(2026, 8, 17),
        selected_symbol="SOXL",
        decision_bar=23,
        exposure=0.8,
        standard_return=0.01,
        cost_18bp_return=0.009,
        delay_5min_return=0.008,
        benchmark_return=0.002,
        context_sessions=70,
        target_minimum_minutes=300,
    )
    observation = V247ShadowObservation(
        session_date=date(2026, 8, 17),
        anchor=anchor,
        component_selected_symbol="TQQQ",
        component_exposure=0.5,
        component_standard_return=0.02,
        component_cost_18bp_return=0.018,
        component_delay_5min_return=0.016,
        component_benchmark_return=0.004,
    )

    record = observation.as_record()

    assert record["candidate_id"] == "lev-v247-df683b8a37c927f6"
    assert record["admission"] == {
        "type": "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION",
        "inherited_v45_factory_null_passed": False,
        "component_factory_null_passed": True,
        "global_bonferroni_passed": False,
    }
    assert record["theoretical"]["standard_9bp_return"] == pytest.approx(0.0105)
    assert all("order" not in key.lower() for key in record)
