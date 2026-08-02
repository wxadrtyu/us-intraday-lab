"""Bounded deterministic null benchmarks for session-local entry signals."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import Literal, cast

from us_intraday_lab.validation.stability import PRODUCTION_SYMBOLS

PRODUCTION_NULL_REPETITIONS = 1_000
MAX_NULL_REPETITIONS = 100_000
MAX_NULL_OPPORTUNITIES = 100_000
MAX_NULL_WORK_ITEMS = 2_000_000

NullMethod = Literal["SESSION_SIGNAL_PERMUTATION", "SESSION_SAFE_TIMESTAMP_SHIFT"]


def _finite_number(value: object, *, name: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{name} must be an exact finite number")
    numeric = cast("int | float", value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be an exact finite number")
    return float(numeric)


@dataclass(frozen=True, slots=True)
class NullOpportunity:
    """An eligible entry slot and its P&L under unchanged holding rules."""

    opportunity_id: str
    symbol: str
    session: date
    signal_time: datetime
    entered: bool
    holding_rule_net_profit: float

    def __post_init__(self) -> None:
        if type(self.opportunity_id) is not str or not self.opportunity_id:
            raise ValueError("opportunity_id must be a non-empty string")
        if type(self.symbol) is not str or self.symbol not in PRODUCTION_SYMBOLS:
            raise ValueError("symbol must be SPY, QQQ, or IWM")
        if type(self.session) is not date:
            raise TypeError("session must be an exact date")
        if type(self.signal_time) is not datetime:
            raise TypeError("signal_time must be an exact datetime")
        if self.signal_time.utcoffset() != timedelta(0):
            raise ValueError("signal_time must be timezone-aware UTC")
        if type(self.entered) is not bool:
            raise TypeError("entered must be an exact bool")
        profit = _finite_number(
            self.holding_rule_net_profit,
            name="holding_rule_net_profit",
        )
        object.__setattr__(self, "signal_time", self.signal_time.astimezone(UTC))
        object.__setattr__(self, "holding_rule_net_profit", profit)


@dataclass(frozen=True, slots=True)
class NullTestConfig:
    seed: int
    repetitions: int = PRODUCTION_NULL_REPETITIONS
    percentile: float = 0.95

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be an exact integer")
        if type(self.repetitions) is not int:
            raise TypeError("repetitions must be an exact integer")
        if not 1 <= self.repetitions <= MAX_NULL_REPETITIONS:
            raise ValueError(
                f"repetitions must be between 1 and {MAX_NULL_REPETITIONS}"
            )
        percentile = _finite_number(self.percentile, name="percentile")
        if not 0.0 < percentile < 1.0:
            raise ValueError("percentile must be greater than 0 and less than 1")
        object.__setattr__(self, "percentile", percentile)


@dataclass(frozen=True, slots=True)
class NullDistribution:
    method: NullMethod
    statistics: tuple[float, ...]
    percentile_threshold: float


@dataclass(frozen=True, slots=True)
class NullTestResult:
    passed: bool
    reason_code: str
    observed_profit: float
    seed: int
    repetitions: int
    percentile: float
    evidence_sha256: str
    distributions: tuple[NullDistribution, ...]
    trade_count_by_symbol_session: Mapping[str, int]


def _validated_opportunities(value: object) -> tuple[NullOpportunity, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("opportunities must be a non-empty exact tuple")
    if len(value) > MAX_NULL_OPPORTUNITIES:
        raise ValueError("opportunities exceed the evidence budget")
    if any(type(item) is not NullOpportunity for item in value):
        raise TypeError("opportunities must contain exact NullOpportunity values")
    reparsed = tuple(
        NullOpportunity(
            opportunity_id=item.opportunity_id,
            symbol=item.symbol,
            session=item.session,
            signal_time=item.signal_time,
            entered=item.entered,
            holding_rule_net_profit=item.holding_rule_net_profit,
        )
        for item in value
    )
    order_key = lambda item: (item.session, item.symbol, item.signal_time, item.opportunity_id)
    if tuple(sorted(reparsed, key=order_key)) != reparsed:
        raise ValueError("opportunities must be canonically sorted")
    identities = tuple(
        (item.symbol, item.session, item.signal_time, item.opportunity_id) for item in reparsed
    )
    if len(set(identities)) != len(identities):
        raise ValueError("opportunities must be unique")
    opportunity_ids = tuple(item.opportunity_id for item in reparsed)
    if len(set(opportunity_ids)) != len(opportunity_ids):
        raise ValueError("opportunity_id values must be unique")
    slot_keys = tuple((item.symbol, item.session, item.signal_time) for item in reparsed)
    if len(set(slot_keys)) != len(slot_keys):
        raise ValueError("symbol/session signal slots must be unique")
    if any(item.signal_time.date() != item.session for item in reparsed):
        raise ValueError("signal_time must fall on its declared session date")
    groups = _group_indexes(reparsed)
    active_group_counts = tuple(
        (sum(reparsed[index].entered for index in indexes), len(indexes))
        for indexes in groups.values()
        if any(reparsed[index].entered for index in indexes)
    )
    if not active_group_counts or any(
        not 0 < entered_count < slot_count
        for entered_count, slot_count in active_group_counts
    ):
        raise ValueError("every active symbol/session group must be shiftable")
    return reparsed


def _group_indexes(
    opportunities: tuple[NullOpportunity, ...],
) -> dict[tuple[str, date], tuple[int, ...]]:
    groups: dict[tuple[str, date], list[int]] = {}
    for index, opportunity in enumerate(opportunities):
        groups.setdefault((opportunity.symbol, opportunity.session), []).append(index)
    return {key: tuple(indexes) for key, indexes in groups.items()}


def _permuted_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    rng: random.Random,
) -> tuple[bool, ...]:
    result = [False] * len(opportunities)
    for indexes in _group_indexes(opportunities).values():
        local = [opportunities[index].entered for index in indexes]
        rng.shuffle(local)
        for index, entered in zip(indexes, local, strict=True):
            result[index] = entered
    return tuple(result)


def _shifted_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    rng: random.Random,
) -> tuple[bool, ...]:
    result = [False] * len(opportunities)
    for indexes in _group_indexes(opportunities).values():
        local = tuple(opportunities[index].entered for index in indexes)
        shifted: tuple[bool, ...]
        if len(local) == 1:
            shifted = local
        else:
            offset = rng.randrange(1, len(local))
            shifted = local[-offset:] + local[:-offset]
        for index, entered in zip(indexes, shifted, strict=True):
            result[index] = entered
    return tuple(result)


def generate_permuted_entry_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    seed: int,
) -> tuple[bool, ...]:
    """Permute entries only within each symbol/session group."""

    evidence = _validated_opportunities(opportunities)
    if type(seed) is not int:
        raise TypeError("seed must be an exact integer")
    return _permuted_mask(evidence, rng=random.Random(seed))


def generate_shifted_entry_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    seed: int,
) -> tuple[bool, ...]:
    """Cyclically shift each group by a seeded nonzero offset."""

    evidence = _validated_opportunities(opportunities)
    if type(seed) is not int:
        raise TypeError("seed must be an exact integer")
    return _shifted_mask(evidence, rng=random.Random(seed))


def _profit(opportunities: tuple[NullOpportunity, ...], mask: tuple[bool, ...]) -> float:
    return math.fsum(
        item.holding_rule_net_profit
        for item, entered in zip(opportunities, mask, strict=True)
        if entered
    )


def _nearest_rank_percentile(statistics: tuple[float, ...], percentile: float) -> float:
    ordered = sorted(statistics)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _evidence_sha256(opportunities: tuple[NullOpportunity, ...]) -> str:
    payload = [
        {
            "entered": item.entered,
            "holding_rule_net_profit": item.holding_rule_net_profit,
            "opportunity_id": item.opportunity_id,
            "session": item.session.isoformat(),
            "signal_time": item.signal_time.isoformat(),
            "symbol": item.symbol,
        }
        for item in opportunities
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_null_tests(
    opportunities: tuple[NullOpportunity, ...],
    *,
    config: NullTestConfig,
) -> NullTestResult:
    """Compare observed profit against both deterministic null distributions."""

    evidence = _validated_opportunities(opportunities)
    if type(config) is not NullTestConfig:
        raise TypeError("config must be an exact NullTestConfig")
    validated_config = NullTestConfig(
        seed=config.seed,
        repetitions=config.repetitions,
        percentile=config.percentile,
    )
    work_items = len(evidence) * validated_config.repetitions * 2
    if work_items > MAX_NULL_WORK_ITEMS:
        raise ValueError("null test configuration exceeds the work-item budget")

    observed_mask = tuple(item.entered for item in evidence)
    observed_profit = _profit(evidence, observed_mask)
    permutation_rng = random.Random(validated_config.seed)
    shift_rng = random.Random(validated_config.seed ^ 0x5DEECE66D)
    permutation_statistics = tuple(
        _profit(evidence, _permuted_mask(evidence, rng=permutation_rng))
        for _ in range(validated_config.repetitions)
    )
    shift_statistics = tuple(
        _profit(evidence, _shifted_mask(evidence, rng=shift_rng))
        for _ in range(validated_config.repetitions)
    )
    distributions = (
        NullDistribution(
            method="SESSION_SIGNAL_PERMUTATION",
            statistics=permutation_statistics,
            percentile_threshold=_nearest_rank_percentile(
                permutation_statistics, validated_config.percentile
            ),
        ),
        NullDistribution(
            method="SESSION_SAFE_TIMESTAMP_SHIFT",
            statistics=shift_statistics,
            percentile_threshold=_nearest_rank_percentile(
                shift_statistics, validated_config.percentile
            ),
        ),
    )
    passed = all(
        observed_profit > distribution.percentile_threshold for distribution in distributions
    )
    trade_counts = {
        f"{session.isoformat()}:{symbol}": sum(evidence[index].entered for index in indexes)
        for (symbol, session), indexes in _group_indexes(evidence).items()
    }
    return NullTestResult(
        passed=passed,
        reason_code="PASSED_NULL_TEST" if passed else "NULL_TEST_FAILED",
        observed_profit=observed_profit,
        seed=validated_config.seed,
        repetitions=validated_config.repetitions,
        percentile=validated_config.percentile,
        evidence_sha256=_evidence_sha256(evidence),
        distributions=distributions,
        trade_count_by_symbol_session=MappingProxyType(dict(sorted(trade_counts.items()))),
    )
