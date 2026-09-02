from __future__ import annotations

import evaluate_full_universe_intraday_v9505_v9604_multiclock_residual as subject


def test_preregistered_multiclock_contract() -> None:
    assert subject.FIRST_VERSION == 9505
    assert subject.LAST_VERSION == 9604
    assert len(subject.FACTOR_BUNDLES) == 10
    assert len(subject.WINDOW_STRUCTURES) == 10
    assert len(subject.specifications()) == 100
    assert len(subject.QUANTILES) * len(subject.ALPHAS) == 6


def test_every_structure_is_causal_nonoverlapping_and_intraday() -> None:
    for structure in subject.WINDOW_STRUCTURES:
        assert len(structure) == 3
        for decision, exit_bar in structure:
            assert decision + 1 < exit_bar <= 72
        for left, right in zip(structure, structure[1:]):
            assert left[1] <= right[0]
