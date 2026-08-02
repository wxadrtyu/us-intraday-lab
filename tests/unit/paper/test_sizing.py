from __future__ import annotations

from us_intraday_lab.paper.sizing import (
    SizingRequest,
    replay_balance_feasibility,
    size_long_position,
)


def _request(**updates: float) -> SizingRequest:
    values = {
        "available_cash": 10_000.0,
        "account_equity": 10_000.0,
        "reference_price": 101.25,
        "stop_distance": 2.50,
        "strategy_risk_fraction": 0.01,
        "max_position_fraction": 0.25,
    }
    values.update(updates)
    return SizingRequest(**values)


def test_sizing_floors_to_the_most_conservative_integer_cap() -> None:
    result = size_long_position(_request())

    # cash=98, position cap=24, stop-risk cap=40 -> 24 shares.
    assert result.approved is True
    assert result.reason_code == "SIZED_INTEGER_POSITION"
    assert result.quantity == 24
    assert result.required_cash == 2_430.0
    assert result.risk_cash == 60.0
    assert result.binding_cap == "position"


def test_sizing_never_rounds_up_or_borrows_for_one_share() -> None:
    result = size_long_position(
        _request(
            available_cash=100.0,
            account_equity=100.0,
            reference_price=100.01,
            stop_distance=1.0,
            strategy_risk_fraction=0.01,
            max_position_fraction=1.0,
        )
    )

    assert result.approved is False
    assert result.reason_code == "NO_FEASIBLE_INTEGER_POSITION"
    assert result.quantity == 0
    assert result.required_cash == 0.0


def test_balance_replays_are_diagnostics_and_do_not_replace_broker_truth() -> None:
    request = _request(available_cash=7_500.0, account_equity=7_500.0)

    actual = size_long_position(request)
    diagnostics = replay_balance_feasibility(request)

    assert actual.quantity == 18
    assert tuple(item.balance for item in diagnostics) == (5_000.0, 10_000.0, 25_000.0)
    assert tuple(item.quantity for item in diagnostics) == (12, 24, 61)
    assert all(item.diagnostic_only for item in diagnostics)
