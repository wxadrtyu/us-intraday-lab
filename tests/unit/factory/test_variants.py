import hashlib
import json
from pathlib import Path

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
