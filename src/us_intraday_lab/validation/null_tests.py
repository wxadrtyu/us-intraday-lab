"""Bounded deterministic null benchmarks with closed holding-rule scoring."""

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

PRODUCTION_NULL_REPETITIONS = 200
MAX_NULL_REPETITIONS = 10_000
MAX_NULL_OPPORTUNITIES = 100_000
MAX_NULL_WORK_ITEMS = 200_000_000
MAX_CONFIGURED_ENTRIES_PER_SESSION = 100
MAX_CONFIGURED_CONCURRENT_POSITIONS = len(PRODUCTION_SYMBOLS)
MAX_EVIDENCE_ID_LENGTH = 128

# Conservative row-operation accounting. Setup covers strict validation twice,
# canonical-order checks, group/evaluation-plan construction, coverage, hashing,
# and result evidence. Scoring includes bounded active-position checks. Each
# repetition builds two masks and scores both full sequences.
_SETUP_OPERATIONS_PER_ROW = 40
_SCORING_BASE_OPERATIONS_PER_ROW = 12
_MASK_OPERATIONS_PER_REPETITION_PER_ROW = 6

NullMethod = Literal["SESSION_SIGNAL_PERMUTATION", "SESSION_SAFE_TIMESTAMP_SHIFT"]


def _finite_number(value: object, *, name: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{name} must be an exact finite number")
    numeric = cast("int | float", value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be an exact finite number")
    return float(numeric)


def _utc(value: object, *, name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{name} must be an exact datetime")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _bounded_id(value: object, *, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty exact string")
    if len(value) > MAX_EVIDENCE_ID_LENGTH:
        raise ValueError(f"{name} must contain at most {MAX_EVIDENCE_ID_LENGTH} characters")
    return value


@dataclass(frozen=True, slots=True)
class NullOpportunity:
    """One eligible entry with fixed exit and base-cost P&L evidence."""

    opportunity_id: str
    symbol: str
    session: date
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entered: bool
    holding_rule_net_profit: float

    def __post_init__(self) -> None:
        _bounded_id(self.opportunity_id, name="opportunity_id")
        if type(self.symbol) is not str or self.symbol not in PRODUCTION_SYMBOLS:
            raise ValueError("symbol must be SPY, QQQ, or IWM")
        if type(self.session) is not date:
            raise TypeError("session must be an exact date")
        signal_time = _utc(self.signal_time, name="signal_time")
        entry_time = _utc(self.entry_time, name="entry_time")
        exit_time = _utc(self.exit_time, name="exit_time")
        if not signal_time <= entry_time <= exit_time:
            raise ValueError("signal_time, entry_time, and exit_time must be chronological")
        if any(value.date() != self.session for value in (signal_time, entry_time, exit_time)):
            raise ValueError("opportunity timestamps must fall on the declared session date")
        if type(self.entered) is not bool:
            raise TypeError("entered must be an exact bool")
        profit = _finite_number(
            self.holding_rule_net_profit,
            name="holding_rule_net_profit",
        )
        object.__setattr__(self, "signal_time", signal_time)
        object.__setattr__(self, "entry_time", entry_time)
        object.__setattr__(self, "exit_time", exit_time)
        object.__setattr__(self, "holding_rule_net_profit", profit)


@dataclass(frozen=True, slots=True)
class HoldingRuleScoringConfig:
    """Closed configuration for the project-owned whole-sequence scorer."""

    scoring_id: str
    rule_version: str
    cost_model_id: str
    cooldown_minutes: int = 0
    max_entries_per_session: int = MAX_CONFIGURED_ENTRIES_PER_SESSION
    max_concurrent_positions: int = MAX_CONFIGURED_CONCURRENT_POSITIONS

    def __post_init__(self) -> None:
        for name in ("scoring_id", "rule_version", "cost_model_id"):
            _bounded_id(getattr(self, name), name=name)
        if type(self.cooldown_minutes) is not int:
            raise TypeError("cooldown_minutes must be an exact integer")
        if not 0 <= self.cooldown_minutes <= 1_440:
            raise ValueError("cooldown_minutes must be between 0 and 1440")
        if type(self.max_entries_per_session) is not int:
            raise TypeError("max_entries_per_session must be an exact integer")
        if not 1 <= self.max_entries_per_session <= MAX_CONFIGURED_ENTRIES_PER_SESSION:
            raise ValueError(
                "max_entries_per_session must be between 1 and "
                f"{MAX_CONFIGURED_ENTRIES_PER_SESSION}"
            )
        if type(self.max_concurrent_positions) is not int:
            raise TypeError("max_concurrent_positions must be an exact integer")
        if not 1 <= self.max_concurrent_positions <= MAX_CONFIGURED_CONCURRENT_POSITIONS:
            raise ValueError(
                "max_concurrent_positions must be between 1 and "
                f"{MAX_CONFIGURED_CONCURRENT_POSITIONS}"
            )


@dataclass(frozen=True, slots=True)
class NullSequenceScore:
    net_profit: float
    accepted_entry_count: int
    rejected_entry_count: int

    def __post_init__(self) -> None:
        profit = _finite_number(self.net_profit, name="net_profit")
        for name in ("accepted_entry_count", "rejected_entry_count"):
            value = getattr(self, name)
            if type(value) is not int:
                raise TypeError(f"{name} must be an exact integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        object.__setattr__(self, "net_profit", profit)


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
            raise ValueError(f"repetitions must be between 1 and {MAX_NULL_REPETITIONS}")
        percentile = _finite_number(self.percentile, name="percentile")
        if not 0.0 < percentile < 1.0:
            raise ValueError("percentile must be greater than 0 and less than 1")
        object.__setattr__(self, "percentile", percentile)


@dataclass(frozen=True, slots=True)
class NullDistribution:
    method: NullMethod
    statistics: tuple[float, ...]
    accepted_entry_counts: tuple[int, ...]
    rejected_entry_counts: tuple[int, ...]
    percentile_threshold: float


@dataclass(frozen=True, slots=True)
class NullTestResult:
    passed: bool
    reason_code: str
    observed_score: NullSequenceScore
    seed: int
    repetitions: int
    percentile: float
    evidence_sha256: str
    evidence_opportunity_ids: tuple[str, ...]
    scoring_config: HoldingRuleScoringConfig
    framework_operation_bound: int
    distributions: tuple[NullDistribution, ...]
    trade_count_by_symbol_session: Mapping[str, int]

    @property
    def observed_profit(self) -> float:
        return self.observed_score.net_profit


@dataclass(frozen=True, slots=True)
class _NullEvaluationPlan:
    opportunities: tuple[NullOpportunity, ...]
    group_indexes: tuple[tuple[int, ...], ...]
    evaluation_order: tuple[int, ...]


def _opportunity_order_key(
    item: NullOpportunity,
) -> tuple[date, datetime, str, str]:
    return (
        item.session,
        item.signal_time,
        item.symbol,
        item.opportunity_id,
    )


def _validated_test_config(value: object) -> NullTestConfig:
    if type(value) is not NullTestConfig:
        raise TypeError("config must be an exact NullTestConfig")
    return NullTestConfig(
        seed=value.seed,
        repetitions=value.repetitions,
        percentile=value.percentile,
    )


def _validated_scoring_config(value: object) -> HoldingRuleScoringConfig:
    if type(value) is not HoldingRuleScoringConfig:
        raise TypeError("scoring_config must be an exact HoldingRuleScoringConfig")
    return HoldingRuleScoringConfig(
        scoring_id=value.scoring_id,
        rule_version=value.rule_version,
        cost_model_id=value.cost_model_id,
        cooldown_minutes=value.cooldown_minutes,
        max_entries_per_session=value.max_entries_per_session,
        max_concurrent_positions=value.max_concurrent_positions,
    )


def _validated_opportunities(value: object) -> tuple[NullOpportunity, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("opportunities must be a non-empty exact tuple")
    if len(value) > MAX_NULL_OPPORTUNITIES:
        raise ValueError("opportunities exceed the evidence budget")
    if any(type(item) is not NullOpportunity for item in value):
        raise TypeError("opportunities must contain exact NullOpportunity values")
    if {item.symbol for item in value} != set(PRODUCTION_SYMBOLS):
        raise ValueError("opportunities must cover exactly SPY, QQQ, and IWM")
    reparsed = tuple(
        NullOpportunity(
            opportunity_id=item.opportunity_id,
            symbol=item.symbol,
            session=item.session,
            signal_time=item.signal_time,
            entry_time=item.entry_time,
            exit_time=item.exit_time,
            entered=item.entered,
            holding_rule_net_profit=item.holding_rule_net_profit,
        )
        for item in value
    )
    if any(
        _opportunity_order_key(reparsed[index - 1]) > _opportunity_order_key(reparsed[index])
        for index in range(1, len(reparsed))
    ):
        raise ValueError("opportunities must be canonically sorted")
    opportunity_ids = tuple(item.opportunity_id for item in reparsed)
    if len(set(opportunity_ids)) != len(opportunity_ids):
        raise ValueError("opportunity_id values must be unique")
    slot_keys = tuple((item.symbol, item.session, item.signal_time) for item in reparsed)
    if len(set(slot_keys)) != len(slot_keys):
        raise ValueError("symbol/session signal slots must be unique")
    return reparsed


def _build_plan(opportunities: tuple[NullOpportunity, ...]) -> _NullEvaluationPlan:
    groups: dict[tuple[str, date], list[int]] = {}
    for index, opportunity in enumerate(opportunities):
        groups.setdefault((opportunity.symbol, opportunity.session), []).append(index)
    ordered_groups = tuple(tuple(indexes) for indexes in groups.values())
    active_group_counts = tuple(
        (sum(opportunities[index].entered for index in indexes), len(indexes))
        for indexes in ordered_groups
        if any(opportunities[index].entered for index in indexes)
    )
    if not active_group_counts or any(
        not 0 < entered_count < slot_count for entered_count, slot_count in active_group_counts
    ):
        raise ValueError("every active symbol/session group must be shiftable")
    return _NullEvaluationPlan(
        opportunities=opportunities,
        group_indexes=ordered_groups,
        evaluation_order=tuple(range(len(opportunities))),
    )


def _permuted_mask(plan: _NullEvaluationPlan, *, rng: random.Random) -> tuple[bool, ...]:
    result = [False] * len(plan.opportunities)
    for indexes in plan.group_indexes:
        local = [plan.opportunities[index].entered for index in indexes]
        rng.shuffle(local)
        for index, entered in zip(indexes, local, strict=True):
            result[index] = entered
    return tuple(result)


def _shifted_mask(plan: _NullEvaluationPlan, *, rng: random.Random) -> tuple[bool, ...]:
    result = [False] * len(plan.opportunities)
    for indexes in plan.group_indexes:
        if len(indexes) == 1:
            result[indexes[0]] = plan.opportunities[indexes[0]].entered
            continue
        offset = rng.randrange(1, len(indexes))
        for local_index, source_index in enumerate(indexes):
            target_index = indexes[(local_index + offset) % len(indexes)]
            result[target_index] = plan.opportunities[source_index].entered
    return tuple(result)


def generate_permuted_entry_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    seed: int,
) -> tuple[bool, ...]:
    evidence = _validated_opportunities(opportunities)
    if type(seed) is not int:
        raise TypeError("seed must be an exact integer")
    return _permuted_mask(_build_plan(evidence), rng=random.Random(seed))


def generate_shifted_entry_mask(
    opportunities: tuple[NullOpportunity, ...],
    *,
    seed: int,
) -> tuple[bool, ...]:
    evidence = _validated_opportunities(opportunities)
    if type(seed) is not int:
        raise TypeError("seed must be an exact integer")
    return _shifted_mask(_build_plan(evidence), rng=random.Random(seed))


def _score_sequence(
    plan: _NullEvaluationPlan,
    mask: tuple[bool, ...],
    *,
    config: HoldingRuleScoringConfig,
) -> NullSequenceScore:
    if type(mask) is not tuple or len(mask) != len(plan.opportunities):
        raise ValueError("entry mask must exactly cover the evaluation plan")
    accepted = 0
    rejected = 0
    profit = 0.0
    session_entry_counts: dict[date, int] = {}
    last_exit_by_symbol_session: dict[tuple[str, date], datetime] = {}
    active_positions: list[tuple[datetime, str, date]] = []
    cooldown = timedelta(minutes=config.cooldown_minutes)

    for index in plan.evaluation_order:
        if not mask[index]:
            continue
        opportunity = plan.opportunities[index]
        active_positions = [
            position for position in active_positions if position[0] > opportunity.entry_time
        ]
        key = (opportunity.symbol, opportunity.session)
        previous_exit = last_exit_by_symbol_session.get(key)
        overlaps_holding = previous_exit is not None and opportunity.entry_time < previous_exit
        violates_cooldown = (
            previous_exit is not None and opportunity.entry_time < previous_exit + cooldown
        )
        exceeds_session_entries = (
            session_entry_counts.get(opportunity.session, 0) >= config.max_entries_per_session
        )
        exceeds_positions = len(active_positions) >= config.max_concurrent_positions
        if overlaps_holding or violates_cooldown or exceeds_session_entries or exceeds_positions:
            rejected += 1
            continue
        accepted += 1
        profit += opportunity.holding_rule_net_profit
        session_entry_counts[opportunity.session] = (
            session_entry_counts.get(opportunity.session, 0) + 1
        )
        last_exit_by_symbol_session[key] = opportunity.exit_time
        active_positions.append((opportunity.exit_time, opportunity.symbol, opportunity.session))
    return NullSequenceScore(
        net_profit=profit,
        accepted_entry_count=accepted,
        rejected_entry_count=rejected,
    )


def _nearest_rank_percentile(statistics: tuple[float, ...], percentile: float) -> float:
    ordered = sorted(statistics)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _operation_components(
    config: NullTestConfig,
    scoring_config: HoldingRuleScoringConfig,
) -> tuple[int, int]:
    score_pass = _SCORING_BASE_OPERATIONS_PER_ROW + (scoring_config.max_concurrent_positions)
    operations_per_row = (
        _SETUP_OPERATIONS_PER_ROW
        + score_pass
        + config.repetitions * (_MASK_OPERATIONS_PER_REPETITION_PER_ROW + 2 * score_pass)
    )
    distribution_overhead = 2 * config.repetitions * (math.ceil(math.log2(config.repetitions)) + 4)
    return operations_per_row, distribution_overhead


def null_framework_operation_bound(
    opportunity_count: int,
    *,
    config: NullTestConfig,
    scoring_config: HoldingRuleScoringConfig,
) -> int:
    if type(opportunity_count) is not int:
        raise TypeError("opportunity_count must be an exact integer")
    if not 1 <= opportunity_count <= MAX_NULL_OPPORTUNITIES:
        raise ValueError(f"opportunity_count must be between 1 and {MAX_NULL_OPPORTUNITIES}")
    validated_config = _validated_test_config(config)
    validated_scoring = _validated_scoring_config(scoring_config)
    operations_per_row, distribution_overhead = _operation_components(
        validated_config,
        validated_scoring,
    )
    return opportunity_count * operations_per_row + distribution_overhead


_PRODUCTION_CAPACITY_CONFIG = NullTestConfig(seed=0)
_PRODUCTION_CAPACITY_SCORING = HoldingRuleScoringConfig(
    scoring_id="capacity-bound",
    rule_version="capacity-bound-v1",
    cost_model_id="capacity-bound-v1",
    max_concurrent_positions=MAX_CONFIGURED_CONCURRENT_POSITIONS,
)
_PRODUCTION_OPERATIONS_PER_ROW, _PRODUCTION_DISTRIBUTION_OVERHEAD = _operation_components(
    _PRODUCTION_CAPACITY_CONFIG,
    _PRODUCTION_CAPACITY_SCORING,
)
PRODUCTION_NULL_OPPORTUNITY_CAPACITY = (
    MAX_NULL_WORK_ITEMS - _PRODUCTION_DISTRIBUTION_OVERHEAD
) // _PRODUCTION_OPERATIONS_PER_ROW


def _evidence_sha256(
    opportunities: tuple[NullOpportunity, ...],
    *,
    config: NullTestConfig,
    scoring_config: HoldingRuleScoringConfig,
) -> str:
    payload = {
        "config": {
            "percentile": config.percentile,
            "repetitions": config.repetitions,
            "seed": config.seed,
        },
        "opportunities": [
            {
                "entered": item.entered,
                "entry_time": item.entry_time.isoformat(),
                "exit_time": item.exit_time.isoformat(),
                "holding_rule_net_profit": item.holding_rule_net_profit,
                "opportunity_id": item.opportunity_id,
                "session": item.session.isoformat(),
                "signal_time": item.signal_time.isoformat(),
                "symbol": item.symbol,
            }
            for item in opportunities
        ],
        "scoring_config": {
            "cooldown_minutes": scoring_config.cooldown_minutes,
            "cost_model_id": scoring_config.cost_model_id,
            "max_concurrent_positions": scoring_config.max_concurrent_positions,
            "max_entries_per_session": scoring_config.max_entries_per_session,
            "rule_version": scoring_config.rule_version,
            "scoring_id": scoring_config.scoring_id,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _score_distribution(
    plan: _NullEvaluationPlan,
    *,
    scoring_config: HoldingRuleScoringConfig,
    repetitions: int,
    rng: random.Random,
    method: NullMethod,
) -> tuple[tuple[float, ...], tuple[int, ...], tuple[int, ...]]:
    scores: list[NullSequenceScore] = []
    for _ in range(repetitions):
        if method == "SESSION_SIGNAL_PERMUTATION":
            mask = _permuted_mask(plan, rng=rng)
        else:
            mask = _shifted_mask(plan, rng=rng)
        scores.append(_score_sequence(plan, mask, config=scoring_config))
    return (
        tuple(score.net_profit for score in scores),
        tuple(score.accepted_entry_count for score in scores),
        tuple(score.rejected_entry_count for score in scores),
    )


def run_null_tests(
    opportunities: tuple[NullOpportunity, ...],
    *,
    config: NullTestConfig,
    scoring_config: HoldingRuleScoringConfig,
) -> NullTestResult:
    """Compare observed profit against two internally scored null distributions."""

    validated_config = _validated_test_config(config)
    validated_scoring = _validated_scoring_config(scoring_config)
    canonical_evidence = _validated_opportunities(opportunities)
    operation_bound = null_framework_operation_bound(
        len(canonical_evidence),
        config=validated_config,
        scoring_config=validated_scoring,
    )
    if operation_bound > MAX_NULL_WORK_ITEMS:
        raise ValueError("null test configuration exceeds the framework work budget")
    plan = _build_plan(canonical_evidence)
    observed_mask = tuple(item.entered for item in plan.opportunities)
    observed_score = _score_sequence(plan, observed_mask, config=validated_scoring)

    permutation_statistics, permutation_accepted, permutation_rejected = _score_distribution(
        plan,
        scoring_config=validated_scoring,
        repetitions=validated_config.repetitions,
        rng=random.Random(validated_config.seed),
        method="SESSION_SIGNAL_PERMUTATION",
    )
    shift_statistics, shift_accepted, shift_rejected = _score_distribution(
        plan,
        scoring_config=validated_scoring,
        repetitions=validated_config.repetitions,
        rng=random.Random(validated_config.seed ^ 0x5DEECE66D),
        method="SESSION_SAFE_TIMESTAMP_SHIFT",
    )
    distributions = (
        NullDistribution(
            method="SESSION_SIGNAL_PERMUTATION",
            statistics=permutation_statistics,
            accepted_entry_counts=permutation_accepted,
            rejected_entry_counts=permutation_rejected,
            percentile_threshold=_nearest_rank_percentile(
                permutation_statistics,
                validated_config.percentile,
            ),
        ),
        NullDistribution(
            method="SESSION_SAFE_TIMESTAMP_SHIFT",
            statistics=shift_statistics,
            accepted_entry_counts=shift_accepted,
            rejected_entry_counts=shift_rejected,
            percentile_threshold=_nearest_rank_percentile(
                shift_statistics,
                validated_config.percentile,
            ),
        ),
    )
    passed = all(
        observed_score.net_profit > distribution.percentile_threshold
        for distribution in distributions
    )

    # Reparse immediately before retained evidence/hash construction. No external
    # callback receives the private canonical objects, but this final boundary
    # check also detects accidental internal mutation.
    retained_evidence = _validated_opportunities(plan.opportunities)
    if retained_evidence != canonical_evidence:
        raise ValueError("canonical null evidence changed during evaluation")
    trade_counts = {
        f"{session.isoformat()}:{symbol}": sum(
            retained_evidence[index].entered for index in indexes
        )
        for indexes in plan.group_indexes
        for symbol, session in (
            (retained_evidence[indexes[0]].symbol, retained_evidence[indexes[0]].session),
        )
    }
    return NullTestResult(
        passed=passed,
        reason_code="PASSED_NULL_TEST" if passed else "NULL_TEST_FAILED",
        observed_score=observed_score,
        seed=validated_config.seed,
        repetitions=validated_config.repetitions,
        percentile=validated_config.percentile,
        evidence_sha256=_evidence_sha256(
            retained_evidence,
            config=validated_config,
            scoring_config=validated_scoring,
        ),
        evidence_opportunity_ids=tuple(item.opportunity_id for item in retained_evidence),
        scoring_config=validated_scoring,
        framework_operation_bound=operation_bound,
        distributions=distributions,
        trade_count_by_symbol_session=MappingProxyType(trade_counts),
    )
