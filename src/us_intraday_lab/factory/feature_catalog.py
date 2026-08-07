from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal, cast

from us_intraday_lab.contracts.hypotheses import (
    ParameterName,
    ParameterRange,
    ParameterValue,
)

ParameterOwner = Literal["entry", "exit", "risk", "sizing"]
ParameterType = Literal["float", "int", "enum"]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: ParameterName
    value_type: ParameterType
    affects: ParameterOwner
    baseline: int | float | str
    minimum: float | int | None = None
    maximum: float | int | None = None
    allowed_values: tuple[str, ...] = ()

    def validate(self, parameter_range: ParameterRange) -> None:
        for value in parameter_range.values:
            if self.value_type == "float":
                if type(value) not in {int, float}:
                    raise ValueError(f"{self.name} requires numeric values")
            elif self.value_type == "int":
                if type(value) is not int:
                    raise ValueError(f"{self.name} requires integer values")
            elif type(value) is not str or value not in self.allowed_values:
                raise ValueError(f"{self.name} contains a non-allowlisted enum value")
            if type(value) in {int, float}:
                numeric_value = cast(int | float, value)
                if self.minimum is not None and numeric_value < self.minimum:
                    raise ValueError(f"{self.name} is below its catalog minimum")
                if self.maximum is not None and numeric_value > self.maximum:
                    raise ValueError(f"{self.name} exceeds its catalog maximum")
        if self.baseline not in parameter_range.values:
            raise ValueError(f"{self.name} values must include the catalog baseline")


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    template_id: str
    required_indicators: tuple[str, ...]
    parameters: Mapping[ParameterName, ParameterSpec]


@dataclass(frozen=True, slots=True)
class FeatureTemplateCatalog:
    version: str
    indicators: tuple[str, ...]
    entry_templates: Mapping[str, TemplateSpec]
    exit_templates: Mapping[str, TemplateSpec]


_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        "cooldown_minutes": ParameterSpec("cooldown_minutes", "int", "risk", 30, 1, 1_440),
        "ema_spread_min": ParameterSpec("ema_spread_min", "float", "entry", 0.0, -1.0, 1.0),
        "minutes_from_open_min": ParameterSpec(
            "minutes_from_open_min", "int", "entry", 120, 0, 390
        ),
        "range_position_max": ParameterSpec(
            "range_position_max", "float", "entry", 0.3, 0.0, 1.0
        ),
        "return_1_max": ParameterSpec("return_1_max", "float", "entry", -0.001, -1.0, 1.0),
        "max_entries_per_session": ParameterSpec("max_entries_per_session", "int", "risk", 3, 1, 3),
        "max_holding_minutes": ParameterSpec("max_holding_minutes", "int", "risk", 90, 1, 1_440),
        "order_type": ParameterSpec(
            "order_type", "enum", "entry", "limit", allowed_values=("market", "limit")
        ),
        "rsi_entry": ParameterSpec("rsi_entry", "float", "entry", 40.0, 0.0, 100.0),
        "sizing_preset": ParameterSpec(
            "sizing_preset",
            "enum",
            "sizing",
            "equal_cash_conservative",
            allowed_values=("equal_cash_conservative", "equal_risk_conservative"),
        ),
        "stop_loss_bps": ParameterSpec("stop_loss_bps", "int", "risk", 35, 1, 10_000),
        "take_profit_bps": ParameterSpec("take_profit_bps", "int", "risk", 70, 1, 10_000),
        "volume_ratio_min": ParameterSpec("volume_ratio_min", "float", "entry", 1.2, 0.0, 100.0),
        "vwap_distance_max": ParameterSpec(
            "vwap_distance_max", "float", "entry", -10.0, -10_000.0, 10_000.0
        ),
    }
)

_TREND_DIP_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        **_PARAMETERS,
        "cooldown_minutes": replace(_PARAMETERS["cooldown_minutes"], baseline=15),
        "ema_spread_min": replace(_PARAMETERS["ema_spread_min"], baseline=0.00025),
        "max_holding_minutes": replace(_PARAMETERS["max_holding_minutes"], baseline=120),
        "minutes_from_open_min": replace(_PARAMETERS["minutes_from_open_min"], baseline=90),
        "range_position_max": replace(_PARAMETERS["range_position_max"], baseline=0.4),
        "return_1_max": replace(_PARAMETERS["return_1_max"], baseline=-0.0005),
        "stop_loss_bps": replace(_PARAMETERS["stop_loss_bps"], baseline=100),
        "take_profit_bps": replace(_PARAMETERS["take_profit_bps"], baseline=200),
    }
)

_OVERSOLD_REBOUND_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        **_TREND_DIP_PARAMETERS,
        "max_holding_minutes": replace(_PARAMETERS["max_holding_minutes"], baseline=60),
        "rsi_entry": replace(_PARAMETERS["rsi_entry"], baseline=35.0),
        "vwap_distance_max": replace(_PARAMETERS["vwap_distance_max"], baseline=-10.0),
    }
)

_LATE_DIP_REBOUND_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        **_TREND_DIP_PARAMETERS,
        "cooldown_minutes": replace(_PARAMETERS["cooldown_minutes"], baseline=30),
        "max_holding_minutes": replace(_PARAMETERS["max_holding_minutes"], baseline=75),
        "minutes_from_open_min": replace(_PARAMETERS["minutes_from_open_min"], baseline=180),
        "range_position_max": replace(_PARAMETERS["range_position_max"], baseline=0.55),
        "return_1_max": replace(_PARAMETERS["return_1_max"], baseline=-0.0009),
        "stop_loss_bps": replace(_PARAMETERS["stop_loss_bps"], baseline=10_000),
        "take_profit_bps": replace(_PARAMETERS["take_profit_bps"], baseline=10_000),
        "vwap_distance_max": replace(_PARAMETERS["vwap_distance_max"], baseline=10.0),
    }
)

_CAUSAL_DIP_ENSEMBLE_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        **_PARAMETERS,
        "bridge_return_1_max": ParameterSpec(
            "bridge_return_1_max", "float", "entry", -0.00185, -1.0, 1.0
        ),
        "cooldown_minutes": replace(_PARAMETERS["cooldown_minutes"], baseline=15),
        "max_holding_minutes": replace(_PARAMETERS["max_holding_minutes"], baseline=116),
        "order_type": replace(_PARAMETERS["order_type"], baseline="market"),
        "stop_loss_bps": replace(_PARAMETERS["stop_loss_bps"], baseline=10_000),
        "take_profit_bps": replace(_PARAMETERS["take_profit_bps"], baseline=10_000),
    }
)

FEATURE_TEMPLATE_CATALOG = FeatureTemplateCatalog(
    version="feature-template-catalog-1.7.0",
    indicators=(
        "return_1",
        "return_3",
        "ema_spread",
        "rsi",
        "atr_bps",
        "volume_ratio",
        "vwap_distance_bps",
        "range_position",
        "minutes_from_open",
    ),
    entry_templates=MappingProxyType(
        {
            "momentum_pullback": TemplateSpec(
                template_id="momentum_pullback",
                required_indicators=("ema_spread", "rsi", "volume_ratio"),
                parameters=_PARAMETERS,
            ),
            "trend_breakout": TemplateSpec(
                template_id="trend_breakout",
                required_indicators=("ema_spread", "rsi", "volume_ratio"),
                parameters=_PARAMETERS,
            ),
            "trend_dip": TemplateSpec(
                template_id="trend_dip",
                required_indicators=(
                    "ema_spread",
                    "return_1",
                    "range_position",
                    "minutes_from_open",
                ),
                parameters=_TREND_DIP_PARAMETERS,
            ),
            "oversold_rebound": TemplateSpec(
                template_id="oversold_rebound",
                required_indicators=("rsi", "vwap_distance_bps", "return_1"),
                parameters=_OVERSOLD_REBOUND_PARAMETERS,
            ),
            "late_dip_rebound": TemplateSpec(
                template_id="late_dip_rebound",
                required_indicators=(
                    "vwap_distance_bps",
                    "return_1",
                    "range_position",
                    "minutes_from_open",
                ),
                parameters=_LATE_DIP_REBOUND_PARAMETERS,
            ),
            "causal_dip_ensemble": TemplateSpec(
                template_id="causal_dip_ensemble",
                required_indicators=(
                    "vwap_distance_bps",
                    "return_1",
                    "range_position",
                    "minutes_from_open",
                    "ema_spread",
                    "return_3",
                ),
                parameters=_CAUSAL_DIP_ENSEMBLE_PARAMETERS,
            ),
        }
    ),
    exit_templates=MappingProxyType(
        {
            "risk_managed": TemplateSpec(
                template_id="risk_managed",
                required_indicators=("rsi",),
                parameters=_PARAMETERS,
            ),
            "trend_failure": TemplateSpec(
                template_id="trend_failure",
                required_indicators=("ema_spread",),
                parameters=_PARAMETERS,
            ),
            "time_stop": TemplateSpec(
                template_id="time_stop",
                required_indicators=("minutes_from_open",),
                parameters=MappingProxyType({}),
            ),
        }
    ),
)


def validate_parameter_ranges(
    *,
    entry_template: str,
    exit_template: str,
    indicators: tuple[str, ...],
    parameter_ranges: Mapping[ParameterName, ParameterRange],
) -> None:
    entry = FEATURE_TEMPLATE_CATALOG.entry_templates.get(entry_template)
    exit_spec = FEATURE_TEMPLATE_CATALOG.exit_templates.get(exit_template)
    if entry is None or exit_spec is None:
        raise ValueError("proposal references an unknown template")
    required_indicators = tuple(
        dict.fromkeys((*entry.required_indicators, *exit_spec.required_indicators))
    )
    if indicators != required_indicators:
        raise ValueError("proposal indicators must exactly match the selected templates")
    allowed = {**entry.parameters, **exit_spec.parameters}
    for name, parameter_range in parameter_ranges.items():
        spec = allowed.get(name)
        if spec is None:
            raise ValueError(f"proposal references unknown parameter: {name}")
        spec.validate(parameter_range)


def _value_key(value: ParameterValue) -> tuple[int, float | str]:
    if type(value) in {int, float}:
        return (0, float(value))
    return (1, cast(str, value))


def required_variant_budget(
    *,
    entry_template: str,
    parameter_ranges: Mapping[ParameterName, ParameterRange],
) -> int:
    """Return slots needed for distinct baseline, all-low, and all-high variants."""
    template = FEATURE_TEMPLATE_CATALOG.entry_templates[entry_template]
    names = tuple(parameter_ranges)
    baseline = tuple(template.parameters[name].baseline for name in names)
    lower = tuple(min(parameter_ranges[name].values, key=_value_key) for name in names)
    upper = tuple(max(parameter_ranges[name].values, key=_value_key) for name in names)
    return len(dict.fromkeys((baseline, lower, upper)))
