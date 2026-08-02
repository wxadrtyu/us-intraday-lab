import re
from datetime import UTC, date, datetime, timedelta
from time import perf_counter

import pytest

from us_intraday_lab.validation.null_tests import (
    MAX_NULL_WORK_ITEMS,
    PRODUCTION_NULL_OPPORTUNITY_CAPACITY,
    PRODUCTION_NULL_REPETITIONS,
    HoldingRuleScoringConfig,
    NullOpportunity,
    NullTestConfig,
    generate_permuted_entry_mask,
    generate_shifted_entry_mask,
    null_framework_operation_bound,
    run_null_tests,
)

RULES = HoldingRuleScoringConfig(
    scoring_id="holding-rules-v1",
    rule_version="overlap-cooldown-v1",
    cost_model_id="base-cost-v1",
    cooldown_minutes=2,
    max_entries_per_session=6,
    max_concurrent_positions=3,
)


def _opportunities(
    *,
    winning_signal: bool = True,
    session_count: int = 1,
    exit_after_minutes: int = 3,
) -> tuple[NullOpportunity, ...]:
    rows: list[NullOpportunity] = []
    outcomes = (10.0, -5.0, -4.0, -3.0, -2.0)
    for session_index in range(session_count):
        session = date(2026, 7, 6) + timedelta(days=session_index)
        for symbol in ("SPY", "QQQ", "IWM"):
            for slot, outcome in enumerate(outcomes):
                selected = (0, 1) if winning_signal else (1, 2)
                signal_time = datetime.combine(
                    session,
                    datetime.min.time(),
                    tzinfo=UTC,
                ) + timedelta(hours=14, minutes=slot)
                entry_time = signal_time + timedelta(minutes=1)
                rows.append(
                    NullOpportunity(
                        opportunity_id=f"{session.isoformat()}-{symbol}-{slot}",
                        symbol=symbol,
                        session=session,
                        signal_time=signal_time,
                        entry_time=entry_time,
                        exit_time=entry_time + timedelta(minutes=exit_after_minutes),
                        entered=slot in selected,
                        holding_rule_net_profit=outcome,
                    )
                )
    return tuple(
        sorted(
            rows,
            key=lambda row: (row.session, row.signal_time, row.symbol, row.opportunity_id),
        )
    )


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


def test_internal_whole_sequence_scorer_enforces_overlap_and_is_deterministic() -> None:
    config = NullTestConfig(seed=1234, repetitions=32, percentile=0.75)

    first = run_null_tests(_opportunities(), config=config, scoring_config=RULES)
    second = run_null_tests(_opportunities(), config=config, scoring_config=RULES)

    assert first == second
    assert first.passed is True
    assert first.reason_code == "PASSED_NULL_TEST"
    independent_slot_sum = sum(
        item.holding_rule_net_profit for item in _opportunities() if item.entered
    )
    assert independent_slot_sum == pytest.approx(15.0)
    assert first.observed_profit == pytest.approx(30.0)
    assert first.observed_score.accepted_entry_count == 3
    assert first.observed_score.rejected_entry_count == 3
    assert tuple(distribution.method for distribution in first.distributions) == (
        "SESSION_SIGNAL_PERMUTATION",
        "SESSION_SAFE_TIMESTAMP_SHIFT",
    )
    assert all(len(distribution.statistics) == 32 for distribution in first.distributions)
    assert all(first.observed_profit > item.percentile_threshold for item in first.distributions)


def test_internal_scorer_enforces_cooldown_session_limit_and_concurrent_positions() -> None:
    opportunities = _opportunities(exit_after_minutes=0)
    strict_rules = HoldingRuleScoringConfig(
        scoring_id="strict-rules",
        rule_version="strict-v1",
        cost_model_id="base-cost-v1",
        cooldown_minutes=2,
        max_entries_per_session=2,
        max_concurrent_positions=1,
    )

    result = run_null_tests(
        opportunities,
        config=NullTestConfig(seed=5, repetitions=8, percentile=0.75),
        scoring_config=strict_rules,
    )

    assert result.observed_score.accepted_entry_count == 2
    assert result.observed_score.rejected_entry_count == 4
    assert result.scoring_config == strict_rules


def test_null_test_rejects_candidate_not_better_than_percentile() -> None:
    result = run_null_tests(
        _opportunities(winning_signal=False),
        config=NullTestConfig(seed=1234, repetitions=32, percentile=0.90),
        scoring_config=RULES,
    )

    assert result.passed is False
    assert result.reason_code == "NULL_TEST_FAILED"
    assert any(result.observed_profit <= item.percentile_threshold for item in result.distributions)


def test_scoring_config_and_cost_model_are_bound_into_evidence_hash() -> None:
    config = NullTestConfig(seed=7, repetitions=8, percentile=0.75)
    changed_cost = HoldingRuleScoringConfig(
        scoring_id=RULES.scoring_id,
        rule_version=RULES.rule_version,
        cost_model_id="stress-cost-v2",
        cooldown_minutes=RULES.cooldown_minutes,
        max_entries_per_session=RULES.max_entries_per_session,
        max_concurrent_positions=RULES.max_concurrent_positions,
    )

    first = run_null_tests(_opportunities(), config=config, scoring_config=RULES)
    second = run_null_tests(_opportunities(), config=config, scoring_config=changed_cost)

    assert first.scoring_config.cost_model_id == "base-cost-v1"
    assert first.evidence_sha256 != second.evidence_sha256
    assert re.fullmatch(r"[0-9a-f]{64}", first.evidence_sha256)


def test_canonical_private_evidence_is_not_changed_by_caller_mutation() -> None:
    opportunities = _opportunities()
    result = run_null_tests(
        opportunities,
        config=NullTestConfig(seed=7, repetitions=8),
        scoring_config=RULES,
    )
    original_hash = result.evidence_sha256
    original_ids = result.evidence_opportunity_ids

    object.__setattr__(opportunities[0], "holding_rule_net_profit", 999_999.0)

    assert result.evidence_sha256 == original_hash
    assert result.evidence_opportunity_ids == original_ids
    assert result == run_null_tests(
        _opportunities(),
        config=NullTestConfig(seed=7, repetitions=8),
        scoring_config=RULES,
    )


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
                scoring_config=RULES,
            )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rows: list(rows),
        lambda rows: (
            rows[:-1]
            + (
                NullOpportunity(
                    opportunity_id="bad-profit",
                    symbol="IWM",
                    session=rows[-1].session,
                    signal_time=rows[-1].signal_time + timedelta(minutes=1),
                    entry_time=rows[-1].entry_time + timedelta(minutes=1),
                    exit_time=rows[-1].exit_time + timedelta(minutes=1),
                    entered=False,
                    holding_rule_net_profit=float("nan"),
                ),
            )
        ),
    ],
)
def test_null_boundaries_reject_non_tuple_or_nonfinite_evidence(mutator: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_null_tests(  # type: ignore[arg-type,operator]
            mutator(_opportunities()),
            config=NullTestConfig(seed=1, repetitions=8),
            scoring_config=RULES,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scoring_id": "", "rule_version": "v1", "cost_model_id": "base"},
        {
            "scoring_id": "id",
            "rule_version": "v1",
            "cost_model_id": "base",
            "cooldown_minutes": True,
        },
        {
            "scoring_id": "id",
            "rule_version": "v1",
            "cost_model_id": "base",
            "max_entries_per_session": 0,
        },
        {
            "scoring_id": "id",
            "rule_version": "v1",
            "cost_model_id": "base",
            "max_concurrent_positions": 4,
        },
    ],
)
def test_holding_rule_config_rejects_missing_coerced_or_unbounded_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        HoldingRuleScoringConfig(**kwargs)  # type: ignore[arg-type]


def test_null_identity_strings_are_bounded_for_hashing_work() -> None:
    with pytest.raises(ValueError, match="at most 128"):
        HoldingRuleScoringConfig(
            scoring_id="x" * 129,
            rule_version="v1",
            cost_model_id="base",
        )
    opportunity = _opportunities()[0]
    with pytest.raises(ValueError, match="at most 128"):
        NullOpportunity(
            opportunity_id="x" * 129,
            symbol=opportunity.symbol,
            session=opportunity.session,
            signal_time=opportunity.signal_time,
            entry_time=opportunity.entry_time,
            exit_time=opportunity.exit_time,
            entered=opportunity.entered,
            holding_rule_net_profit=opportunity.holding_rule_net_profit,
        )


def test_work_bound_counts_framework_passes_and_supports_practical_capacity() -> None:
    production = NullTestConfig(seed=1)
    assert PRODUCTION_NULL_REPETITIONS > 32
    assert PRODUCTION_NULL_OPPORTUNITY_CAPACITY >= 3 * 26 * 252
    capacity_bound = null_framework_operation_bound(
        PRODUCTION_NULL_OPPORTUNITY_CAPACITY,
        config=production,
        scoring_config=RULES,
    )
    next_bound = null_framework_operation_bound(
        PRODUCTION_NULL_OPPORTUNITY_CAPACITY + 1,
        config=production,
        scoring_config=RULES,
    )

    assert capacity_bound <= MAX_NULL_WORK_ITEMS
    assert next_bound > MAX_NULL_WORK_ITEMS


def test_modest_multi_session_runtime_regression() -> None:
    opportunities = _opportunities(session_count=20)
    config = NullTestConfig(seed=3, repetitions=32, percentile=0.90)

    started = perf_counter()
    result = run_null_tests(opportunities, config=config, scoring_config=RULES)
    elapsed = perf_counter() - started

    assert result.framework_operation_bound == null_framework_operation_bound(
        len(opportunities), config=config, scoring_config=RULES
    )
    assert elapsed < 2.0


def test_null_rejects_unsorted_duplicate_unshiftable_or_invalid_timestamps() -> None:
    opportunities = _opportunities()
    duplicate = opportunities[:-1] + (opportunities[-2],)
    unshiftable = tuple(row for row in opportunities if row.entered)
    invalid_timestamps = _opportunities()
    invalid_time = invalid_timestamps[-1]
    object.__setattr__(invalid_time, "exit_time", invalid_time.entry_time - timedelta(minutes=1))

    for invalid in (
        tuple(reversed(opportunities)),
        duplicate,
        unshiftable,
        invalid_timestamps,
    ):
        with pytest.raises(ValueError):
            run_null_tests(
                invalid,
                config=NullTestConfig(seed=1, repetitions=8),
                scoring_config=RULES,
            )
