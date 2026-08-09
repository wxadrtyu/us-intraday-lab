from __future__ import annotations

import math
from functools import reduce
from operator import mul
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EntryTemplate = Literal[
    "trend_pullback_5m",
    "opening_reclaim_5m",
    "vwap_reversion_5m",
    "momentum_5m",
    "cross_rebound_5m",
    "cross_regime_reversal_5m",
    "cross_momentum_5m",
    "relative_laggard_5m",
    "asymmetric_pair_ensemble_5m",
]

APPROVED_PARAMETERS = frozenset(
    {
        "return_1_min",
        "return_1_max",
        "return_3_min",
        "ema_spread_min",
        "rsi_min",
        "rsi_max",
        "volume_ratio_min",
        "vwap_distance_bps_min",
        "vwap_distance_bps_max",
        "range_position_min",
        "range_position_max",
        "atr_bps_min",
        "atr_bps_max",
        "minutes_from_open_min",
        "minutes_from_open_max",
        "stop_loss_bps",
        "take_profit_bps",
        "max_holding_minutes",
        "cooldown_minutes",
        "max_entries_per_session",
        "return_from_open_max",
        "peer_return_from_open_max",
        "prior_session_return_max",
        "peer_prior_session_return_max",
        "cross_return_from_open_max",
        "cross_prior_session_return_max",
        "cross_prior_session_return_min",
        "cross_return_from_open_min",
        "cross_trailing_session_return_5_min",
        "relative_return_from_open_max",
        "return_from_open_min",
        "trailing_session_return_3_max",
        "tqqq_entry_minutes",
        "soxl_entry_minutes",
        "tqqq_exit_minutes",
        "soxl_exit_minutes",
    }
)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ParameterRange(_ClosedModel):
    values: tuple[float, ...] = Field(min_length=1, max_length=50)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("parameter values must be finite")
        if len(set(values)) != len(values):
            raise ValueError("parameter values must be distinct")
        return values


class LongHorizonHypothesisProposal(_ClosedModel):
    schema_version: Literal["1.0.0"]
    proposal_id: str = Field(min_length=1, max_length=128)
    entry_template: EntryTemplate
    symbols: tuple[
        Literal["AAPL", "QQQ", "SPY", "IWM", "TQQQ", "UPRO", "SOXL"], ...
    ]
    parameter_ranges: dict[str, ParameterRange] = Field(min_length=1, max_length=12)
    max_variants: int = Field(ge=4, le=50)
    seed: int = Field(ge=0, le=2**64 - 1)
    rationale: str = Field(min_length=12, max_length=2_000)
    provenance: Literal["ai", "fixture"]

    @model_validator(mode="after")
    def validate_closed_search_space(self) -> Self:
        if self.symbols not in (
            ("AAPL", "QQQ"),
            ("SPY", "IWM"),
            ("SPY", "TQQQ"),
            ("TQQQ", "UPRO"),
            ("TQQQ", "SOXL"),
        ):
            raise ValueError("symbols must use an approved exact ordered pair")
        unknown = sorted(set(self.parameter_ranges).difference(APPROVED_PARAMETERS))
        if unknown:
            raise ValueError("unknown long-horizon parameters: " + ",".join(unknown))
        combinations = reduce(
            mul,
            (len(parameter.values) for parameter in self.parameter_ranges.values()),
            1,
        )
        if combinations < 4:
            raise ValueError("search space must provide a baseline and three robustness neighbors")
        return self
