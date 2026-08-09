from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

IndicatorName = Literal[
    "return_1",
    "return_3",
    "return_from_open",
    "prior_session_return",
    "peer_return_from_open",
    "peer_prior_session_return",
    "ema_spread",
    "rsi",
    "atr_bps",
    "volume_ratio",
    "vwap_distance_bps",
    "range_position",
    "minutes_from_open",
]
ComparisonOp = Literal["gt", "gte", "lt", "lte"]
SignalBarSize = Literal["5min", "15min"]
OrderType = Literal["market", "limit"]
SizingPreset = Literal[
    "equal_cash_conservative",
    "equal_risk_conservative",
]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ComparisonCondition(_ClosedModel):
    indicator: IndicatorName
    op: ComparisonOp
    value: float


class AllCondition(_ClosedModel):
    all: tuple["Condition", ...]


class AnyCondition(_ClosedModel):
    any: tuple["Condition", ...]


def _condition_discriminator(value: object) -> str | None:
    if isinstance(value, dict):
        if "indicator" in value:
            return "comparison"
        if "all" in value:
            return "all"
        if "any" in value:
            return "any"
        return None
    if isinstance(value, ComparisonCondition):
        return "comparison"
    if isinstance(value, AllCondition):
        return "all"
    if isinstance(value, AnyCondition):
        return "any"
    return None


type Condition = Annotated[
    Annotated[ComparisonCondition, Tag("comparison")]
    | Annotated[AllCondition, Tag("all")]
    | Annotated[AnyCondition, Tag("any")],
    Discriminator(_condition_discriminator),
]

AllCondition.model_rebuild()
AnyCondition.model_rebuild()


class RiskDefinition(_ClosedModel):
    stop_loss_bps: int
    take_profit_bps: int
    max_holding_minutes: int
    cooldown_minutes: int
    max_entries_per_session: int
    sizing_preset: SizingPreset


class StrategyDefinition(_ClosedModel):
    strategy_id: str = Field(min_length=1)
    dsl_version: Literal["1.0.0"]
    symbols: tuple[str, ...]
    signal_bar_size: SignalBarSize
    entry: Condition
    exit: Condition
    risk: RiskDefinition
    order_type: OrderType
