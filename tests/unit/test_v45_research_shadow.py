from datetime import date

from us_intraday_lab.v45_research_shadow import V45ShadowObservation


def test_v45_shadow_record_preserves_exception_and_has_no_order_fields() -> None:
    observation = V45ShadowObservation(
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

    record = observation.as_record()

    assert record["candidate_id"] == "lev-v45e-0d302fbf92727a31"
    assert record["admission"] == {
        "type": "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION",
        "factory_null_passed": False,
    }
    assert record["theoretical"]["standard_9bp_return"] == 0.01
    assert all("order" not in key.lower() for key in record)
