import re
from datetime import UTC, date, datetime, timedelta

import pytest

from us_intraday_lab.validation.null_tests import (
    PRODUCTION_NULL_REPETITIONS,
    NullOpportunity,
    NullTestConfig,
    generate_permuted_entry_mask,
    generate_shifted_entry_mask,
    run_null_tests,
)


def _opportunities(*, winning_signal: bool = True) -> tuple[NullOpportunity, ...]:
    session = date(2026, 7, 6)
    rows: list[NullOpportunity] = []
    outcomes = (10.0, -5.0, -4.0, -3.0, -2.0)
    for symbol_index, symbol in enumerate(("SPY", "QQQ", "IWM")):
        for slot, outcome in enumerate(outcomes):
            entered = slot == (0 if winning_signal else 1)
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

    first = run_null_tests(_opportunities(), config=config)
    second = run_null_tests(_opportunities(), config=config)

    assert first == second
    assert first.passed is True
    assert first.reason_code == "PASSED_NULL_TEST"
    assert first.observed_profit == pytest.approx(30.0)
    assert re.fullmatch(r"[0-9a-f]{64}", first.evidence_sha256)
    assert tuple(distribution.method for distribution in first.distributions) == (
        "SESSION_SIGNAL_PERMUTATION",
        "SESSION_SAFE_TIMESTAMP_SHIFT",
    )
    assert all(len(distribution.statistics) == 32 for distribution in first.distributions)
    assert all(first.observed_profit > item.percentile_threshold for item in first.distributions)
    assert dict(first.trade_count_by_symbol_session) == {
        "2026-07-06:IWM": 1,
        "2026-07-06:QQQ": 1,
        "2026-07-06:SPY": 1,
    }


def test_null_test_rejects_candidate_not_better_than_percentile() -> None:
    result = run_null_tests(
        _opportunities(winning_signal=False),
        config=NullTestConfig(seed=1234, repetitions=32, percentile=0.90),
    )

    assert result.passed is False
    assert result.reason_code == "NULL_TEST_FAILED"
    assert any(result.observed_profit <= item.percentile_threshold for item in result.distributions)


def test_null_config_has_large_bounded_production_default_and_small_fixture_override() -> None:
    production = NullTestConfig(seed=1)
    fixture = NullTestConfig(seed=1, repetitions=8)

    assert production.repetitions == PRODUCTION_NULL_REPETITIONS
    assert PRODUCTION_NULL_REPETITIONS >= 1_000
    assert fixture.repetitions == 8


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rows: list(rows),
        lambda rows: rows[:-1]
        + (
            NullOpportunity(
                opportunity_id="bad-symbol",
                symbol="DIA",
                session=rows[-1].session,
                signal_time=rows[-1].signal_time + timedelta(minutes=1),
                entered=False,
                holding_rule_net_profit=1.0,
            ),
        ),
        lambda rows: rows[:-1]
        + (
            NullOpportunity(
                opportunity_id="bad-profit",
                symbol="IWM",
                session=rows[-1].session,
                signal_time=rows[-1].signal_time + timedelta(minutes=1),
                entered=False,
                holding_rule_net_profit=float("nan"),
            ),
        ),
    ],
)
def test_null_boundaries_reject_non_tuple_unknown_symbol_or_nonfinite_profit(mutator: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_null_tests(  # type: ignore[arg-type,operator]
            mutator(_opportunities()),
            config=NullTestConfig(seed=1, repetitions=8),
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
def test_null_config_rejects_coercion_nonfinite_and_excessive_work(kwargs: dict[str, object]) -> None:
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
        tuple(sorted(opportunities + (wrong_session,), key=lambda row: (
            row.session, row.symbol, row.signal_time, row.opportunity_id
        ))),
    ):
        with pytest.raises(ValueError):
            run_null_tests(invalid, config=NullTestConfig(seed=1, repetitions=8))


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
        run_null_tests(mixed, config=NullTestConfig(seed=1, repetitions=8))


def test_null_test_revalidates_tampered_frozen_inputs() -> None:
    opportunities = _opportunities()
    object.__setattr__(opportunities[0], "holding_rule_net_profit", float("nan"))
    config = NullTestConfig(seed=1, repetitions=8)
    object.__setattr__(config, "repetitions", True)

    with pytest.raises(ValueError, match="finite"):
        run_null_tests(opportunities, config=NullTestConfig(seed=1, repetitions=8))
    with pytest.raises(TypeError, match="repetitions"):
        run_null_tests(_opportunities(), config=config)
