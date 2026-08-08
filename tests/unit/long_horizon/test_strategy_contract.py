import pytest

from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.strategy.validator import validate_strategy


def _payload(symbols: list[str]) -> dict[str, object]:
    return {
        "strategy_id": "five-minute-test",
        "dsl_version": "1.0.0",
        "symbols": symbols,
        "signal_bar_size": "5min",
        "entry": {"all": [{"indicator": "minutes_from_open", "op": "gte", "value": 30}]},
        "exit": {"any": [{"indicator": "minutes_from_open", "op": "gt", "value": 1_000}]},
        "risk": {
            "stop_loss_bps": 100,
            "take_profit_bps": 200,
            "max_holding_minutes": 90,
            "cooldown_minutes": 30,
            "max_entries_per_session": 1,
            "sizing_preset": "equal_cash_conservative",
        },
        "order_type": "market",
    }


def test_five_minute_strategy_allows_only_aapl_qqq_long_scope() -> None:
    strategy = StrategyDefinition.model_validate(_payload(["AAPL", "QQQ"]))

    assert validate_strategy(strategy).passed


@pytest.mark.parametrize("symbols", [["QQQ", "AAPL"], ["AAPL"], ["AAPL", "QQQ", "SPY"]])
def test_five_minute_scope_rejects_other_symbol_sets(symbols: list[str]) -> None:
    strategy = StrategyDefinition.model_validate(_payload(symbols))

    validation = validate_strategy(strategy)
    assert not validation.passed
    assert "DSL_FIVE_MINUTE_SYMBOL_SCOPE" in {issue.code for issue in validation.issues}

