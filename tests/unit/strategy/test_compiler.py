import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import us_intraday_lab.strategy.compiler as compiler_module
from us_intraday_lab.contracts.strategies import ComparisonCondition, StrategyDefinition
from us_intraday_lab.strategy.compiler import (
    COMPARISONS,
    INDICATORS,
    StrategyCompileError,
    compile_strategy,
)
from us_intraday_lab.strategy.operators import (
    AllOperator,
    AnyOperator,
    ComparisonOperator,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "strategies" / "valid_momentum_pullback.json"


def test_valid_fixture_compiles_to_typed_allowlisted_operator_nodes() -> None:
    strategy = StrategyDefinition.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    compiled = compile_strategy(strategy)

    assert isinstance(compiled.entry, AllOperator)
    assert isinstance(compiled.entry.children[0], ComparisonOperator)
    assert compiled.entry.children[0].indicator == "ema_spread"
    assert compiled.entry.children[0].indicator_fn is INDICATORS["ema_spread"]
    assert isinstance(compiled.exit, AnyOperator)
    assert all(isinstance(node, ComparisonOperator) for node in compiled.exit.children)
    assert compiled.symbols == ("SPY", "QQQ", "IWM")
    assert compiled.order_type == "limit"
    canonical = json.dumps(
        strategy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    expected = f"{strategy.strategy_id}@sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    assert compiled.definition_fingerprint == expected


def test_indicator_dispatch_is_the_exact_literal_release_one_allowlist() -> None:
    assert tuple(INDICATORS) == (
        "return_1",
        "return_3",
        "return_from_open",
        "prior_session_return",
        "trailing_session_return_3",
        "trailing_session_return_5",
        "peer_return_from_open",
        "relative_return_from_open",
        "peer_prior_session_return",
        "pair_prior_session_return_min",
        "peer_trailing_session_return_5",
        "is_tqqq",
        "is_soxl",
        "ema_spread",
        "rsi",
        "atr_bps",
        "volume_ratio",
        "vwap_distance_bps",
        "range_position",
        "minutes_from_open",
    )


def test_dispatch_tables_are_publicly_inspectable_but_immutable() -> None:
    assert isinstance(INDICATORS, MappingProxyType)
    assert isinstance(COMPARISONS, MappingProxyType)

    with pytest.raises(TypeError):
        INDICATORS["rsi"] = lambda _: 0.0  # type: ignore[index]
    with pytest.raises(TypeError):
        COMPARISONS["gt"] = lambda _left, _right: False  # type: ignore[index]


def test_public_dispatch_rebinding_cannot_replace_private_compiler_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = StrategyDefinition.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr(compiler_module, "INDICATORS", {})
    monkeypatch.setattr(compiler_module, "COMPARISONS", {})

    compiled = compile_strategy(strategy)

    assert isinstance(compiled.entry, AllOperator)
    assert isinstance(compiled.entry.children[0], ComparisonOperator)
    assert compiled.entry.children[0].indicator_fn is not None


class HostilePayload:
    def __init__(self) -> None:
        object.__setattr__(self, "attribute_accessed", False)

    def __getattribute__(self, name: str) -> object:
        if name == "attribute_accessed":
            return object.__getattribute__(self, name)
        object.__setattr__(self, "attribute_accessed", True)
        raise AssertionError(f"compiler accessed hostile attribute: {name}")


class HostileIndicator:
    def __init__(self) -> None:
        self.executed = False

    def __hash__(self) -> int:
        self.executed = True
        raise AssertionError("compiler executed hostile indicator")

    def __str__(self) -> str:
        self.executed = True
        raise AssertionError("compiler rendered hostile indicator")


def test_handcrafted_object_is_rejected_without_attribute_access_or_execution() -> None:
    payload = HostilePayload()

    with pytest.raises(StrategyCompileError) as exc_info:
        compile_strategy(payload)  # type: ignore[arg-type]

    assert exc_info.value.code == "DSL_UNSAFE_COMPILE_INPUT"
    assert payload.attribute_accessed is False


def test_model_construct_cannot_smuggle_an_executable_indicator() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    strategy = StrategyDefinition.model_validate(payload)
    hostile = HostileIndicator()
    entry = ComparisonCondition.model_construct(indicator=hostile, op="gt", value=0.0)
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "entry": entry})

    with pytest.raises(StrategyCompileError):
        compile_strategy(invalid)

    assert hostile.executed is False


def test_compiler_refuses_typed_but_domain_invalid_strategy() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    strategy = StrategyDefinition.model_validate(payload)
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, "symbols": ("SPY", "DIA")})

    with pytest.raises(StrategyCompileError) as exc_info:
        compile_strategy(invalid)

    assert exc_info.value.code == "DSL_VALIDATION_FAILED"
    assert exc_info.value.issues[0].code == "DSL_UNSUPPORTED_SYMBOL"


@pytest.mark.parametrize(
    ("overrides", "expected_path"),
    [
        ({"order_type": "short"}, "order_type"),
        ({"symbols": ["SPY"]}, "symbols"),
        ({"risk": object()}, "risk"),
    ],
)
def test_compiler_never_propagates_forged_exact_models(
    overrides: dict[str, Any], expected_path: str
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    strategy = StrategyDefinition.model_validate(payload)
    invalid = StrategyDefinition.model_construct(**{**strategy.__dict__, **overrides})

    with pytest.raises(StrategyCompileError) as exc_info:
        compile_strategy(invalid)

    assert exc_info.value.code == "DSL_VALIDATION_FAILED"
    assert any(issue.path == expected_path for issue in exc_info.value.issues)
