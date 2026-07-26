import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

from us_intraday_lab.contracts.strategies import (
    AllCondition,
    AnyCondition,
    ComparisonCondition,
    Condition,
    RiskDefinition,
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
MAX_CONTRADICTION_BRANCHES = 16
MAX_CONTRADICTION_WORK = 96

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
_COMPACT_FIELD_ALIASES = {
    "limitprice": "limit_price",
    "limitoffset": "limit_offset",
    "limitoffsetbps": "limit_offset_bps",
    "limitpriceoffset": "limit_price_offset",
    "limitpriceoffsetbps": "limit_price_offset_bps",
    "priceoffset": "price_offset",
    "priceoffsetbps": "price_offset_bps",
    "targetposition": "target_position",
    "pythoncode": "python_code",
    "importmodule": "import_module",
}


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


def _canonical_field(field: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", field.casefold())
    alias = _COMPACT_FIELD_ALIASES.get(compact)
    if alias is not None:
        return alias
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field)
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", separated)
    return re.sub(r"[^a-z0-9]+", "_", separated.casefold()).strip("_")


def _field_parts(field: str) -> frozenset[str]:
    return frozenset(part for part in field.split("_") if part)


def _is_forbidden_field(canonical_field: str) -> bool:
    return canonical_field in _FORBIDDEN_FIELD_PARTS or bool(
        _field_parts(canonical_field) & _FORBIDDEN_FIELD_PARTS
    )


def _is_limit_offset_field(canonical_field: str) -> bool:
    parts = _field_parts(canonical_field)
    return (
        canonical_field in _LIMIT_OFFSET_FIELDS
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
                canonical_field = _canonical_field(field)
                child = _child_path(path, canonical_field)
                child_inside_exit = inside_exit or (not path and canonical_field == "exit")
                if _is_limit_offset_field(canonical_field):
                    issues.append(
                        ValidationIssue(
                            code="DSL_UNSUPPORTED_LIMIT_OFFSET",
                            path=child,
                            message=(
                                "strategy-controlled limit pricing is not supported by this DSL"
                            ),
                        )
                    )
                elif child_inside_exit and canonical_field in _EXIT_EXPOSURE_FIELDS:
                    issues.append(
                        ValidationIssue(
                            code="DSL_EXIT_CAN_INCREASE_EXPOSURE",
                            path=child,
                            message=f"exit field '{canonical_field}' can increase exposure",
                        )
                    )
                elif _is_forbidden_field(canonical_field):
                    issues.append(
                        ValidationIssue(
                            code="DSL_FORBIDDEN_FIELD",
                            path=child,
                            message=(
                                f"field '{canonical_field}' is not permitted in strategy payloads"
                            ),
                        )
                    )
                walk(mapping[field], child, child_inside_exit)
            return
        if type(value) is list:
            sequence = cast(list[object], value)
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


@dataclass(frozen=True)
class _ConditionStats:
    leaves: int
    structurally_valid: bool


def _model_data(model: object) -> dict[str, object]:
    return cast(dict[str, object], object.__getattribute__(model, "__dict__"))


def _missing_fields(
    data: dict[str, object],
    fields: tuple[str, ...],
    path: str,
    issues: list[ValidationIssue],
) -> bool:
    missing = False
    for field in fields:
        if field not in data:
            missing = True
            issues.append(
                ValidationIssue(
                    code="DSL_MISSING_FIELD",
                    path=_child_path(path, field),
                    message=f"required field '{field}' is missing",
                )
            )
    return missing


def _unexpected_fields(
    data: dict[str, object],
    allowed_fields: tuple[str, ...],
    path: str,
    issues: list[ValidationIssue],
) -> bool:
    unexpected: list[str] = []
    invalid_key = False
    allowed = frozenset(allowed_fields)
    for field in data:
        if type(field) is not str:
            invalid_key = True
        elif field not in allowed:
            unexpected.append(field)
    for field in sorted(unexpected):
        issues.append(
            ValidationIssue(
                code="DSL_UNEXPECTED_FIELD",
                path=_child_path(path, field),
                message=f"field '{field}' is not part of the closed strategy contract",
            )
        )
    if invalid_key:
        issues.append(
            ValidationIssue(
                code="DSL_UNEXPECTED_FIELD",
                path=path,
                message="model storage contains a non-string field name",
            )
        )
    return bool(unexpected) or invalid_key


def _visit_condition(
    condition: object,
    path: str,
    depth: int,
    issues: list[ValidationIssue],
) -> _ConditionStats:
    if depth > MAX_CONDITION_DEPTH:
        issues.append(
            ValidationIssue(
                code="DSL_CONDITION_DEPTH_EXCEEDED",
                path=path,
                message=f"condition nesting depth must not exceed {MAX_CONDITION_DEPTH}",
            )
        )
        return _ConditionStats(leaves=0, structurally_valid=False)

    if type(condition) is ComparisonCondition:
        data = _model_data(condition)
        valid = not _missing_fields(data, ("indicator", "op", "value"), path, issues)
        valid = not _unexpected_fields(data, ("indicator", "op", "value"), path, issues) and valid
        indicator = data.get("indicator")
        comparison = data.get("op")
        threshold = data.get("value")
        if "indicator" in data and (
            type(indicator) is not str or indicator not in ALLOWED_INDICATORS
        ):
            valid = False
            issues.append(
                ValidationIssue(
                    code="DSL_UNKNOWN_INDICATOR",
                    path=f"{path}.indicator",
                    message="indicator is not a literal allowlisted name",
                )
            )
        if "op" in data and (type(comparison) is not str or comparison not in ALLOWED_COMPARISONS):
            valid = False
            issues.append(
                ValidationIssue(
                    code="DSL_UNKNOWN_COMPARISON",
                    path=f"{path}.op",
                    message="comparison is not a literal allowlisted operator",
                )
            )
        if "value" in data and (type(threshold) is not float or not math.isfinite(threshold)):
            valid = False
            issues.append(
                ValidationIssue(
                    code="DSL_NON_FINITE_THRESHOLD",
                    path=f"{path}.value",
                    message="comparison threshold must be an exact finite float",
                )
            )
        return _ConditionStats(leaves=1, structurally_valid=valid)

    if type(condition) is AllCondition or type(condition) is AnyCondition:
        data = _model_data(condition)
        field = "all" if type(condition) is AllCondition else "any"
        closed = not _unexpected_fields(data, (field,), path, issues)
        if field not in data:
            _missing_fields(data, (field,), path, issues)
            return _ConditionStats(leaves=0, structurally_valid=False)
        children = data[field]
        if type(children) is not tuple:
            issues.append(
                ValidationIssue(
                    code="DSL_INVALID_CONDITION_CONTAINER",
                    path=f"{path}.{field}",
                    message=f"{field} conditions must be stored in an exact tuple",
                )
            )
            return _ConditionStats(leaves=0, structurally_valid=False)
        leaves = 0
        valid = closed
        for index, child in enumerate(cast(tuple[object, ...], children)):
            child_stats = _visit_condition(
                child,
                f"{path}.{field}[{index}]",
                depth + 1,
                issues,
            )
            leaves += child_stats.leaves
            valid = valid and child_stats.structurally_valid
        return _ConditionStats(leaves=leaves, structurally_valid=valid)

    issues.append(
        ValidationIssue(
            code="DSL_UNKNOWN_CONDITION",
            path=path,
            message="condition node is not an allowlisted DSL node",
        )
    )
    return _ConditionStats(leaves=0, structurally_valid=False)


def _condition_complexity(condition: Condition) -> tuple[int, int]:
    if type(condition) is ComparisonCondition:
        return (1, 1)

    data = _model_data(condition)
    if type(condition) is AnyCondition:
        branches = 0
        work = 0
        for child in cast(tuple[Condition, ...], data["any"]):
            child_branches, child_work = _condition_complexity(child)
            branches = min(MAX_CONTRADICTION_BRANCHES + 1, branches + child_branches)
            work = min(MAX_CONTRADICTION_WORK + 1, work + child_work)
        return (branches, work)

    branches = 1
    work = 0
    for child in cast(tuple[Condition, ...], data["all"]):
        child_branches, child_work = _condition_complexity(child)
        combined_work = work * child_branches + child_work * branches
        branches = min(MAX_CONTRADICTION_BRANCHES + 1, branches * child_branches)
        work = min(MAX_CONTRADICTION_WORK + 1, combined_work)
    return (branches, work)


def _iter_all_branches(
    children: tuple[Condition, ...],
    index: int,
    prefix: tuple[ComparisonCondition, ...],
) -> Iterator[tuple[ComparisonCondition, ...]]:
    if index == len(children):
        yield prefix
        return
    for addition in _iter_condition_branches(children[index]):
        yield from _iter_all_branches(children, index + 1, prefix + addition)


def _iter_condition_branches(
    condition: Condition,
) -> Iterator[tuple[ComparisonCondition, ...]]:
    if type(condition) is ComparisonCondition:
        yield (condition,)
        return
    data = _model_data(condition)
    if type(condition) is AnyCondition:
        for child in cast(tuple[Condition, ...], data["any"]):
            yield from _iter_condition_branches(child)
        return
    children = cast(tuple[Condition, ...], data["all"])
    yield from _iter_all_branches(children, 0, ())


def _branch_has_contradiction(branch: tuple[ComparisonCondition, ...]) -> bool:
    by_indicator: dict[str, list[tuple[str, float]]] = {}
    for condition in branch:
        data = _model_data(condition)
        indicator = cast(str, data["indicator"])
        comparison = cast(str, data["op"])
        threshold = cast(float, data["value"])
        by_indicator.setdefault(indicator, []).append((comparison, threshold))

    for conditions in by_indicator.values():
        lower_value = -math.inf
        lower_strict = False
        upper_value = math.inf
        upper_strict = False
        for comparison, threshold in conditions:
            if comparison in {"gt", "gte"}:
                strict = comparison == "gt"
                if threshold > lower_value:
                    lower_value = threshold
                    lower_strict = strict
                elif threshold == lower_value:
                    lower_strict = lower_strict or strict
            else:
                strict = comparison == "lt"
                if threshold < upper_value:
                    upper_value = threshold
                    upper_strict = strict
                elif threshold == upper_value:
                    upper_strict = upper_strict or strict
        if lower_value > upper_value:
            return True
        if lower_value == upper_value and (lower_strict or upper_strict):
            return True
    return False


def _check_contradictions(
    condition: Condition,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    branches, work = _condition_complexity(condition)
    if branches > MAX_CONTRADICTION_BRANCHES or work > MAX_CONTRADICTION_WORK:
        issues.append(
            ValidationIssue(
                code="DSL_CONTRADICTION_BUDGET_EXCEEDED",
                path=path,
                message=("condition contradiction analysis exceeds the static branch/work budget"),
            )
        )
        return
    if any(_branch_has_contradiction(branch) for branch in _iter_condition_branches(condition)):
        issues.append(
            ValidationIssue(
                code="DSL_CONTRADICTORY_CONDITIONS",
                path=path,
                message="a conjunctive branch contains mutually exclusive comparisons",
            )
        )


def _validate_risk(risk: object, issues: list[ValidationIssue]) -> None:
    if type(risk) is not RiskDefinition:
        issues.append(
            ValidationIssue(
                code="DSL_INVALID_RISK",
                path="risk",
                message="risk must be an exact RiskDefinition instance",
            )
        )
        return

    data = _model_data(risk)
    numeric_fields = (
        "stop_loss_bps",
        "take_profit_bps",
        "max_holding_minutes",
        "cooldown_minutes",
        "max_entries_per_session",
    )
    _unexpected_fields(data, numeric_fields + ("sizing_preset",), "risk", issues)
    _missing_fields(data, numeric_fields + ("sizing_preset",), "risk", issues)
    for field in numeric_fields:
        if field not in data:
            continue
        value = data[field]
        if type(value) is not int:
            issues.append(
                ValidationIssue(
                    code="DSL_INVALID_RISK_FIELD",
                    path=f"risk.{field}",
                    message=f"{field} must be an exact integer",
                )
            )
            continue
        numeric_value = value
        if field == "max_entries_per_session":
            if numeric_value <= 0:
                issues.append(
                    ValidationIssue(
                        code="DSL_NON_POSITIVE_MAX_ENTRIES",
                        path=f"risk.{field}",
                        message="max_entries_per_session must be greater than zero",
                    )
                )
            elif numeric_value > MAX_ENTRIES_PER_SESSION:
                issues.append(
                    ValidationIssue(
                        code="DSL_MAX_ENTRIES_EXCEEDED",
                        path=f"risk.{field}",
                        message=(
                            f"max_entries_per_session must not exceed {MAX_ENTRIES_PER_SESSION}"
                        ),
                    )
                )
        elif numeric_value <= 0:
            issues.append(
                ValidationIssue(
                    code="DSL_NON_POSITIVE_RISK_CONTROL",
                    path=f"risk.{field}",
                    message=f"{field} must be greater than zero",
                )
            )

    if "sizing_preset" in data:
        sizing = data["sizing_preset"]
        if type(sizing) is not str or sizing not in {
            "equal_cash_conservative",
            "equal_risk_conservative",
        }:
            issues.append(
                ValidationIssue(
                    code="DSL_INVALID_SIZING_PRESET",
                    path="risk.sizing_preset",
                    message="sizing_preset is not allowlisted",
                )
            )


def validate_strategy(strategy: StrategyDefinition) -> StrategyValidation:
    """Re-establish structure and domain policy on an untrusted exact model."""

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
    data = _model_data(strategy)
    required_fields = (
        "strategy_id",
        "dsl_version",
        "symbols",
        "signal_bar_size",
        "entry",
        "exit",
        "risk",
        "order_type",
    )
    _unexpected_fields(data, required_fields, "", issues)
    _missing_fields(data, required_fields, "", issues)

    if "strategy_id" in data:
        strategy_id = data["strategy_id"]
        if type(strategy_id) is not str or not strategy_id:
            issues.append(
                ValidationIssue(
                    code="DSL_INVALID_STRATEGY_ID",
                    path="strategy_id",
                    message="strategy_id must be an exact non-empty string",
                )
            )
    if "dsl_version" in data:
        version = data["dsl_version"]
        if type(version) is not str or version != "1.0.0":
            issues.append(
                ValidationIssue(
                    code="DSL_UNSUPPORTED_DSL_VERSION",
                    path="dsl_version",
                    message="only DSL version 1.0.0 is supported",
                )
            )
    if "symbols" in data:
        symbols = data["symbols"]
        if type(symbols) is not tuple:
            issues.append(
                ValidationIssue(
                    code="DSL_INVALID_SYMBOLS_CONTAINER",
                    path="symbols",
                    message="symbols must be stored in an exact tuple",
                )
            )
        else:
            symbol_tuple = cast(tuple[object, ...], symbols)
            if not symbol_tuple:
                issues.append(
                    ValidationIssue(
                        code="DSL_EMPTY_SYMBOLS",
                        path="symbols",
                        message="at least one production symbol is required",
                    )
                )
            for index, symbol in enumerate(symbol_tuple):
                if type(symbol) is not str:
                    issues.append(
                        ValidationIssue(
                            code="DSL_INVALID_SYMBOL_TYPE",
                            path=f"symbols[{index}]",
                            message="symbols must contain exact strings",
                        )
                    )
                elif symbol not in PRODUCTION_SYMBOLS:
                    issues.append(
                        ValidationIssue(
                            code="DSL_UNSUPPORTED_SYMBOL",
                            path=f"symbols[{index}]",
                            message=f"symbol '{symbol}' is not supported for production strategies",
                        )
                    )
    if "signal_bar_size" in data:
        bar_size = data["signal_bar_size"]
        if type(bar_size) is not str or bar_size != "15min":
            issues.append(
                ValidationIssue(
                    code="DSL_UNSUPPORTED_SIGNAL_BAR",
                    path="signal_bar_size",
                    message="only completed 15-minute signal bars are supported",
                )
            )
    if "risk" in data:
        _validate_risk(data["risk"], issues)
    if "order_type" in data:
        order_type = data["order_type"]
        if type(order_type) is not str or order_type not in {"market", "limit"}:
            issues.append(
                ValidationIssue(
                    code="DSL_UNSUPPORTED_ORDER_TYPE",
                    path="order_type",
                    message="order_type must be market or limit",
                )
            )

    condition_stats: dict[str, _ConditionStats] = {}
    for path in ("entry", "exit"):
        if path in data:
            condition_stats[path] = _visit_condition(data[path], path, 1, issues)

    if "entry" in condition_stats and "exit" in condition_stats:
        entry_stats = condition_stats["entry"]
        exit_stats = condition_stats["exit"]
        total_leaves = entry_stats.leaves + exit_stats.leaves
        if total_leaves > MAX_LEAF_CONDITIONS:
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
        elif entry_stats.structurally_valid and exit_stats.structurally_valid:
            _check_contradictions(cast(Condition, data["entry"]), "entry", issues)
            _check_contradictions(cast(Condition, data["exit"]), "exit", issues)
    return _validation(issues)
