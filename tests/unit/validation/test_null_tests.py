import re
from datetime import UTC, date, datetime, timedelta

import pytest

from us_intraday_lab.validation.null_tests import (
    MAX_NULL_WORK_ITEMS,
    PRODUCTION_NULL_OPPORTUNITY_CAPACITY,
    PRODUCTION_NULL_REPETITIONS,
    NullOpportunity,
    NullScorerIdentity,
    NullSequenceScore,
    NullTestConfig,
    generate_permuted_entry_mask,
    generate_shifted_entry_mask,
    run_null_tests,
)


class CooldownSequenceScorer:
    def __init__(self, *, scorer_id: str = "fixture-cooldown-v1") -> None:
        self.identity = NullScorerIdentity(
            scorer_id=scorer_id,
            rule_version="holding-cooldown-v1",
            cost_model_id="base-cost-v1",
        )
        self.calls: list[tuple[bool, ...]] = []

    def score_sequence(
        self,
        opportunities: tuple[NullOpportunity, ...],
        entry_mask: tuple[bool, ...],
    ) -> NullSequenceScore:
        self.calls.append(entry_mask)
        accepted = 0
        rejected = 0
        profit = 0.0
        last_entry: dict[tuple[str, date], datetime] = {}
        for opportunity, entered in zip(opportunities, entry_mask, strict=True):
            if not entered:
                continue
            key = (opportunity.symbol, opportunity.session)
            previous = last_entry.get(key)
            if previous is not None and opportunity.signal_time - previous < timedelta(minutes=2):
                rejected += 1
                continue
            last_entry[key] = opportunity.signal_time
            accepted += 1
            profit += opportunity.holding_rule_net_profit
        return NullSequenceScore(
            net_profit=profit,
            accepted_entry_count=accepted,
            rejected_entry_count=rejected,
        )


def _opportunities(*, winning_signal: bool = True) -> tuple[NullOpportunity, ...]:
    session = date(2026, 7, 6)
    rows: list[NullOpportunity] = []
    outcomes = (10.0, -5.0, -4.0, -3.0, -2.0)
    for symbol_index, symbol in enumerate(("SPY", "QQQ", "IWM")):
        for slot, outcome in enumerate(outcomes):
            selected = (0, 1) if winning_signal else (1, 2)
            entered = slot in selected
            rows.append(
                NullOpportunity(
                    opportunity_id=f"{symbol}-{slot}",
                    symbol=symbol,
                    session=session,
                    signal_time=datetime(2026, 7, 6, 14, slot + symbol_index * 10, tzinfo=UTC),
                    entered=entered,
                    holding_rule_net_profit=outcome,
                )
            )
    return tuple(sorted(rows, key=lambda row: (row.session, row.symbol, row.signal_time)))


def _counts_by_group(
    opportunities: tuple[NullOpportunity, ...], mask: tuple[bool, ...]
) -> dict[tuple[str, date], int]:
    counts: dict[tuple[str, date], int] = {}
    for opportunity, entered in zip(opportunities, mask, strict=True):
        key = (opportunity.symbol, opportunity.session)
        counts[key] = counts.get(key, 0) + int(entered)
    return counts


def test_permutation_is_seeded_session_local_and_preserves_trade_count() -> None:
    opportunities = _opportunities()
    original = tuple(row.entered for row in opportunities)

    first = generate_permuted_entry_mask(opportunities, seed=17)
    second = generate_permuted_entry_mask(opportunities, seed=17)

    assert first == second
    assert first != original
    assert _counts_by_group(opportunities, first) == _counts_by_group(opportunities, original)


def test_timestamp_shift_is_seeded_nonzero_session_safe_and_preserves_count() -> None:
    opportunities = _opportunities()
    original = tuple(row.entered for row in opportunities)

    first = generate_shifted_entry_mask(opportunities, seed=29)
    second = generate_shifted_entry_mask(opportunities, seed=29)

    assert first == second
    assert first != original
    assert _counts_by_group(opportunities, first) == _counts_by_group(opportunities, original)


def test_null_test_is_deterministic_and_requires_both_null_percentiles() -> None:
    config = NullTestConfig(seed=1234, repetitions=32, percentile=0.90)
    first_scorer = CooldownSequenceScorer()
    second_scorer = CooldownSequenceScorer()

    first = run_null_tests(_opportunities(), config=config, scorer=first_scorer)
    second = run_null_tests(_opportunities(), config=config, scorer=second_scorer)

    assert first == second
    assert first.passed is True
    assert first.reason_code == "PASSED_NULL_TEST"
    assert first.observed_profit == pytest.approx(30.0)
    independent_slot_sum = sum(
        item.holding_rule_net_profit for item in _opportunities() if item.entered
    )
    assert independent_slot_sum == pytest.approx(15.0)
    assert first.observed_profit != independent_slot_sum
    assert first.observed_score.accepted_entry_count == 3
    assert first.observed_score.rejected_entry_count == 3
    assert first.scorer_identity == first_scorer.identity
    assert len(first_scorer.calls) == 2 + 2 * config.repetitions
    assert re.fullmatch(r"[0-9a-f]{64}", first.evidence_sha256)
    assert tuple(distribution.method for distribution in first.distributions) == (
        "SESSION_SIGNAL_PERMUTATION",
        "SESSION_SAFE_TIMESTAMP_SHIFT",
    )
    assert all(len(distribution.statistics) == 32 for distribution in first.distributions)
    assert any(
        rejected > 0
        for distribution in first.distributions
        for rejected in distribution.rejected_entry_counts
    )
    assert all(first.observed_profit > item.percentile_threshold for item in first.distributions)
    assert dict(first.trade_count_by_symbol_session) == {
        "2026-07-06:IWM": 2,
        "2026-07-06:QQQ": 2,
        "2026-07-06:SPY": 2,
    }


def test_null_test_rejects_candidate_not_better_than_percentile() -> None:
    result = run_null_tests(
        _opportunities(winning_signal=False),
        config=NullTestConfig(seed=1234, repetitions=32, percentile=0.90),
        scorer=CooldownSequenceScorer(),
    )

    assert result.passed is False
    assert result.reason_code == "NULL_TEST_FAILED"
    assert any(result.observed_profit <= item.percentile_threshold for item in result.distributions)


def test_null_config_has_large_bounded_production_default_and_small_fixture_override() -> None:
    production = NullTestConfig(seed=1)
    fixture = NullTestConfig(seed=1, repetitions=8)

    assert production.repetitions == PRODUCTION_NULL_REPETITIONS
    assert PRODUCTION_NULL_REPETITIONS >= 1_000
    assert PRODUCTION_NULL_OPPORTUNITY_CAPACITY >= 3 * 26 * 252
    production_work_per_opportunity = 4 * PRODUCTION_NULL_REPETITIONS + 2
    assert (
        PRODUCTION_NULL_OPPORTUNITY_CAPACITY * production_work_per_opportunity
        <= MAX_NULL_WORK_ITEMS
    )
    assert (
        PRODUCTION_NULL_OPPORTUNITY_CAPACITY + 1
    ) * production_work_per_opportunity > MAX_NULL_WORK_ITEMS
    assert fixture.repetitions == 8


def test_scorer_identity_and_cost_model_are_bound_into_evidence_hash() -> None:
    config = NullTestConfig(seed=7, repetitions=8, percentile=0.75)

    first = run_null_tests(
        _opportunities(), config=config, scorer=CooldownSequenceScorer(scorer_id="scorer-a")
    )
    second = run_null_tests(
        _opportunities(), config=config, scorer=CooldownSequenceScorer(scorer_id="scorer-b")
    )

    assert first.scorer_identity.scorer_id == "scorer-a"
    assert first.scorer_identity.rule_version == "holding-cooldown-v1"
    assert first.scorer_identity.cost_model_id == "base-cost-v1"
    assert first.evidence_sha256 != second.evidence_sha256


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rows: list(rows),
        lambda rows: (
            rows[:-1]
            + (
                NullOpportunity(
                    opportunity_id="bad-symbol",
                    symbol="DIA",
                    session=rows[-1].session,
                    signal_time=rows[-1].signal_time + timedelta(minutes=1),
                    entered=False,
                    holding_rule_net_profit=1.0,
                ),
            )
        ),
        lambda rows: (
            rows[:-1]
            + (
                NullOpportunity(
                    opportunity_id="bad-profit",
                    symbol="IWM",
                    session=rows[-1].session,
                    signal_time=rows[-1].signal_time + timedelta(minutes=1),
                    entered=False,
                    holding_rule_net_profit=float("nan"),
                ),
            )
        ),
    ],
)
def test_null_boundaries_reject_non_tuple_unknown_symbol_or_nonfinite_profit(
    mutator: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_null_tests(  # type: ignore[arg-type,operator]
            mutator(_opportunities()),
            config=NullTestConfig(seed=1, repetitions=8),
            scorer=CooldownSequenceScorer(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seed": True},
        {"seed": 1, "repetitions": True},
        {"seed": 1, "repetitions": 0},
        {"seed": 1, "repetitions": 100_001},
        {"seed": 1, "percentile": 1.0},
        {"seed": 1, "percentile": float("nan")},
    ],
)
def test_null_config_rejects_coercion_nonfinite_and_excessive_work(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        NullTestConfig(**kwargs)  # type: ignore[arg-type]


def test_null_test_rejects_unsorted_duplicate_or_unshiftable_evidence() -> None:
    opportunities = _opportunities()
    duplicate = opportunities[:-1] + (opportunities[-2],)
    unshiftable = tuple(row for row in opportunities if row.entered)

    for invalid in (tuple(reversed(opportunities)), duplicate, unshiftable):
        with pytest.raises(ValueError):
            run_null_tests(
                invalid,
                config=NullTestConfig(seed=1, repetitions=8),
                scorer=CooldownSequenceScorer(),
            )


def test_null_test_rejects_duplicate_slots_or_mismatched_session_dates() -> None:
    opportunities = _opportunities()
    same_slot = NullOpportunity(
        opportunity_id="different-id-same-slot",
        symbol=opportunities[-1].symbol,
        session=opportunities[-1].session,
        signal_time=opportunities[-1].signal_time,
        entered=False,
        holding_rule_net_profit=1.0,
    )
    wrong_session = NullOpportunity(
        opportunity_id="wrong-session",
        symbol=opportunities[-1].symbol,
        session=opportunities[-1].session + timedelta(days=1),
        signal_time=opportunities[-1].signal_time,
        entered=False,
        holding_rule_net_profit=1.0,
    )

    for invalid in (
        opportunities + (same_slot,),
        tuple(
            sorted(
                opportunities + (wrong_session,),
                key=lambda row: (row.session, row.symbol, row.signal_time, row.opportunity_id),
            )
        ),
    ):
        with pytest.raises(ValueError):
            run_null_tests(
                invalid,
                config=NullTestConfig(seed=1, repetitions=8),
                scorer=CooldownSequenceScorer(),
            )


def test_null_test_rejects_any_active_group_that_cannot_shift() -> None:
    opportunities = _opportunities()
    singleton_session = date(2026, 7, 7)
    active_singleton = NullOpportunity(
        opportunity_id="SPY-singleton-entered",
        symbol="SPY",
        session=singleton_session,
        signal_time=datetime(2026, 7, 7, 14, 0, tzinfo=UTC),
        entered=True,
        holding_rule_net_profit=1.0,
    )
    mixed = tuple(
        sorted(
            opportunities + (active_singleton,),
            key=lambda row: (row.session, row.symbol, row.signal_time, row.opportunity_id),
        )
    )

    with pytest.raises(ValueError, match="every active"):
        run_null_tests(
            mixed,
            config=NullTestConfig(seed=1, repetitions=8),
            scorer=CooldownSequenceScorer(),
        )


def test_null_test_revalidates_tampered_frozen_inputs() -> None:
    opportunities = _opportunities()
    object.__setattr__(opportunities[0], "holding_rule_net_profit", float("nan"))
    config = NullTestConfig(seed=1, repetitions=8)
    object.__setattr__(config, "repetitions", True)

    with pytest.raises(ValueError, match="finite"):
        run_null_tests(
            opportunities,
            config=NullTestConfig(seed=1, repetitions=8),
            scorer=CooldownSequenceScorer(),
        )
    with pytest.raises(TypeError, match="repetitions"):
        run_null_tests(_opportunities(), config=config, scorer=CooldownSequenceScorer())


def test_null_evidence_requires_exact_global_production_symbol_coverage() -> None:
    opportunities = _opportunities()
    missing = tuple(item for item in opportunities if item.symbol != "IWM")
    extra = list(opportunities)
    object.__setattr__(extra[-1], "symbol", "DIA")

    for invalid in (missing, tuple(extra)):
        with pytest.raises(ValueError, match="exactly SPY, QQQ, and IWM"):
            run_null_tests(
                invalid,
                config=NullTestConfig(seed=1, repetitions=8),
                scorer=CooldownSequenceScorer(),
            )


class InvalidOutputScorer(CooldownSequenceScorer):
    def __init__(self, *, field: str, value: object) -> None:
        super().__init__()
        self._field = field
        self._value = value

    def score_sequence(
        self,
        opportunities: tuple[NullOpportunity, ...],
        entry_mask: tuple[bool, ...],
    ) -> NullSequenceScore:
        result = super().score_sequence(opportunities, entry_mask)
        object.__setattr__(result, self._field, self._value)
        return result


@pytest.mark.parametrize(
    ("field", "value"),
    [("net_profit", float("nan")), ("accepted_entry_count", True)],
)
def test_null_scorer_outputs_reject_nonfinite_or_coerced_values(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_null_tests(
            _opportunities(),
            config=NullTestConfig(seed=1, repetitions=8),
            scorer=InvalidOutputScorer(field=field, value=value),
        )


def test_null_scorer_requires_strict_identity_output() -> None:
    scorer = CooldownSequenceScorer()
    object.__setattr__(scorer.identity, "cost_model_id", "")

    with pytest.raises(ValueError, match="cost_model_id"):
        run_null_tests(
            _opportunities(),
            config=NullTestConfig(seed=1, repetitions=8),
            scorer=scorer,
        )
