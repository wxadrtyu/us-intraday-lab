import pytest
from pydantic import ValidationError

from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal
from us_intraday_lab.long_horizon.variants import generate_long_horizon_variants


def _payload() -> dict[str, object]:
    return {
        "proposal_id": "proposal-a",
        "schema_version": "1.0.0",
        "entry_template": "momentum_5m",
        "symbols": ["AAPL", "QQQ"],
        "parameter_ranges": {
            "return_1_min": {"values": [0.0005, 0.001, 0.0015]},
            "stop_loss_bps": {"values": [30, 50, 70]},
        },
        "max_variants": 12,
        "seed": 17,
        "rationale": "Short bursts with volume confirmation may persist after costs.",
        "provenance": "ai",
    }


@pytest.mark.parametrize(
    "template",
    [
        "trend_pullback_5m",
        "opening_reclaim_5m",
        "vwap_reversion_5m",
        "momentum_5m",
        "cross_rebound_5m",
        "cross_regime_reversal_5m",
        "cross_momentum_5m",
        "relative_laggard_5m",
        "asymmetric_pair_ensemble_5m",
    ],
)
def test_only_approved_five_minute_templates_are_accepted(template: str) -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {**_payload(), "entry_template": template}
    )

    assert proposal.symbols == ("AAPL", "QQQ")
    assert proposal.max_variants <= 50


def test_spy_iwm_proposal_generates_only_the_declared_scope() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {**_payload(), "symbols": ["SPY", "IWM"]}
    )

    assert all(
        variant.symbols == ("SPY", "IWM")
        for variant in generate_long_horizon_variants(proposal)
    )


def test_search_space_requires_three_distinct_neighbors() -> None:
    with pytest.raises(ValidationError, match="three robustness neighbors"):
        LongHorizonHypothesisProposal.model_validate(
            {
                **_payload(),
                "parameter_ranges": {"return_1_min": {"values": [-0.001]}},
            }
        )


def test_variants_are_seeded_bounded_valid_dsl_and_include_neighbors() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(_payload())

    first = generate_long_horizon_variants(proposal)
    second = generate_long_horizon_variants(proposal)

    assert first == second
    assert 4 <= len(first) <= proposal.max_variants
    assert len({item.strategy_id for item in first}) == len(first)
    assert all(item.symbols == ("AAPL", "QQQ") for item in first)
    assert all(item.signal_bar_size == "5min" for item in first)


def test_trend_pullback_omits_optional_ema_filter_when_not_proposed() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "trend_pullback_5m",
            "parameter_ranges": {
                "return_1_max": {"values": [-0.0013, -0.0014]},
                "range_position_max": {"values": [0.075, 0.09]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        indicators = [rule.indicator for rule in variant.entry.all]
        assert "ema_spread" not in indicators
        assert variant.risk.sizing_preset == "equal_cash_conservative"


def test_cross_rebound_uses_only_causal_self_and_peer_features() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "cross_rebound_5m",
            "symbols": ["SPY", "TQQQ"],
            "parameter_ranges": {
                "cross_return_from_open_max": {"values": [-0.002, -0.003]},
                "cross_prior_session_return_max": {"values": [-0.001, -0.002]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        indicators = {rule.indicator for rule in variant.entry.all}
        assert {
            "return_from_open",
            "peer_return_from_open",
            "prior_session_return",
            "peer_prior_session_return",
        }.issubset(indicators)
        assert variant.risk.sizing_preset == "equal_cash_conservative"


def test_cross_regime_reversal_requires_completed_trend_and_peer_features() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "cross_regime_reversal_5m",
            "symbols": ["TQQQ", "SOXL"],
            "parameter_ranges": {
                "cross_return_from_open_min": {"values": [0.0, 0.001]},
                "cross_prior_session_return_max": {"values": [-0.005, -0.01]},
                "cross_trailing_session_return_5_min": {"values": [-0.075]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        indicators = {rule.indicator for rule in variant.entry.all}
        assert {
            "return_from_open",
            "peer_return_from_open",
            "prior_session_return",
            "peer_prior_session_return",
            "trailing_session_return_5",
            "peer_trailing_session_return_5",
        }.issubset(indicators)
        assert variant.risk.sizing_preset == "equal_cash_leveraged_25pct"


def test_cross_momentum_uses_causal_pair_confirmation() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "cross_momentum_5m",
            "symbols": ["SPY", "TQQQ"],
            "parameter_ranges": {
                "cross_return_from_open_min": {"values": [0.001, 0.002]},
                "cross_prior_session_return_min": {"values": [-0.02, -0.01]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        indicators = {rule.indicator for rule in variant.entry.all}
        assert {
            "return_from_open",
            "peer_return_from_open",
            "prior_session_return",
            "peer_prior_session_return",
        }.issubset(indicators)
        assert variant.risk.sizing_preset == "equal_cash_leveraged_25pct"


def test_relative_laggard_enters_only_from_causal_relative_evidence() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "relative_laggard_5m",
            "symbols": ["TQQQ", "SOXL"],
            "parameter_ranges": {
                "relative_return_from_open_max": {"values": [-0.002, -0.005]},
                "return_from_open_min": {"values": [-0.02, -0.01]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        indicators = {rule.indicator for rule in variant.entry.all}
        assert {
            "relative_return_from_open",
            "return_from_open",
            "prior_session_return",
            "peer_prior_session_return",
        }.issubset(indicators)
        assert variant.risk.sizing_preset == "equal_cash_conservative"


def test_asymmetric_pair_ensemble_has_closed_symbol_specific_branches() -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {
            **_payload(),
            "entry_template": "asymmetric_pair_ensemble_5m",
            "symbols": ["TQQQ", "SOXL"],
            "parameter_ranges": {
                "relative_return_from_open_max": {"values": [-0.004, -0.006]},
                "return_from_open_min": {"values": [-0.02, -0.0175]},
            },
            "max_variants": 4,
        }
    )

    for variant in generate_long_horizon_variants(proposal):
        entry_indicators = {
            rule.indicator
            for branch in variant.entry.any
            for rule in branch.all
        }
        exit_indicators = {
            rule.indicator
            for branch in variant.exit.any
            for rule in branch.all
        }
        assert {
            "is_tqqq",
            "is_soxl",
            "trailing_session_return_3",
            "relative_return_from_open",
        }.issubset(entry_indicators)
        assert {"is_tqqq", "is_soxl", "minutes_from_open"}.issubset(exit_indicators)
        assert variant.risk.max_entries_per_session == 1
        assert variant.risk.sizing_preset == "equal_cash_conservative"
