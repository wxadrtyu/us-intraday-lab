"""Hard gates that must pass before forward performance can be ranked."""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from us_intraday_lab.contracts.registry import RegistryState

MIN_COMPLETED_DAYS = 30
MIN_CLOSED_TRADES = 50
MIN_DATA_COMPLETENESS = 0.99
MIN_EXECUTION_QUALITY = 0.95


class BrokerConfirmedTrade(BaseModel):
    """A closed trade reconstructed exclusively from broker-confirmed fills."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    trade_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    session_date: date
    symbol: Literal["SPY", "QQQ", "IWM"]
    net_return: float
    net_pnl: float
    fees_bps: float = Field(ge=0)
    slippage_bps: float
    source: Literal["broker_confirmed_fill"] = "broker_confirmed_fill"


class ForwardEvidence(BaseModel):
    """Immutable summary inputs retained for one forward evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    evidence_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    completed_days: tuple[date, ...]
    closed_trades: tuple[BrokerConfirmedTrade, ...]
    unresolved_reconciliations: int = Field(ge=0)
    unresolved_overnight_incidents: int = Field(ge=0)
    data_completeness: float = Field(ge=0, le=1)
    execution_quality: float = Field(ge=0, le=1)
    expected_net_return: float = 0.0

    @model_validator(mode="after")
    def validate_evidence_identity(self) -> Self:
        if len(self.completed_days) != len(set(self.completed_days)):
            raise ValueError("completed_days must be distinct")
        trade_ids = tuple(trade.trade_id for trade in self.closed_trades)
        if len(trade_ids) != len(set(trade_ids)):
            raise ValueError("closed trades must have distinct broker trade IDs")
        if any(trade.strategy_id != self.strategy_id for trade in self.closed_trades):
            raise ValueError("closed trades must belong to evidence strategy")
        if any(trade.session_date not in self.completed_days for trade in self.closed_trades):
            raise ValueError("closed trade session must be a completed day")
        return self


class EligibilityGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason_code: str
    passed: bool
    observed: float | int | str | bool
    threshold: float | int | str | bool


class EligibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    evidence_id: str
    eligible: bool
    gates: tuple[EligibilityGate, ...]


def evaluate_eligibility(
    evidence: ForwardEvidence,
    *,
    lifecycle_state: RegistryState,
    capacity_available: bool,
) -> EligibilityDecision:
    """Evaluate every hard gate without allowing performance to offset a failure."""

    gates = (
        EligibilityGate(
            reason_code="MIN_COMPLETED_PAPER_DAYS",
            passed=len(evidence.completed_days) >= MIN_COMPLETED_DAYS,
            observed=len(evidence.completed_days),
            threshold=MIN_COMPLETED_DAYS,
        ),
        EligibilityGate(
            reason_code="MIN_BROKER_CONFIRMED_CLOSED_TRADES",
            passed=len(evidence.closed_trades) >= MIN_CLOSED_TRADES,
            observed=len(evidence.closed_trades),
            threshold=MIN_CLOSED_TRADES,
        ),
        EligibilityGate(
            reason_code="NO_UNRESOLVED_RECONCILIATION",
            passed=evidence.unresolved_reconciliations == 0,
            observed=evidence.unresolved_reconciliations,
            threshold=0,
        ),
        EligibilityGate(
            reason_code="NO_UNRESOLVED_OVERNIGHT_RISK",
            passed=evidence.unresolved_overnight_incidents == 0,
            observed=evidence.unresolved_overnight_incidents,
            threshold=0,
        ),
        EligibilityGate(
            reason_code="OBSERVING_LIFECYCLE_REQUIRED",
            passed=lifecycle_state == "paper_observing",
            observed=lifecycle_state,
            threshold="paper_observing",
        ),
        EligibilityGate(
            reason_code="MIN_DATA_COMPLETENESS",
            passed=evidence.data_completeness >= MIN_DATA_COMPLETENESS,
            observed=evidence.data_completeness,
            threshold=MIN_DATA_COMPLETENESS,
        ),
        EligibilityGate(
            reason_code="MIN_EXECUTION_QUALITY",
            passed=evidence.execution_quality >= MIN_EXECUTION_QUALITY,
            observed=evidence.execution_quality,
            threshold=MIN_EXECUTION_QUALITY,
        ),
        EligibilityGate(
            reason_code="RANKED_CAPACITY_AVAILABLE",
            passed=capacity_available,
            observed=capacity_available,
            threshold=True,
        ),
    )
    return EligibilityDecision(
        strategy_id=evidence.strategy_id,
        evidence_id=evidence.evidence_id,
        eligible=all(gate.passed for gate in gates),
        gates=gates,
    )
