from __future__ import annotations

import hashlib
import itertools
import json
import random
from typing import Any

from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal
from us_intraday_lab.strategy.validator import validate_strategy

_DEFAULTS: dict[str, float] = {
    "return_1_min": 0.0005,
    "return_1_max": -0.0005,
    "return_3_min": 0.001,
    "ema_spread_min": 0.0,
    "rsi_min": 55.0,
    "rsi_max": 40.0,
    "volume_ratio_min": 1.1,
    "vwap_distance_bps_min": 0.0,
    "vwap_distance_bps_max": -10.0,
    "range_position_min": 0.6,
    "range_position_max": 0.4,
    "atr_bps_min": 5.0,
    "atr_bps_max": 80.0,
    "minutes_from_open_min": 30.0,
    "minutes_from_open_max": 240.0,
    "stop_loss_bps": 50.0,
    "take_profit_bps": 100.0,
    "max_holding_minutes": 60.0,
    "cooldown_minutes": 30.0,
    "max_entries_per_session": 2.0,
}


def _comparison(indicator: str, op: str, value: float) -> dict[str, object]:
    return {"indicator": indicator, "op": op, "value": value}


def _rules(template: str, parameters: dict[str, float]) -> tuple[dict[str, Any], dict[str, Any]]:
    p = {**_DEFAULTS, **parameters}
    minutes = _comparison("minutes_from_open", "gte", p["minutes_from_open_min"])
    if template == "trend_pullback_5m":
        trend_filter = (
            [_comparison("ema_spread", "gt", p["ema_spread_min"])]
            if "ema_spread_min" in parameters
            else []
        )
        entry = {
            "all": [
                *trend_filter,
                _comparison("return_1", "lte", p["return_1_max"]),
                _comparison("range_position", "lte", p["range_position_max"]),
                minutes,
                _comparison("minutes_from_open", "lte", p["minutes_from_open_max"]),
            ]
        }
        exit_rule = {
            "any": [
                _comparison("return_1", "gt", p["return_1_min"]),
                _comparison("rsi", "gt", p["rsi_min"]),
            ]
        }
    elif template == "opening_reclaim_5m":
        entry = {
            "all": [
                _comparison("return_3", "gt", p["return_3_min"]),
                _comparison("vwap_distance_bps", "gt", p["vwap_distance_bps_min"]),
                _comparison("volume_ratio", "gte", p["volume_ratio_min"]),
                minutes,
            ]
        }
        exit_rule = {
            "any": [
                _comparison("return_1", "lt", p["return_1_max"]),
                _comparison("minutes_from_open", "gte", p["minutes_from_open_max"]),
            ]
        }
    elif template == "vwap_reversion_5m":
        entry = {
            "all": [
                _comparison("vwap_distance_bps", "lt", p["vwap_distance_bps_max"]),
                _comparison("rsi", "lt", p["rsi_max"]),
                _comparison("ema_spread", "gt", p["ema_spread_min"]),
                minutes,
            ]
        }
        exit_rule = {
            "any": [
                _comparison("vwap_distance_bps", "gt", p["vwap_distance_bps_min"]),
                _comparison("rsi", "gt", p["rsi_min"]),
            ]
        }
    elif template == "momentum_5m":
        entry = {
            "all": [
                _comparison("return_1", "gt", p["return_1_min"]),
                _comparison("return_3", "gt", p["return_3_min"]),
                _comparison("volume_ratio", "gte", p["volume_ratio_min"]),
                _comparison("atr_bps", "lte", p["atr_bps_max"]),
            ]
        }
        exit_rule = {"any": [_comparison("return_1", "lt", p["return_1_max"])]}
    else:
        raise ValueError("unsupported long-horizon template")
    return entry, exit_rule


def _strategy(
    proposal: LongHorizonHypothesisProposal,
    parameters: dict[str, float],
) -> StrategyDefinition:
    entry, exit_rule = _rules(proposal.entry_template, parameters)
    canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    suffix = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    strategy = StrategyDefinition.model_validate(
        {
            "strategy_id": f"{proposal.proposal_id}-{suffix}",
            "dsl_version": "1.0.0",
            "symbols": list(proposal.symbols),
            "signal_bar_size": "5min",
            "entry": entry,
            "exit": exit_rule,
            "risk": {
                "stop_loss_bps": round(parameters.get("stop_loss_bps", 50.0)),
                "take_profit_bps": round(parameters.get("take_profit_bps", 100.0)),
                "max_holding_minutes": round(
                    parameters.get("max_holding_minutes", 60.0)
                ),
                "cooldown_minutes": round(parameters.get("cooldown_minutes", 30.0)),
                "max_entries_per_session": round(
                    parameters.get("max_entries_per_session", 2.0)
                ),
                "sizing_preset": (
                    "equal_cash_conservative"
                    if proposal.entry_template == "trend_pullback_5m"
                    else "equal_risk_conservative"
                ),
            },
            "order_type": "market",
        }
    )
    validation = validate_strategy(strategy)
    if not validation.passed:
        reasons = ",".join(issue.code for issue in validation.issues)
        raise ValueError(f"generated long-horizon variant failed the closed DSL: {reasons}")
    return strategy


def generate_long_horizon_variants(
    proposal: LongHorizonHypothesisProposal,
) -> tuple[StrategyDefinition, ...]:
    """Expand one finite grid into a seeded, bounded tuple of valid JSON DSL variants."""

    if type(proposal) is not LongHorizonHypothesisProposal:
        raise TypeError("proposal must be exact LongHorizonHypothesisProposal")
    names = tuple(sorted(proposal.parameter_ranges))
    combinations = [
        dict(zip(names, values, strict=True))
        for values in itertools.product(
            *(proposal.parameter_ranges[name].values for name in names)
        )
    ]
    if len(combinations) > proposal.max_variants:
        indexes = list(range(len(combinations)))
        random.Random(proposal.seed).shuffle(indexes)
        combinations = [combinations[index] for index in sorted(indexes[: proposal.max_variants])]
    return tuple(_strategy(proposal, parameters) for parameters in combinations)
