import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from us_intraday_lab.contracts.strategies import (
    AllCondition,
    AnyCondition,
    ComparisonCondition,
    RiskDefinition,
    StrategyDefinition,
)
from us_intraday_lab.strategy.validator import (
    ValidationIssue,
    scan_strategy_payload,
    validate_strategy,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "strategies"


def _payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "valid_momentum_pullback.json").read_text(encoding="utf-8"))


def _strategy() -> StrategyDefinition:
    return StrategyDefinition.model_validate(_payload())


def _codes(strategy: StrategyDefinition) -> set[str]:
    return {issue.code for issue in validate_strategy(strategy).issues}


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda strategy: StrategyDefinition.model_construct(
                **{**strategy.__dict__, "symbols": ("SPY", "DIA")}
            ),
            "DSL_UNSUPPORTED_SYMBOL",
        ),
        (
            lambda strategy: StrategyDefinition.model_construct(
                **{
                    **strategy.__dict__,
                    "risk": RiskDefinition.model_construct(
                        **{**strategy.risk.__dict__, "max_entries_per_session": 4}
                    ),
                }
            ),
            "DSL_MAX_ENTRIES_EXCEEDED",
        ),
        (
            lambda strategy: StrategyDefinition.model_construct(
                **{**strategy.__dict__, "signal_bar_size": "5min"}
            ),
            "DSL_UNSUPPORTED_SIGNAL_BAR",
        ),
    ],
)
def test_typed_validator_rejects_top_level_domain_limits(mutate: Any, expected_code: str) -> None:
    assert expected_code in _codes(mutate(_strategy()))


@pytest.mark.parametrize(
    "field",
    [
        "stop_loss_bps",
        "take_profit_bps",
        "max_holding_minutes",
        "cooldown_minutes",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_typed_validator_rejects_non_positive_risk_controls(field: str, value: int) -> None:
    strategy = _strategy()
    risk = RiskDefinition.model_construct(**{**strategy.risk.__dict__, field: value})
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "risk": risk})

    issues = validate_strategy(invalid).issues

    assert (
        ValidationIssue(
            code="DSL_NON_POSITIVE_RISK_CONTROL",
            path=f"risk.{field}",
            message=f"{field} must be greater than zero",
        )
        in issues
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("limit_offset", 10, "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("limit_offset_bps", 10, "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("limit_price", 620.0, "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("price_offset", -5, "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("limit_price_offset_bps", 5, "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("python", "print('unsafe')", "DSL_FORBIDDEN_FIELD"),
        ("sql", "select * from secrets", "DSL_FORBIDDEN_FIELD"),
        ("template", "{{ config }}", "DSL_FORBIDDEN_FIELD"),
        ("url", "https://example.invalid", "DSL_FORBIDDEN_FIELD"),
        ("file_path", "C:/secrets.txt", "DSL_FORBIDDEN_FIELD"),
        ("import_module", "os", "DSL_FORBIDDEN_FIELD"),
        ("callback", lambda: None, "DSL_FORBIDDEN_CALLABLE"),
    ],
)
def test_raw_scan_rejects_non_dsl_strategy_controls(
    field: str, value: object, expected_code: str
) -> None:
    payload = _payload()
    payload[field] = value

    assert expected_code in {issue.code for issue in scan_strategy_payload(payload).issues}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("action", "enter"),
        ("side", "buy"),
        ("quantity", 10),
        ("exposure", 1.0),
        ("target_position", 100),
        ("enter", True),
        ("buy", True),
        ("short", True),
        ("leverage", 2),
    ],
)
def test_raw_scan_rejects_exit_fields_that_can_increase_exposure(field: str, value: object) -> None:
    payload = _payload()
    payload["exit"] = {"all": [payload["exit"], {field: value}]}

    issues = scan_strategy_payload(payload).issues

    assert any(
        issue.code == "DSL_EXIT_CAN_INCREASE_EXPOSURE" and issue.path == f"exit.all[1].{field}"
        for issue in issues
    )


def test_raw_scan_rejects_invalid_fixture_before_pydantic_parsing() -> None:
    payload = json.loads((FIXTURES / "invalid_freeform_code.json").read_text(encoding="utf-8"))

    result = scan_strategy_payload(payload)

    assert not result.passed
    assert result.issues == (
        ValidationIssue(
            code="DSL_FORBIDDEN_FIELD",
            path="python",
            message="field 'python' is not permitted in strategy payloads",
        ),
    )


def test_raw_scan_orders_all_issues_by_path_then_code() -> None:
    payload = _payload()
    payload["z_url"] = "https://example.invalid"
    payload["a_python"] = "pass"
    payload["exit"] = {"side": "buy", "action": "enter"}

    issues = scan_strategy_payload(payload).issues

    assert [issue.path for issue in issues] == [
        "a_python",
        "exit.action",
        "exit.side",
        "z_url",
    ]


def test_typed_validator_rejects_unknown_indicator_and_comparison() -> None:
    strategy = _strategy()
    unknown_indicator = ComparisonCondition.model_construct(
        indicator="module.function", op="gt", value=0.0
    )
    unknown_comparison = ComparisonCondition.model_construct(
        indicator="rsi", op="invoke", value=50.0
    )
    entry = AllCondition.model_construct(all=(unknown_indicator, unknown_comparison))
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": entry})

    issues = validate_strategy(invalid).issues

    assert [(issue.code, issue.path) for issue in issues] == [
        ("DSL_UNKNOWN_INDICATOR", "entry.all[0].indicator"),
        ("DSL_UNKNOWN_COMPARISON", "entry.all[1].op"),
    ]


def test_typed_validator_rejects_condition_depth_above_three() -> None:
    strategy = _strategy()
    leaf = ComparisonCondition(indicator="rsi", op="lt", value=45.0)
    too_deep = AllCondition.model_construct(
        all=(AnyCondition.model_construct(any=(AllCondition.model_construct(all=(leaf,)),)),)
    )
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": too_deep})

    issues = validate_strategy(invalid).issues

    assert any(
        issue.code == "DSL_CONDITION_DEPTH_EXCEEDED" and issue.path == "entry.all[0].any[0].all[0]"
        for issue in issues
    )


def test_typed_validator_rejects_more_than_twelve_total_leaves() -> None:
    strategy = _strategy()
    leaves = tuple(
        ComparisonCondition(indicator="rsi", op="lt", value=float(index)) for index in range(12)
    )
    invalid = StrategyDefinition.model_construct(
        **{
            **strategy.__dict__,
            "entry": AllCondition(all=leaves),
            "exit": ComparisonCondition(indicator="rsi", op="gt", value=90.0),
        }
    )

    issues = validate_strategy(invalid).issues

    assert any(
        issue.code == "DSL_CONDITION_LEAF_LIMIT_EXCEEDED" and issue.path == "entry"
        for issue in issues
    )


@pytest.mark.parametrize(
    "conditions",
    [
        (
            ComparisonCondition(indicator="rsi", op="gt", value=50.0),
            ComparisonCondition(indicator="rsi", op="lt", value=50.0),
        ),
        (
            ComparisonCondition(indicator="rsi", op="gte", value=51.0),
            ComparisonCondition(indicator="rsi", op="lte", value=50.0),
        ),
    ],
)
def test_typed_validator_rejects_contradictory_conjunctive_leaves(
    conditions: tuple[ComparisonCondition, ComparisonCondition],
) -> None:
    strategy = _strategy()
    invalid = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "entry": AllCondition(all=conditions)}
    )

    assert "DSL_CONTRADICTORY_CONDITIONS" in _codes(invalid)


def test_disjunctive_opposites_are_not_reported_as_contradictory() -> None:
    strategy = _strategy()
    valid_entry = AnyCondition(
        any=(
            ComparisonCondition(indicator="rsi", op="gt", value=70.0),
            ComparisonCondition(indicator="rsi", op="lt", value=30.0),
        )
    )
    candidate = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": valid_entry})

    assert "DSL_CONTRADICTORY_CONDITIONS" not in _codes(candidate)


def test_valid_fixture_passes_both_safety_layers() -> None:
    payload = _payload()

    raw = scan_strategy_payload(deepcopy(payload))
    typed = validate_strategy(StrategyDefinition.model_validate(payload))

    assert raw.passed
    assert raw.issues == ()
    assert typed.passed
    assert typed.issues == ()
