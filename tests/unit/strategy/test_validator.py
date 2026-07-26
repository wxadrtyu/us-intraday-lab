import json
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

import pytest

import us_intraday_lab.strategy.validator as validator_module
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


class Explosive:
    def __init__(self, calls: list[str]) -> None:
        object.__setattr__(self, "_calls", calls)

    def _explode(self, method: str) -> NoReturn:
        object.__getattribute__(self, "_calls").append(method)
        raise AssertionError(f"attacker-controlled {method} executed")

    def __getattribute__(self, name: str) -> object:
        if name == "_explode":
            return object.__getattribute__(self, name)
        object.__getattribute__(self, "_explode")("__getattribute__")

    def __iter__(self) -> Any:
        self._explode("__iter__")

    def __len__(self) -> int:
        self._explode("__len__")
        return 0

    def __hash__(self) -> int:
        self._explode("__hash__")
        return 0

    def __eq__(self, other: object) -> bool:
        self._explode("__eq__")

    def __lt__(self, other: object) -> bool:
        self._explode("__lt__")

    def __le__(self, other: object) -> bool:
        self._explode("__le__")

    def __bool__(self) -> bool:
        self._explode("__bool__")
        return False

    def __str__(self) -> str:
        self._explode("__str__")
        return ""

    def __repr__(self) -> str:
        self._explode("__repr__")

    def __int__(self) -> int:
        self._explode("__int__")

    def __float__(self) -> float:
        self._explode("__float__")


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


@pytest.mark.parametrize(
    ("variant", "expected_path", "expected_code"),
    [
        ("limitPrice", "limit_price", "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("LiMiTPrice", "limit_price", "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("priceOffset", "price_offset", "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("PRICE-OFFSET", "price_offset", "DSL_UNSUPPORTED_LIMIT_OFFSET"),
        ("pythonCode", "python_code", "DSL_FORBIDDEN_FIELD"),
        ("PYTHON CODE", "python_code", "DSL_FORBIDDEN_FIELD"),
        ("importModule", "import_module", "DSL_FORBIDDEN_FIELD"),
    ],
)
def test_raw_scan_canonicalizes_compound_field_variants(
    variant: str, expected_path: str, expected_code: str
) -> None:
    payload = _payload()
    payload[variant] = "untrusted"

    issues = scan_strategy_payload(payload).issues

    assert any(issue.code == expected_code and issue.path == expected_path for issue in issues)


@pytest.mark.parametrize("variant", ["targetPosition", "TARGET_POSITION", "target-position"])
def test_raw_scan_canonicalizes_exit_exposure_fields(variant: str) -> None:
    payload = _payload()
    payload["exit"] = {variant: 1}

    assert scan_strategy_payload(payload).issues == (
        ValidationIssue(
            code="DSL_EXIT_CAN_INCREASE_EXPOSURE",
            path="exit.target_position",
            message="exit field 'target_position' can increase exposure",
        ),
    )


def test_raw_scan_orders_canonical_paths_deterministically() -> None:
    payload = _payload()
    payload["pythonCode"] = "pass"
    payload["Import-Module"] = "os"
    payload["exit"] = {"targetPosition": 1, "Buy": True}

    issues = scan_strategy_payload(payload).issues

    assert [issue.path for issue in issues] == [
        "exit.buy",
        "exit.target_position",
        "import_module",
        "python_code",
    ]


@pytest.mark.parametrize("value", [(), {"SPY"}, frozenset({"SPY"})])
def test_raw_scan_rejects_non_json_containers(value: object) -> None:
    result = scan_strategy_payload(value)

    assert result.issues == (
        ValidationIssue(
            code="DSL_UNSAFE_PAYLOAD_TYPE",
            path="",
            message="strategy payload contains a non-JSON value",
        ),
    )


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


def _wide_any_tree(group_count: int, extra_leaves: int = 0) -> AllCondition:
    groups = tuple(
        AnyCondition(
            any=(
                ComparisonCondition(indicator="rsi", op="gt", value=float(index)),
                ComparisonCondition(indicator="rsi", op="lt", value=float(index + 1)),
            )
        )
        for index in range(group_count)
    )
    extras = tuple(
        ComparisonCondition(indicator="volume_ratio", op="gt", value=float(index))
        for index in range(extra_leaves)
    )
    return AllCondition(all=groups + extras)


def test_leaf_limit_aborts_contradiction_analysis_before_dnf_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = _strategy()
    invalid = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "entry": _wide_any_tree(21)}
    )

    def fail_if_called(*args: object) -> None:
        raise AssertionError("contradiction analysis ran after leaf limit failure")

    monkeypatch.setattr(validator_module, "_check_contradictions", fail_if_called)

    issues = validate_strategy(invalid).issues

    assert "DSL_CONDITION_LEAF_LIMIT_EXCEEDED" in {issue.code for issue in issues}


def test_contradiction_branch_budget_has_deterministic_boundary() -> None:
    strategy = _strategy()
    at_budget = StrategyDefinition.model_construct(
        **{
            **strategy.__dict__,
            "entry": _wide_any_tree(4),
            "exit": ComparisonCondition(indicator="rsi", op="gte", value=0.0),
        }
    )
    over_budget = StrategyDefinition.model_construct(
        **{
            **strategy.__dict__,
            "entry": _wide_any_tree(5),
            "exit": ComparisonCondition(indicator="rsi", op="gte", value=0.0),
        }
    )

    assert "DSL_CONTRADICTION_BUDGET_EXCEEDED" not in _codes(at_budget)
    assert "DSL_CONTRADICTION_BUDGET_EXCEEDED" in _codes(over_budget)


def test_contradiction_work_budget_is_enforced_before_expansion() -> None:
    strategy = _strategy()
    over_budget = StrategyDefinition.model_construct(
        **{
            **strategy.__dict__,
            "entry": _wide_any_tree(4, extra_leaves=3),
            "exit": ComparisonCondition(indicator="rsi", op="gte", value=0.0),
        }
    )

    issues = validate_strategy(over_budget).issues

    assert any(
        issue.code == "DSL_CONTRADICTION_BUDGET_EXCEEDED" and issue.path == "entry"
        for issue in issues
    )


def test_exact_model_construct_missing_fields_returns_issues_without_raising() -> None:
    invalid = StrategyDefinition.model_construct(strategy_id="partial")

    issues = validate_strategy(invalid).issues

    assert [issue.path for issue in issues] == [
        "dsl_version",
        "entry",
        "exit",
        "order_type",
        "risk",
        "signal_bar_size",
        "symbols",
    ]
    assert {issue.code for issue in issues} == {"DSL_MISSING_FIELD"}


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("strategy_id", 7, "DSL_INVALID_STRATEGY_ID"),
        ("dsl_version", "2.0.0", "DSL_UNSUPPORTED_DSL_VERSION"),
        ("symbols", ["SPY"], "DSL_INVALID_SYMBOLS_CONTAINER"),
        ("signal_bar_size", 15, "DSL_UNSUPPORTED_SIGNAL_BAR"),
        ("risk", {"stop_loss_bps": 1}, "DSL_INVALID_RISK"),
        ("order_type", "short", "DSL_UNSUPPORTED_ORDER_TYPE"),
    ],
)
def test_exact_model_construct_reestablishes_top_level_contract_invariants(
    field: str, value: object, expected_code: str
) -> None:
    strategy = _strategy()
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, field: value})

    assert expected_code in _codes(invalid)


def test_exact_model_construct_rejects_malicious_symbols_without_dunder_calls() -> None:
    strategy = _strategy()
    calls: list[str] = []
    invalid_container = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "symbols": Explosive(calls)}
    )
    invalid_element = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "symbols": ("SPY", Explosive(calls))}
    )

    container_issues = validate_strategy(invalid_container).issues
    element_issues = validate_strategy(invalid_element).issues

    assert "DSL_INVALID_SYMBOLS_CONTAINER" in {issue.code for issue in container_issues}
    assert "DSL_INVALID_SYMBOL_TYPE" in {issue.code for issue in element_issues}
    assert calls == []


def test_exact_model_construct_rejects_malicious_risk_without_dunder_calls() -> None:
    strategy = _strategy()
    calls: list[str] = []
    forged_risk = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "risk": Explosive(calls)}
    )
    risk = RiskDefinition.model_construct(
        **{**strategy.risk.__dict__, "stop_loss_bps": Explosive(calls)}
    )
    forged_field = StrategyDefinition.model_construct(**{**strategy.__dict__, "risk": risk})

    risk_issues = validate_strategy(forged_risk).issues
    field_issues = validate_strategy(forged_field).issues

    assert "DSL_INVALID_RISK" in {issue.code for issue in risk_issues}
    assert any(
        issue.code == "DSL_INVALID_RISK_FIELD" and issue.path == "risk.stop_loss_bps"
        for issue in field_issues
    )
    assert calls == []


def test_exact_model_construct_rejects_forged_condition_container_without_dunders() -> None:
    strategy = _strategy()
    calls: list[str] = []
    entry = AllCondition.model_construct(all=Explosive(calls))
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": entry})

    issues = validate_strategy(invalid).issues

    assert any(
        issue.code == "DSL_INVALID_CONDITION_CONTAINER" and issue.path == "entry.all"
        for issue in issues
    )
    assert calls == []


def test_exact_model_construct_rejects_forged_leaf_values_without_dunders() -> None:
    strategy = _strategy()
    calls: list[str] = []
    entry = ComparisonCondition.model_construct(
        indicator=Explosive(calls),
        op=Explosive(calls),
        value=Explosive(calls),
    )
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": entry})

    issues = validate_strategy(invalid).issues

    assert [(issue.code, issue.path) for issue in issues if issue.path.startswith("entry")] == [
        ("DSL_UNKNOWN_INDICATOR", "entry.indicator"),
        ("DSL_UNKNOWN_COMPARISON", "entry.op"),
        ("DSL_NON_FINITE_THRESHOLD", "entry.value"),
    ]
    assert calls == []


def test_exact_models_reject_unexpected_internal_fields_deterministically() -> None:
    strategy = _strategy()
    risk = RiskDefinition.model_construct(**strategy.risk.__dict__)
    risk.__dict__["url"] = "https://example.invalid"
    entry = ComparisonCondition(indicator="rsi", op="lt", value=40.0)
    entry.__dict__["python"] = "pass"
    invalid = StrategyDefinition.model_construct(
        **{**strategy.__dict__, "entry": entry, "risk": risk}
    )
    invalid.__dict__["sql"] = "select 1"

    issues = validate_strategy(invalid).issues

    assert [
        (issue.code, issue.path) for issue in issues if issue.code == "DSL_UNEXPECTED_FIELD"
    ] == [
        ("DSL_UNEXPECTED_FIELD", "entry.python"),
        ("DSL_UNEXPECTED_FIELD", "risk.url"),
        ("DSL_UNEXPECTED_FIELD", "sql"),
    ]
