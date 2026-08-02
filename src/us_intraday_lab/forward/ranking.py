"""Deterministic cross-sectional ranking of eligible paper evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from us_intraday_lab.forward.eligibility import ForwardEvidence

DEFAULT_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "net_return": 0.20,
        "max_drawdown": 0.15,
        "profit_factor": 0.15,
        "expectancy": 0.10,
        "day_consistency": 0.10,
        "week_consistency": 0.10,
        "cost_realization": 0.10,
        "symbol_concentration": 0.05,
        "historical_divergence": 0.05,
    }
)
LOWER_IS_BETTER = frozenset({"max_drawdown", "symbol_concentration", "historical_divergence"})


@dataclass(frozen=True, slots=True)
class ForwardMetrics:
    net_return: float
    max_drawdown: float
    profit_factor: float
    expectancy: float
    day_consistency: float
    week_consistency: float
    cost_realization: float
    symbol_concentration: float
    historical_divergence: float

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in DEFAULT_WEIGHTS}


@dataclass(frozen=True, slots=True)
class RankingResult:
    strategy_id: str
    evidence_id: str
    rank: int
    quality_score: float
    component_values: Mapping[str, float]
    component_scores: Mapping[str, float]
    weights: Mapping[str, float]


def calculate_metrics(evidence: ForwardEvidence) -> ForwardMetrics:
    trades = evidence.closed_trades
    returns = [trade.net_return for trade in trades]
    pnl = [trade.net_pnl for trade in trades]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for item in returns:
        cumulative += item
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    gains = sum(item for item in pnl if item > 0)
    losses = abs(sum(item for item in pnl if item < 0))
    profit_factor = gains / losses if losses else (5.0 if gains else 0.0)

    by_day: dict[object, float] = defaultdict(float)
    by_week: dict[object, float] = defaultdict(float)
    symbols: dict[str, int] = defaultdict(int)
    for trade in trades:
        by_day[trade.session_date] += trade.net_pnl
        by_week[trade.session_date.isocalendar()[:2]] += trade.net_pnl
        symbols[trade.symbol] += 1
    day_consistency = sum(value > 0 for value in by_day.values()) / len(by_day)
    week_consistency = sum(value > 0 for value in by_week.values()) / len(by_week)
    concentration = max(symbols.values()) / len(trades)
    average_cost_drag = sum(trade.fees_bps + abs(trade.slippage_bps) for trade in trades) / len(
        trades
    )
    net_return = sum(returns)
    return ForwardMetrics(
        net_return=net_return,
        max_drawdown=max_drawdown,
        profit_factor=min(profit_factor, 5.0),
        expectancy=sum(pnl) / len(pnl),
        day_consistency=day_consistency,
        week_consistency=week_consistency,
        cost_realization=-average_cost_drag,
        symbol_concentration=concentration,
        historical_divergence=abs(net_return - evidence.expected_net_return),
    )


def rank_eligible(evidence: Sequence[ForwardEvidence]) -> tuple[RankingResult, ...]:
    """Rank a pre-filtered eligible cohort; immutable strategy ID breaks all ties."""

    if not evidence:
        return ()
    if len({item.strategy_id for item in evidence}) != len(evidence):
        raise ValueError("ranking cohort must contain unique strategy IDs")
    metrics = {item.strategy_id: calculate_metrics(item) for item in evidence}
    component_scores: dict[str, dict[str, float]] = {item.strategy_id: {} for item in evidence}
    for component in DEFAULT_WEIGHTS:
        values = sorted(
            {metrics[item.strategy_id].as_dict()[component] for item in evidence},
            reverse=component not in LOWER_IS_BETTER,
        )
        score_by_value = {
            value: 1.0 if len(values) == 1 else 1.0 - index / (len(values) - 1)
            for index, value in enumerate(values)
        }
        for item in evidence:
            value = metrics[item.strategy_id].as_dict()[component]
            component_scores[item.strategy_id][component] = score_by_value[value]
    scored = []
    evidence_by_id = {item.strategy_id: item for item in evidence}
    for strategy_id, score_values in component_scores.items():
        score = sum(score_values[name] * weight for name, weight in DEFAULT_WEIGHTS.items())
        scored.append((strategy_id, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return tuple(
        RankingResult(
            strategy_id=strategy_id,
            evidence_id=evidence_by_id[strategy_id].evidence_id,
            rank=index,
            quality_score=score,
            component_values=MappingProxyType(metrics[strategy_id].as_dict()),
            component_scores=MappingProxyType(dict(sorted(component_scores[strategy_id].items()))),
            weights=DEFAULT_WEIGHTS,
        )
        for index, (strategy_id, score) in enumerate(scored, start=1)
    )
