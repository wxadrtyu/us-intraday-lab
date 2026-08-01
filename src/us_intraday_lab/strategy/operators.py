from collections.abc import Callable, Mapping
from dataclasses import dataclass

from us_intraday_lab.contracts.strategies import (
    OrderType,
    RiskDefinition,
    StrategyDefinition,
)

type FeatureValue = float | int | None
type FeatureRow = Mapping[str, FeatureValue]
type IndicatorFn = Callable[[FeatureRow], FeatureValue]
type ComparisonFn = Callable[[float, float], bool]


def feature_return_1(features: FeatureRow) -> FeatureValue:
    return features.get("return_1")


def feature_return_3(features: FeatureRow) -> FeatureValue:
    return features.get("return_3")


def feature_ema_spread(features: FeatureRow) -> FeatureValue:
    return features.get("ema_spread")


def feature_rsi(features: FeatureRow) -> FeatureValue:
    return features.get("rsi")


def feature_atr_bps(features: FeatureRow) -> FeatureValue:
    return features.get("atr_bps")


def feature_volume_ratio(features: FeatureRow) -> FeatureValue:
    return features.get("volume_ratio")


def feature_vwap_distance_bps(features: FeatureRow) -> FeatureValue:
    return features.get("vwap_distance_bps")


def feature_range_position(features: FeatureRow) -> FeatureValue:
    return features.get("range_position")


def feature_minutes_from_open(features: FeatureRow) -> FeatureValue:
    return features.get("minutes_from_open")


def compare_gt(left: float, right: float) -> bool:
    return left > right


def compare_gte(left: float, right: float) -> bool:
    return left >= right


def compare_lt(left: float, right: float) -> bool:
    return left < right


def compare_lte(left: float, right: float) -> bool:
    return left <= right


@dataclass(frozen=True)
class ComparisonOperator:
    indicator: str
    indicator_fn: IndicatorFn
    comparison: str
    comparison_fn: ComparisonFn
    threshold: float


@dataclass(frozen=True)
class AllOperator:
    children: tuple["RuleOperator", ...]


@dataclass(frozen=True)
class AnyOperator:
    children: tuple["RuleOperator", ...]


type RuleOperator = ComparisonOperator | AllOperator | AnyOperator


@dataclass(frozen=True)
class CompiledStrategy:
    definition: StrategyDefinition
    strategy_id: str
    definition_fingerprint: str
    symbols: tuple[str, ...]
    entry: RuleOperator
    exit: RuleOperator
    risk: RiskDefinition
    order_type: OrderType
