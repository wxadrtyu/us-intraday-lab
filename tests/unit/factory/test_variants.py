import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.hypotheses import HypothesisProposal
from us_intraday_lab.factory.proposal import FixtureProposalProvider
from us_intraday_lab.factory.variants import (
    deduplicate_variants,
    generate_strategy_variants,
)
from us_intraday_lab.strategy.validator import validate_strategy

FIXTURE = Path(__file__).parents[2] / "fixtures" / "hypotheses" / "momentum_pullback.json"


def _proposal() -> HypothesisProposal:
    return FixtureProposalProvider(FIXTURE).load()


def test_same_proposal_produces_identical_budgeted_valid_variants() -> None:
    proposal = _proposal()

    first = generate_strategy_variants(proposal)
    second = generate_strategy_variants(proposal)

    assert 3 <= len(first) <= proposal.max_variants
    assert [variant.variant_id for variant in first] == [variant.variant_id for variant in second]
    assert [variant.canonical_json() for variant in first] == [
        variant.canonical_json() for variant in second
    ]
    assert all(validate_strategy(variant.definition).passed for variant in first)
    assert first[0].selection_reason == "baseline"
    assert {variant.selection_reason for variant in first} >= {
        "baseline",
        "lower_boundary",
        "upper_boundary",
    }
    for variant in first:
        identity_payload = variant.definition.model_dump(mode="json", exclude={"strategy_id"})
        canonical = json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        assert variant.variant_id == hashlib.sha256(canonical.encode()).hexdigest()[:16]


def test_descriptive_text_does_not_change_variant_ids() -> None:
    proposal = _proposal()
    changed = HypothesisProposal.model_validate(
        {
            **proposal.model_dump(mode="json"),
            "thesis": "Different prose",
            "rationale": "Different descriptive annotation",
        }
    )

    assert [item.variant_id for item in generate_strategy_variants(proposal)] == [
        item.variant_id for item in generate_strategy_variants(changed)
    ]


def test_trend_breakout_template_requires_upward_momentum_and_exits_on_trend_failure() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            **_proposal().model_dump(mode="json"),
            "hypothesis_id": "trend-breakout",
            "entry_template": "trend_breakout",
            "exit_template": "trend_failure",
            "parameter_ranges": {
                "ema_spread_min": {"values": [0.0, 0.001]},
                "rsi_entry": {"values": [40.0, 55.0]},
                "volume_ratio_min": {"values": [1.0, 1.2]},
            },
            "max_variants": 8,
        }
    )

    variants = generate_strategy_variants(proposal)

    for variant in variants:
        entry = variant.definition.entry.model_dump(mode="json")
        assert entry["all"][1]["indicator"] == "rsi"
        assert entry["all"][1]["op"] == "gt"
        assert variant.definition.exit.model_dump(mode="json") == {
            "indicator": "ema_spread",
            "op": "lt",
            "value": 0.0,
        }


def test_trend_dip_template_is_constrained_to_causal_pullback_features() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            **_proposal().model_dump(mode="json"),
            "hypothesis_id": "trend-dip",
            "entry_template": "trend_dip",
            "exit_template": "time_stop",
            "indicators": [
                "ema_spread",
                "return_1",
                "range_position",
                "minutes_from_open",
            ],
            "parameter_ranges": {
                "ema_spread_min": {"values": [0.00025, 0.0005]},
                "return_1_max": {"values": [-0.001, -0.0005]},
                "range_position_max": {"values": [0.2, 0.4]},
                "minutes_from_open_min": {"values": [90, 120]},
            },
            "max_variants": 16,
        }
    )

    for variant in generate_strategy_variants(proposal):
        entry = variant.definition.entry.model_dump(mode="json")["all"]
        assert [(item["indicator"], item["op"]) for item in entry] == [
            ("ema_spread", "gt"),
            ("return_1", "lt"),
            ("range_position", "lt"),
            ("minutes_from_open", "gt"),
        ]
        assert variant.definition.exit.model_dump(mode="json") == {
            "indicator": "minutes_from_open",
            "op": "gte",
            "value": 390.0,
        }


def test_trend_dip_defaults_encode_the_cost_resilient_anchor() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            **_proposal().model_dump(mode="json"),
            "hypothesis_id": "trend-dip-anchor",
            "entry_template": "trend_dip",
            "exit_template": "time_stop",
            "indicators": [
                "ema_spread",
                "return_1",
                "range_position",
                "minutes_from_open",
            ],
            "parameter_ranges": {"max_holding_minutes": {"values": [90, 120, 150]}},
            "max_variants": 3,
        }
    )

    variant = next(
        item for item in generate_strategy_variants(proposal) if item.parameters["max_holding_minutes"] == 120
    )

    assert variant.parameters["stop_loss_bps"] == 100
    assert variant.parameters["take_profit_bps"] == 200
    assert variant.parameters["return_1_max"] == -0.0005
    assert variant.parameters["range_position_max"] == 0.4


def test_oversold_rebound_template_uses_only_causal_oversold_features() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            **_proposal().model_dump(mode="json"),
            "hypothesis_id": "oversold-rebound",
            "entry_template": "oversold_rebound",
            "exit_template": "time_stop",
            "indicators": ["rsi", "vwap_distance_bps", "return_1", "minutes_from_open"],
            "parameter_ranges": {"max_holding_minutes": {"values": [45, 60, 90]}},
            "max_variants": 3,
        }
    )

    for variant in generate_strategy_variants(proposal):
        entry = variant.definition.entry.model_dump(mode="json")["all"]
        assert [(item["indicator"], item["op"]) for item in entry] == [
            ("rsi", "lt"),
            ("vwap_distance_bps", "lt"),
            ("return_1", "lt"),
        ]


def test_late_dip_rebound_defaults_preserve_the_screened_anchor() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            **_proposal().model_dump(mode="json"),
            "hypothesis_id": "late-dip-rebound",
            "entry_template": "late_dip_rebound",
            "exit_template": "time_stop",
            "indicators": [
                "vwap_distance_bps",
                "return_1",
                "range_position",
                "minutes_from_open",
            ],
            "parameter_ranges": {"max_holding_minutes": {"values": [90, 120, 150]}},
            "max_variants": 3,
        }
    )

    anchor = next(
        item for item in generate_strategy_variants(proposal) if item.parameters["max_holding_minutes"] == 120
    )
    assert anchor.parameters["vwap_distance_max"] == -10.0
    assert anchor.parameters["return_1_max"] == -0.001
    assert anchor.parameters["range_position_max"] == 0.3
    assert anchor.parameters["minutes_from_open_min"] == 120


def test_seed_changes_only_over_budget_selected_subset() -> None:
    proposal = _proposal()
    changed_seed = HypothesisProposal.model_validate(
        {**proposal.model_dump(mode="json"), "seed": proposal.seed + 1}
    )

    original_ids = {item.variant_id for item in generate_strategy_variants(proposal)}
    changed_ids = {item.variant_id for item in generate_strategy_variants(changed_seed)}

    assert original_ids != changed_ids
    assert len(original_ids) == len(changed_ids) == proposal.max_variants

    small = HypothesisProposal.model_validate(
        {
            **proposal.model_dump(mode="json"),
            "parameter_ranges": {
                "rsi_entry": {"values": [35.0, 40.0]},
                "stop_loss_bps": {"values": [25, 35]},
            },
            "max_variants": 20,
        }
    )
    small_changed_seed = HypothesisProposal.model_validate(
        {**small.model_dump(mode="json"), "seed": small.seed + 1}
    )
    assert [item.variant_id for item in generate_strategy_variants(small)] == [
        item.variant_id for item in generate_strategy_variants(small_changed_seed)
    ]


def test_duplicate_strategy_definitions_collapse_by_content_hash() -> None:
    variant = generate_strategy_variants(_proposal())[0]

    assert deduplicate_variants((variant, variant, variant)) == (variant,)


def test_generator_rejects_strict_integer_forgery() -> None:
    proposal = _proposal()
    forged = proposal.model_copy(update={"max_variants": True})

    with pytest.raises(ValidationError):
        generate_strategy_variants(forged)

    forged_range = proposal.parameter_ranges["stop_loss_bps"].model_copy(
        update={"values": (True, 35, 45)}
    )
    forged_ranges = dict(proposal.parameter_ranges)
    forged_ranges["stop_loss_bps"] = forged_range
    with pytest.raises(ValidationError):
        generate_strategy_variants(proposal.model_copy(update={"parameter_ranges": forged_ranges}))


def test_space_filling_has_bounded_distance_work(monkeypatch: pytest.MonkeyPatch) -> None:
    import us_intraday_lab.factory.variants as variants_module

    proposal = _proposal()
    proposal = HypothesisProposal.model_validate(
        {**proposal.model_dump(mode="python"), "max_variants": 200}
    )
    calls = 0
    original = variants_module._distance

    def counted_distance(*args: object, **kwargs: object) -> float:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(variants_module, "_distance", counted_distance)
    generated = generate_strategy_variants(proposal)

    assert len(generated) == proposal.max_variants
    assert calls <= 400_000
