import math
import re
from dataclasses import dataclass
from typing import cast

from us_intraday_lab.contracts.strategies import (
    AllCondition,
    AnyCondition,
    ComparisonCondition,
    Condition,
    StrategyDefinition,
)

PRODUCTION_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
ALLOWED_INDICATORS = frozenset(
    {
        "return_1",
        "return_3",
        "ema_spread",
        "rsi",
        "atr_bps",
        "volume_ratio",
        "vwap_distance_bps",
        "range_position",
        "minutes_from_open",
    }
)
ALLOWED_COMPARISONS = frozenset({"gt", "gte", "lt", "lte"})
MAX_CONDITION_DEPTH = 3
MAX_LEAF_CONDITIONS = 12
MAX_ENTRIES_PER_SESSION = 3

_LIMIT_OFFSET_FIELDS = frozenset(
    {
        "limit_offset",
        "limit_offset_bps",
        "limit_price",
        "price_offset",
        "price_offset_bps",
    }
)
_EXIT_EXPOSURE_FIELDS = frozenset(
    {
        "action",
        "side",
        "quantity",
        "exposure",
        "target_position",
        "enter",
        "buy",
        "short",
        "leverage",
    }
)
_FORBIDDEN_FIELD_PARTS = frozenset(
    {
        "python",
        "sql",
        "template",
        "url",
        "uri",
        "file",
        "filepath",
        "path",
        "import",
        "callable",
        "callback",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class StrategyValidation:
    passed: bool
    issues: tuple[ValidationIssue, ...]


def _validation(issues: list[ValidationIssue]) -> StrategyValidation:
    ordered = tuple(sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message)))
    return StrategyValidation(passed=not ordered, issues=ordered)


def _field_parts(field: str) -> frozenset[str]:
    normalized = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    return frozenset(part for part in normalized.split("_") if part)


def _is_forbidden_field(field: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    return normalized in _FORBIDDEN_FIELD_PARTS or bool(
        _field_parts(normalized) & _FORBIDDEN_FIELD_PARTS
    )


def _is_limit_offset_field(field: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    parts = _field_parts(normalized)
    return (
        normalized in _LIMIT_OFFSET_FIELDS
        or {"limit", "offset"} <= parts
        or {"price", "offset"} <= parts
    )


def _child_path(path: str, field: str) -> str:
    return f"{path}.{field}" if path else field


def scan_strategy_payload(payload: object) -> StrategyValidation:
    """Scan raw JSON-like input for controls the closed DSL never permits.

    This scan does not parse, import, interpolate, resolve, or execute field values.
    Pydantic remains responsible for structural parsing after this preflight passes.
    """

    issues: list[ValidationIssue] = []

    def walk(value: object, path: str, inside_exit: bool) -> None:
        if callable(value):
            issues.append(
                ValidationIssue(
                    code="DSL_FORBIDDEN_CALLABLE",
                    path=path,
                    message="callable values are not permitted in strategy payloads",
                )
            )
            return
        if type(value) is dict:
            mapping = value
            string_keys = sorted(key for key in mapping if type(key) is str)
            if len(string_keys) != len(mapping):
                issues.append(
                    ValidationIssue(
                        code="DSL_UNSAFE_PAYLOAD_TYPE",
                        path=path,
                        message="strategy object keys must be strings",
                    )
                )
            for field in string_keys:
                child = _child_path(path, field)
                normalized = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
                child_inside_exit = inside_exit or (not path and normalized == "exit")
                if _is_limit_offset_field(normalized):
                    issues.append(
                        ValidationIssue(
                            code="DSL_UNSUPPORTED_LIMIT_OFFSET",
                            path=child,
                            message=(
                                "strategy-controlled limit pricing is not supported by this DSL"
                            ),
                        )
                    )
                elif child_inside_exit and normalized in _EXIT_EXPOSURE_FIELDS:
                    issues.append(
                        ValidationIssue(
                            code="DSL_EXIT_CAN_INCREASE_EXPOSURE",
                            path=child,
                            message=f"exit field '{field}' can increase exposure",
                        )
                    )
                elif _is_forbidden_field(normalized):
                    issues.append(
                        ValidationIssue(
                            code="DSL_FORBIDDEN_FIELD",
                            path=child,
                            message=f"field '{field}' is not permitted in strategy payloads",
                        )
                    )
                walk(mapping[field], child, child_inside_exit)
            return
        if type(value) in {list, tuple}:
            sequence = cast(list[object] | tuple[object, ...], value)
            for index, item in enumerate(sequence):
                walk(item, f"{path}[{index}]", inside_exit)
            return
        if value is None or type(value) in {str, int, float, bool}:
            return
        issues.append(
            ValidationIssue(
                code="DSL_UNSAFE_PAYLOAD_TYPE",
                path=path,
                message="strategy payload contains a non-JSON value",
            )
        )

    walk(payload, "", False)
    return _validation(issues)


def _visit_condition(
    condition: Condition,
    path: str,
    depth: int,
    issues: list[ValidationIssue],
) -> int:
    if depth > MAX_CONDITION_DEPTH:
        issues.append(
            ValidationIssue(
                code="DSL_CONDITION_DEPTH_EXCEEDED",
                path=path,
                message=f"condition nesting depth must not exceed {MAX_CONDITION_DEPTH}",
            )
        )
    if type(condition) is ComparisonCondition:
        indicator = condition.__dict__.get("indicator")
        comparison = condition.__dict__.get("op")
        threshold = condition.__dict__.get("value")
        if type(indicator) is not str or indicator not in ALLOWED_INDICATORS:
            issues.append(
                ValidationIssue(
                    code="DSL_UNKNOWN_INDICATOR",
                    path=f"{path}.indicator",
                    message="indicator is not a literal allowlisted name",
                )
            )
        if type(comparison) is not str or comparison not in ALLOWED_COMPARISONS:
            issues.append(
                ValidationIssue(
                    code="DSL_UNKNOWN_COMPARISON",
                    path=f"{path}.op",
                    message="comparison is not a literal allowlisted operator",
                )
            )
        if (
            type(threshold) not in {int, float}
            or type(threshold) is bool
            or not math.isfinite(cast(float, threshold))
        ):
            issues.append(
                ValidationIssue(
                    code="DSL_NON_FINITE_THRESHOLD",
                    path=f"{path}.value",
                    message="comparison threshold must be finite",
                )
            )
        return 1
    if type(condition) is AllCondition:
        return sum(
            _visit_condition(child, f"{path}.all[{index}]", depth + 1, issues)
            for index, child in enumerate(condition.all)
        )
    if type(condition) is AnyCondition:
        return sum(
            _visit_condition(child, f"{path}.any[{index}]", depth + 1, issues)
            for index, child in enumerate(condition.any)
        )
    issues.append(
        ValidationIssue(
            code="DSL_UNKNOWN_CONDITION",
            path=path,
            message="condition node is not an allowlisted DSL node",
        )
    )
    return 0


def _condition_branches(condition: Condition) -> tuple[tuple[ComparisonCondition, ...], ...]:
    if type(condition) is ComparisonCondition:
        return ((condition,),)
    if type(condition) is AnyCondition:
        return tuple(branch for child in condition.any for branch in _condition_branches(child))
    if type(condition) is AllCondition:
        branches: tuple[tuple[ComparisonCondition, ...], ...] = ((),)
        for child in condition.all:
            child_branches = _condition_branches(child)
            branches = tuple(
                existing + addition for existing in branches for addition in child_branches
            )
        return branches
    return ()


def _branch_has_contradiction(branch: tuple[ComparisonCondition, ...]) -> bool:
    by_indicator: dict[str, list[ComparisonCondition]] = {}
    for condition in branch:
        indicator = condition.__dict__.get("indicator")
        comparison = condition.__dict__.get("op")
        threshold = condition.__dict__.get("value")
        if (
            type(indicator) is str
            and indicator in ALLOWED_INDICATORS
            and type(comparison) is str
            and comparison in ALLOWED_COMPARISONS
            and type(threshold) in {int, float}
            and type(threshold) is not bool
            and math.isfinite(cast(float, threshold))
        ):
            by_indicator.setdefault(indicator, []).append(condition)

    for conditions in by_indicator.values():
        lower_value = -math.inf
        lower_strict = False
        upper_value = math.inf
        upper_strict = False
        for condition in conditions:
            if condition.op in {"gt", "gte"}:
                strict = condition.op == "gt"
                if condition.value > lower_value:
                    lower_value = condition.value
                    lower_strict = strict
                elif condition.value == lower_value:
                    lower_strict = lower_strict or strict
            else:
                strict = condition.op == "lt"
                if condition.value < upper_value:
                    upper_value = condition.value
                    upper_strict = strict
                elif condition.value == upper_value:
                    upper_strict = upper_strict or strict
        if lower_value > upper_value:
            return True
        if lower_value == upper_value and (lower_strict or upper_strict):
            return True
    return False


def _check_contradictions(condition: Condition, path: str, issues: list[ValidationIssue]) -> None:
    if any(_branch_has_contradiction(branch) for branch in _condition_branches(condition)):
        issues.append(
            ValidationIssue(
                code="DSL_CONTRADICTORY_CONDITIONS",
                path=path,
                message="a conjunctive branch contains mutually exclusive comparisons",
            )
        )


def validate_strategy(strategy: StrategyDefinition) -> StrategyValidation:
    """Validate bounded domain policy on an already parsed strategy definition."""

    if type(strategy) is not StrategyDefinition:
        return _validation(
            [
                ValidationIssue(
                    code="DSL_UNSAFE_STRATEGY_TYPE",
                    path="",
                    message="validator requires an exact StrategyDefinition instance",
                )
            ]
        )

    issues: list[ValidationIssue] = []
    for index, symbol in enumerate(strategy.symbols):
        if symbol not in PRODUCTION_SYMBOLS:
            issues.append(
                ValidationIssue(
                    code="DSL_UNSUPPORTED_SYMBOL",
                    path=f"symbols[{index}]",
                    message=f"symbol '{symbol}' is not supported for production strategies",
                )
            )
    if not strategy.symbols:
        issues.append(
            ValidationIssue(
                code="DSL_EMPTY_SYMBOLS",
                path="symbols",
                message="at least one production symbol is required",
            )
        )
    if strategy.signal_bar_size != "15min":
        issues.append(
            ValidationIssue(
                code="DSL_UNSUPPORTED_SIGNAL_BAR",
                path="signal_bar_size",
                message="only completed 15-minute signal bars are supported",
            )
        )

    risk_fields = (
        "stop_loss_bps",
        "take_profit_bps",
        "max_holding_minutes",
        "cooldown_minutes",
    )
    for field in risk_fields:
        value = strategy.risk.__dict__[field]
        if value <= 0:
            issues.append(
                ValidationIssue(
                    code="DSL_NON_POSITIVE_RISK_CONTROL",
                    path=f"risk.{field}",
                    message=f"{field} must be greater than zero",
                )
            )
    if strategy.risk.max_entries_per_session <= 0:
        issues.append(
            ValidationIssue(
                code="DSL_NON_POSITIVE_MAX_ENTRIES",
                path="risk.max_entries_per_session",
                message="max_entries_per_session must be greater than zero",
            )
        )
    elif strategy.risk.max_entries_per_session > MAX_ENTRIES_PER_SESSION:
        issues.append(
            ValidationIssue(
                code="DSL_MAX_ENTRIES_EXCEEDED",
                path="risk.max_entries_per_session",
                message=f"max_entries_per_session must not exceed {MAX_ENTRIES_PER_SESSION}",
            )
        )

    entry_leaves = _visit_condition(strategy.entry, "entry", 1, issues)
    exit_leaves = _visit_condition(strategy.exit, "exit", 1, issues)
    if entry_leaves + exit_leaves > MAX_LEAF_CONDITIONS:
        issues.append(
            ValidationIssue(
                code="DSL_CONDITION_LEAF_LIMIT_EXCEEDED",
                path="entry",
                message=(
                    f"entry and exit rules must contain at most {MAX_LEAF_CONDITIONS} "
                    "leaf conditions in total"
                ),
            )
        )
    _check_contradictions(strategy.entry, "entry", issues)
    _check_contradictions(strategy.exit, "exit", issues)
    return _validation(issues)
