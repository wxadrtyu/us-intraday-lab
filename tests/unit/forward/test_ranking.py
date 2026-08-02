from datetime import date, timedelta

from us_intraday_lab.forward.eligibility import BrokerConfirmedTrade, ForwardEvidence
from us_intraday_lab.forward.ranking import DEFAULT_WEIGHTS, rank_eligible


def _evidence(strategy_id: str, *, pnl: float, net_return: float) -> ForwardEvidence:
    days = tuple(date(2026, 1, 2) + timedelta(days=index) for index in range(30))
    return ForwardEvidence(
        evidence_id=f"evidence-{strategy_id}",
        strategy_id=strategy_id,
        completed_days=days,
        closed_trades=tuple(
            BrokerConfirmedTrade(
                trade_id=f"{strategy_id}-{index}",
                strategy_id=strategy_id,
                session_date=days[index % len(days)],
                symbol=("SPY", "QQQ", "IWM")[index % 3],
                net_return=net_return,
                net_pnl=pnl,
                fees_bps=0.01,
                slippage_bps=0.25,
            )
            for index in range(60)
        ),
        unresolved_reconciliations=0,
        unresolved_overnight_incidents=0,
        data_completeness=1.0,
        execution_quality=1.0,
        expected_net_return=net_return * 60,
    )


def test_ranking_stores_raw_components_normalized_scores_and_weights() -> None:
    results = rank_eligible(
        (
            _evidence("strategy-b", pnl=5.0, net_return=0.001),
            _evidence("strategy-a", pnl=10.0, net_return=0.002),
        )
    )

    assert tuple(item.strategy_id for item in results) == ("strategy-a", "strategy-b")
    assert results[0].rank == 1
    assert set(results[0].component_values) == set(DEFAULT_WEIGHTS)
    assert set(results[0].component_scores) == set(DEFAULT_WEIGHTS)
    assert dict(results[0].weights) == dict(DEFAULT_WEIGHTS)
    assert sum(results[0].weights.values()) == 1.0


def test_complete_quality_tie_is_resolved_by_immutable_strategy_id() -> None:
    results = rank_eligible(
        (
            _evidence("strategy-z", pnl=10.0, net_return=0.001),
            _evidence("strategy-a", pnl=10.0, net_return=0.001),
        )
    )

    assert tuple(item.strategy_id for item in results) == ("strategy-a", "strategy-z")
    assert results[0].quality_score == results[1].quality_score
    assert dict(results[0].component_scores) == dict(results[1].component_scores)
