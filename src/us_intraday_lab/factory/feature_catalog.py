from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, cast

from us_intraday_lab.contracts.hypotheses import ParameterName, ParameterRange

ParameterOwner = Literal["entry", "exit", "risk", "sizing"]
ParameterType = Literal["float", "int", "enum"]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: ParameterName
    value_type: ParameterType
    affects: ParameterOwner
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


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    template_id: str
    parameters: Mapping[ParameterName, ParameterSpec]


@dataclass(frozen=True, slots=True)
class FeatureTemplateCatalog:
    version: str
    indicators: tuple[str, ...]
    entry_templates: Mapping[str, TemplateSpec]
    exit_templates: Mapping[str, TemplateSpec]


_PARAMETERS: Mapping[ParameterName, ParameterSpec] = MappingProxyType(
    {
        "cooldown_minutes": ParameterSpec("cooldown_minutes", "int", "risk", 1, 1_440),
        "ema_spread_min": ParameterSpec("ema_spread_min", "float", "entry", -1.0, 1.0),
        "max_entries_per_session": ParameterSpec("max_entries_per_session", "int", "risk", 1, 3),
        "max_holding_minutes": ParameterSpec("max_holding_minutes", "int", "risk", 1, 1_440),
        "order_type": ParameterSpec(
            "order_type", "enum", "entry", allowed_values=("market", "limit")
        ),
        "rsi_entry": ParameterSpec("rsi_entry", "float", "entry", 0.0, 100.0),
        "sizing_preset": ParameterSpec(
            "sizing_preset",
            "enum",
            "sizing",
            allowed_values=("equal_cash_conservative", "equal_risk_conservative"),
        ),
        "stop_loss_bps": ParameterSpec("stop_loss_bps", "int", "risk", 1, 10_000),
        "take_profit_bps": ParameterSpec("take_profit_bps", "int", "risk", 1, 10_000),
        "volume_ratio_min": ParameterSpec("volume_ratio_min", "float", "entry", 0.0, 100.0),
    }
)

FEATURE_TEMPLATE_CATALOG = FeatureTemplateCatalog(
    version="feature-template-catalog-1.0.0",
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
                parameters=_PARAMETERS,
            )
        }
    ),
    exit_templates=MappingProxyType(
        {
            "risk_managed": TemplateSpec(
                template_id="risk_managed",
                parameters=_PARAMETERS,
            )
        }
    ),
)


def validate_parameter_ranges(
    *,
    entry_template: str,
    exit_template: str,
    parameter_ranges: Mapping[ParameterName, ParameterRange],
) -> None:
    entry = FEATURE_TEMPLATE_CATALOG.entry_templates.get(entry_template)
    exit_spec = FEATURE_TEMPLATE_CATALOG.exit_templates.get(exit_template)
    if entry is None or exit_spec is None:
        raise ValueError("proposal references an unknown template")
    allowed = {**entry.parameters, **exit_spec.parameters}
    for name, parameter_range in parameter_ranges.items():
        spec = allowed.get(name)
        if spec is None:
            raise ValueError(f"proposal references unknown parameter: {name}")
        spec.validate(parameter_range)
