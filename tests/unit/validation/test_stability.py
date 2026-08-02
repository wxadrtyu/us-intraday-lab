import math

import pytest

from us_intraday_lab.validation.stability import (
    PRODUCTION_SYMBOLS,
    PerturbationObservation,
    StartDateObservation,
    assess_parameter_neighborhood,
    assess_start_date_sensitivity,
    assess_symbol_concentration,
)


def _observation(observation_id: str, net_return: float, drawdown: float) -> PerturbationObservation:
    return PerturbationObservation(
        observation_id=observation_id,
        net_return=net_return,
        max_drawdown=drawdown,
    )


def test_parameter_neighborhood_passes_on_profitable_drawdown_safe_plateau() -> None:
    neighbors = (
        _observation("rsi=40", 0.03, 0.04),
        _observation("rsi=45", 0.01, 0.07),
        _observation("rsi=50", -0.002, 0.06),
    )

    result = assess_parameter_neighborhood(
        neighbors,
        required_profitable_fraction=2 / 3,
        max_drawdown=0.08,
    )

    assert result.passed is True
    assert result.reason_code == "STABLE_PARAMETER_NEIGHBORHOOD"
    assert result.profitable_count == 2
    assert result.observations == neighbors


def test_parameter_neighborhood_rejects_isolated_optimum_and_drawdown_breach() -> None:
    isolated = assess_parameter_neighborhood(
        (
            _observation("left", -0.01, 0.03),
            _observation("center", 0.05, 0.04),
            _observation("right", -0.02, 0.02),
        ),
        required_profitable_fraction=0.6,
        max_drawdown=0.08,
    )
    breached = assess_parameter_neighborhood(
        (
            _observation("left", 0.01, 0.081),
            _observation("center", 0.05, 0.04),
            _observation("right", 0.02, 0.02),
        ),
        required_profitable_fraction=0.6,
        max_drawdown=0.08,
    )

    assert isolated.passed is False
    assert isolated.reason_code == "UNSTABLE_PARAMETER_NEIGHBORHOOD"
    assert breached.passed is False
    assert breached.reason_code == "UNSTABLE_PARAMETER_NEIGHBORHOOD"


def test_parameter_neighborhood_requires_multiple_adjacent_observations() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        assess_parameter_neighborhood((_observation("only-optimum", 0.05, 0.02),))


def test_symbol_concentration_uses_positive_profit_and_preserves_losses() -> None:
    result = assess_symbol_concentration(
        {"SPY": 70.0, "QQQ": 30.0, "IWM": -10.0},
        max_positive_profit_share=0.70,
    )

    assert result.passed is True
    assert result.reason_code == "DIVERSIFIED_SYMBOL_PROFIT"
    assert result.total_profit == pytest.approx(90.0)
    assert result.positive_profit == pytest.approx(100.0)
    assert dict(result.profit_by_symbol) == {"SPY": 70.0, "QQQ": 30.0, "IWM": -10.0}
    assert dict(result.positive_profit_share_by_symbol) == {
        "SPY": pytest.approx(0.70),
        "QQQ": pytest.approx(0.30),
        "IWM": pytest.approx(0.0),
    }


@pytest.mark.parametrize(
    "profits",
    [
        {"SPY": 71.0, "QQQ": 29.0, "IWM": -1.0},
        {"SPY": 5.0, "QQQ": -3.0, "IWM": -2.0},
    ],
)
def test_symbol_concentration_rejects_dominance_or_nonpositive_total(
    profits: dict[str, float],
) -> None:
    result = assess_symbol_concentration(profits, max_positive_profit_share=0.70)

    assert result.passed is False
    assert result.reason_code == "SYMBOL_PROFIT_CONCENTRATION"


def test_symbol_concentration_requires_exact_finite_production_evidence() -> None:
    assert PRODUCTION_SYMBOLS == ("SPY", "QQQ", "IWM")
    for invalid in (
        {"SPY": 1.0, "QQQ": 1.0},
        {"SPY": 1.0, "QQQ": 1.0, "IWM": 1.0, "DIA": 1.0},
        {"SPY": 1.0, "QQQ": 1.0, "IWM": math.nan},
        {"SPY": 1.0, "QQQ": True, "IWM": 1.0},
    ):
        with pytest.raises((TypeError, ValueError)):
            assess_symbol_concentration(invalid)


def test_start_date_sensitivity_records_every_configured_offset() -> None:
    offsets = (
        StartDateObservation(offset_sessions=0, net_return=0.03, max_drawdown=0.04),
        StartDateObservation(offset_sessions=5, net_return=0.02, max_drawdown=0.05),
        StartDateObservation(offset_sessions=10, net_return=-0.01, max_drawdown=0.07),
    )

    result = assess_start_date_sensitivity(
        offsets,
        required_profitable_fraction=2 / 3,
        max_drawdown=0.08,
    )

    assert result.passed is True
    assert result.reason_code == "STABLE_START_DATE"
    assert result.observations == offsets
    assert result.profitable_count == 2


def test_start_date_sensitivity_fails_on_majority_or_any_drawdown_breach() -> None:
    unprofitable = assess_start_date_sensitivity(
        (
            StartDateObservation(offset_sessions=0, net_return=0.01, max_drawdown=0.03),
            StartDateObservation(offset_sessions=5, net_return=0.0, max_drawdown=0.04),
            StartDateObservation(offset_sessions=10, net_return=-0.01, max_drawdown=0.05),
        )
    )
    breached = assess_start_date_sensitivity(
        (
            StartDateObservation(offset_sessions=0, net_return=0.01, max_drawdown=0.03),
            StartDateObservation(offset_sessions=5, net_return=0.02, max_drawdown=0.081),
            StartDateObservation(offset_sessions=10, net_return=0.01, max_drawdown=0.05),
        )
    )

    assert unprofitable.reason_code == "START_DATE_INSTABILITY"
    assert unprofitable.passed is False
    assert breached.reason_code == "START_DATE_INSTABILITY"
    assert breached.passed is False


def test_start_date_sensitivity_requires_sorted_unique_exact_offsets() -> None:
    valid = StartDateObservation(offset_sessions=0, net_return=0.01, max_drawdown=0.03)
    invalid_offset = StartDateObservation(offset_sessions=5, net_return=0.01, max_drawdown=0.03)
    object.__setattr__(invalid_offset, "offset_sessions", True)

    for invalid in ((valid, valid), (invalid_offset,), tuple(reversed((valid, invalid_offset)))):
        with pytest.raises((TypeError, ValueError)):
            assess_start_date_sensitivity(invalid)

    with pytest.raises(ValueError, match="at least 2"):
        assess_start_date_sensitivity(
            (StartDateObservation(offset_sessions=0, net_return=0.01, max_drawdown=0.03),)
        )


def test_parameter_neighborhood_revalidates_tampered_frozen_observation() -> None:
    observation = _observation("neighbor", 0.01, 0.03)
    object.__setattr__(observation, "net_return", math.nan)

    with pytest.raises(ValueError, match="finite"):
        assess_parameter_neighborhood((observation, _observation("other", 0.02, 0.02)))


@pytest.mark.parametrize(
    ("neighbors", "fraction", "drawdown"),
    [
        ([], 0.6, 0.08),
        ((_observation("x", 0.1, 0.01),), True, 0.08),
        ((_observation("x", 0.1, 0.01),), 0.5, math.inf),
    ],
)
def test_stability_boundaries_reject_coerced_or_nonfinite_inputs(
    neighbors: object,
    fraction: object,
    drawdown: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        assess_parameter_neighborhood(
            neighbors,  # type: ignore[arg-type]
            required_profitable_fraction=fraction,  # type: ignore[arg-type]
            max_drawdown=drawdown,  # type: ignore[arg-type]
        )
