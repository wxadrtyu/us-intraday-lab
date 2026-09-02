from __future__ import annotations

import evaluate_full_universe_intraday_v9305_v9404_causal_recovery as subject


def test_preregistered_version_and_causality_contract() -> None:
    subject._configure()
    assert subject.FIRST_VERSION == 9305
    assert subject.LAST_VERSION == 9404
    assert len(subject.FAMILIES) == 10
    assert len(subject.SCHEDULES) == 5
    assert len(subject.campaign.campaign.specifications()) == 100
    assert all(decision + 1 < exit_bar <= 72 for decision, exit_bar in subject.SCHEDULES)
    assert subject.campaign.HISTORICAL_MIN_ANNUALIZED_RETURN == 0.15
    assert subject.campaign.REQUIRE_CONSUMED_2026Q1_GATE is True


def test_families_are_distinct_and_factors_have_directions() -> None:
    names = [name for name, _factors, _directions in subject.FAMILIES]
    assert len(set(names)) == len(names)
    for _name, factors, directions in subject.FAMILIES:
        assert len(factors) == len(directions)
        assert len(factors) >= 3
        assert set(directions) <= {-1, 1}
