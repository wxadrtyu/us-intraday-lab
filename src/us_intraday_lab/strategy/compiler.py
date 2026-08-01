import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType

from us_intraday_lab.contracts.strategies import (
    AllCondition,
    AnyCondition,
    ComparisonCondition,
    Condition,
    StrategyDefinition,
)
from us_intraday_lab.strategy.operators import (
    AllOperator,
    AnyOperator,
    ComparisonFn,
    ComparisonOperator,
    CompiledStrategy,
    IndicatorFn,
    RuleOperator,
    compare_gt,
    compare_gte,
    compare_lt,
    compare_lte,
    feature_atr_bps,
    feature_ema_spread,
    feature_minutes_from_open,
    feature_range_position,
    feature_return_1,
    feature_return_3,
    feature_rsi,
    feature_volume_ratio,
    feature_vwap_distance_bps,
)
from us_intraday_lab.strategy.validator import ValidationIssue, validate_strategy

_INDICATOR_DISPATCH: Mapping[str, IndicatorFn] = MappingProxyType(
    {
        "return_1": feature_return_1,
        "return_3": feature_return_3,
        "ema_spread": feature_ema_spread,
        "rsi": feature_rsi,
        "atr_bps": feature_atr_bps,
        "volume_ratio": feature_volume_ratio,
        "vwap_distance_bps": feature_vwap_distance_bps,
        "range_position": feature_range_position,
        "minutes_from_open": feature_minutes_from_open,
    }
)
INDICATORS = _INDICATOR_DISPATCH

_COMPARISON_DISPATCH: Mapping[str, ComparisonFn] = MappingProxyType(
    {
        "gt": compare_gt,
        "gte": compare_gte,
        "lt": compare_lt,
        "lte": compare_lte,
    }
)
COMPARISONS = _COMPARISON_DISPATCH


def strategy_definition_fingerprint(strategy: StrategyDefinition) -> str:
    canonical = json.dumps(
        strategy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{strategy.strategy_id}@sha256:{digest}"


class StrategyCompileError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        issues: tuple[ValidationIssue, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.issues = issues


def _compile_condition(condition: Condition) -> RuleOperator:
    if type(condition) is ComparisonCondition:
        return ComparisonOperator(
            indicator=condition.indicator,
            indicator_fn=_INDICATOR_DISPATCH[condition.indicator],
            comparison=condition.op,
            comparison_fn=_COMPARISON_DISPATCH[condition.op],
            threshold=condition.value,
        )
    if type(condition) is AllCondition:
        return AllOperator(children=tuple(_compile_condition(child) for child in condition.all))
    if type(condition) is AnyCondition:
        return AnyOperator(children=tuple(_compile_condition(child) for child in condition.any))
    raise StrategyCompileError(
        code="DSL_UNKNOWN_CONDITION",
        message="compiler received an unknown condition node",
    )


def compile_strategy(strategy: StrategyDefinition) -> CompiledStrategy:
    if type(strategy) is not StrategyDefinition:
        raise StrategyCompileError(
            code="DSL_UNSAFE_COMPILE_INPUT",
            message="compiler accepts only exact validated StrategyDefinition instances",
        )

    validation = validate_strategy(strategy)
    if not validation.passed:
        raise StrategyCompileError(
            code="DSL_VALIDATION_FAILED",
            message="strategy failed static domain validation",
            issues=validation.issues,
        )

    return CompiledStrategy(
        definition=strategy,
        strategy_id=strategy.strategy_id,
        definition_fingerprint=strategy_definition_fingerprint(strategy),
        symbols=strategy.symbols,
        entry=_compile_condition(strategy.entry),
        exit=_compile_condition(strategy.exit),
        risk=strategy.risk,
        order_type=strategy.order_type,
    )
