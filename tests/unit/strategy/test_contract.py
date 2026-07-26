from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.backtests import (
    BacktestFailure,
    BacktestJob,
    BacktestResult,
    CostModelIds,
)
from us_intraday_lab.contracts.orders import OrderEvent, OrderIntent
from us_intraday_lab.contracts.strategies import AllCondition, StrategyDefinition

VALID = {
    "strategy_id": "mom-pullback-v1",
    "dsl_version": "1.0.0",
    "symbols": ["SPY", "QQQ", "IWM"],
    "signal_bar_size": "15min",
    "entry": {
        "all": [
            {"indicator": "ema_spread", "op": "gt", "value": 0.0},
            {"indicator": "rsi", "op": "lt", "value": 45.0},
        ]
    },
    "exit": {"any": [{"indicator": "rsi", "op": "gt", "value": 65.0}]},
    "risk": {
        "stop_loss_bps": 35,
        "take_profit_bps": 70,
        "max_holding_minutes": 90,
        "cooldown_minutes": 30,
        "max_entries_per_session": 3,
        "sizing_preset": "equal_risk_conservative",
    },
    "order_type": "market",
}


def test_strategy_contract_accepts_only_closed_dsl() -> None:
    strategy = StrategyDefinition.model_validate(VALID)
    assert strategy.signal_bar_size == "15min"


def test_strategy_contract_rejects_extra_code_field() -> None:
    payload = {**VALID, "python": "import os; os.system('whoami')"}
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(payload)


def test_strategy_contract_is_recursive_frozen_and_json_round_trippable() -> None:
    payload = {
        **VALID,
        "entry": {
            "all": [
                {"indicator": "ema_spread", "op": "gt", "value": 0.0},
                {
                    "any": [
                        {"indicator": "rsi", "op": "lt", "value": 45.0},
                        {"indicator": "range_position", "op": "lte", "value": 0.25},
                    ]
                },
            ]
        },
    }
    strategy = StrategyDefinition.model_validate(payload)

    restored = StrategyDefinition.model_validate_json(strategy.model_dump_json())

    assert restored == strategy
    assert isinstance(restored.entry, AllCondition)
    assert isinstance(restored.entry.all, tuple)
    assert restored.symbols == ("SPY", "QQQ", "IWM")
    with pytest.raises(ValidationError):
        strategy.order_type = "limit"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("dsl_version", "2.0.0"),
        ("signal_bar_size", "1min"),
        ("order_type", "stop"),
    ],
)
def test_strategy_contract_rejects_values_outside_closed_allowlists(path: str, value: str) -> None:
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate({**VALID, path: value})


def test_strategy_contract_rejects_extra_nested_fields() -> None:
    payload = {
        **VALID,
        "entry": {
            "all": [
                {
                    "indicator": "ema_spread",
                    "op": "gt",
                    "value": 0.0,
                    "expression": "__import__('os').system('whoami')",
                }
            ]
        },
    }

    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(payload)


def _order_intent() -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id="run-001",
        strategy_id="mom-pullback-v1",
        symbol="SPY",
        session=date(2026, 7, 2),
        side="buy",
        order_type="market",
        quantity=10,
        limit_price=None,
        signal_time=datetime(2026, 7, 2, 14, 0, tzinfo=UTC),
        eligible_time=datetime(2026, 7, 2, 14, 1, tzinfo=UTC),
        reason_code="entry_signal",
        idempotency_key="run-001:SPY:20260702T140000Z:buy",
    )


def test_order_intent_json_round_trip_is_frozen() -> None:
    intent = _order_intent()

    restored = OrderIntent.model_validate_json(intent.model_dump_json())

    assert restored == intent
    assert restored.signal_time.tzinfo is UTC
    assert restored.eligible_time.tzinfo is UTC
    with pytest.raises(ValidationError):
        intent.quantity = 20


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime.fromisoformat("2026-07-02T14:00:00"),
        datetime(2026, 7, 2, 22, 0, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_order_intent_rejects_non_utc_timestamps(timestamp: datetime) -> None:
    payload = _order_intent().model_dump()
    payload["signal_time"] = timestamp

    with pytest.raises(ValidationError, match="timestamp must be timezone-aware UTC"):
        OrderIntent.model_validate(payload)


def test_order_intent_rejects_non_closed_side_and_extra_fields() -> None:
    payload = _order_intent().model_dump()
    payload["side"] = "sell_short"
    payload["leverage"] = 2

    with pytest.raises(ValidationError):
        OrderIntent.model_validate(payload)


@pytest.mark.parametrize(
    ("order_type", "limit_price"),
    [
        ("market", 620.0),
        ("limit", None),
    ],
)
def test_order_intent_requires_price_only_for_limit_orders(
    order_type: str, limit_price: float | None
) -> None:
    payload = _order_intent().model_dump()
    payload["order_type"] = order_type
    payload["limit_price"] = limit_price

    with pytest.raises(ValidationError, match="limit_price"):
        OrderIntent.model_validate(payload)


def test_order_event_json_round_trip_preserves_status_transition() -> None:
    event = OrderEvent(
        schema_version="1.0.0",
        order_id="backtest-order-001",
        previous_status="accepted",
        status="partially_filled",
        event_time=datetime(2026, 7, 2, 14, 2, tzinfo=UTC),
        requested_quantity=10,
        filled_quantity=4,
        requested_price=None,
        filled_price=621.25,
        fees=0.02,
        rejection_reason=None,
    )

    restored = OrderEvent.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.event_time.tzinfo is UTC
    with pytest.raises(ValidationError):
        event.status = "filled"


def test_order_event_rejects_non_utc_event_time() -> None:
    payload = {
        "schema_version": "1.0.0",
        "order_id": "backtest-order-001",
        "previous_status": "accepted",
        "status": "filled",
        "event_time": datetime.fromisoformat("2026-07-02T14:02:00"),
        "requested_quantity": 10,
        "filled_quantity": 10,
        "requested_price": None,
        "filled_price": 621.25,
        "fees": 0.05,
        "rejection_reason": None,
    }

    with pytest.raises(ValidationError, match="timestamp must be timezone-aware UTC"):
        OrderEvent.model_validate(payload)


def test_order_event_rejects_filled_quantity_above_requested_quantity() -> None:
    payload = {
        "schema_version": "1.0.0",
        "order_id": "backtest-order-001",
        "previous_status": "partially_filled",
        "status": "filled",
        "event_time": datetime(2026, 7, 2, 14, 2, tzinfo=UTC),
        "requested_quantity": 10,
        "filled_quantity": 11,
        "requested_price": None,
        "filled_price": 621.25,
        "fees": 0.05,
        "rejection_reason": None,
    }

    with pytest.raises(ValidationError, match="filled_quantity must not exceed"):
        OrderEvent.model_validate(payload)


def _backtest_job() -> BacktestJob:
    return BacktestJob(
        schema_version="1.0.0",
        job_id="job-001",
        strategy_id="mom-pullback-v1",
        dataset_id="tiingo-iex-minute-20260702",
        engine_id="event-engine-1.0.0",
        calendar_id="XNYS-2026a",
        cost_model_ids=CostModelIds(
            optimistic="cost-optimistic-1.0.0",
            base="cost-base-1.0.0",
            stress="cost-stress-1.0.0",
        ),
    )


def test_backtest_job_json_round_trip_is_frozen_and_versioned() -> None:
    job = _backtest_job()

    restored = BacktestJob.model_validate_json(job.model_dump_json())

    assert restored == job
    with pytest.raises(ValidationError):
        job.engine_id = "different-engine"


def test_backtest_result_json_round_trip_has_typed_cost_scenarios() -> None:
    result = BacktestResult(
        schema_version="1.0.0",
        run_id="run-001",
        job_id="job-001",
        status="succeeded",
        failure=None,
        metrics_by_cost_scenario={
            "optimistic": {"net_return": 0.03},
            "base": {"net_return": 0.02},
            "stress": {"net_return": 0.01},
        },
        trades_uri="file:///artifacts/run-001/trades.parquet",
        events_uri="file:///artifacts/run-001/events.jsonl",
        content_sha256="a" * 64,
    )

    restored = BacktestResult.model_validate_json(result.model_dump_json())

    assert restored == result
    with pytest.raises(ValidationError):
        result.status = "failed"


def test_successful_backtest_result_requires_all_three_cost_scenarios() -> None:
    payload = {
        "schema_version": "1.0.0",
        "run_id": "run-001",
        "job_id": "job-001",
        "status": "succeeded",
        "failure": None,
        "metrics_by_cost_scenario": {
            "optimistic": {"net_return": 0.03},
            "base": {"net_return": 0.02},
        },
        "trades_uri": "file:///artifacts/run-001/trades.parquet",
        "events_uri": "file:///artifacts/run-001/events.jsonl",
        "content_sha256": "a" * 64,
    }

    with pytest.raises(ValidationError, match="all three cost scenarios"):
        BacktestResult.model_validate(payload)


def test_backtest_result_requires_typed_failure_when_failed() -> None:
    payload = {
        "schema_version": "1.0.0",
        "run_id": "run-002",
        "job_id": "job-001",
        "status": "failed",
        "failure": None,
        "metrics_by_cost_scenario": {},
        "trades_uri": "file:///artifacts/run-002/trades.parquet",
        "events_uri": "file:///artifacts/run-002/events.jsonl",
        "content_sha256": "b" * 64,
    }

    with pytest.raises(ValidationError, match="failed result requires a failure"):
        BacktestResult.model_validate(payload)

    restored = BacktestResult.model_validate(
        {
            **payload,
            "failure": BacktestFailure(
                failure_type="execution",
                message="fill simulation failed",
            ),
        }
    )
    assert restored.failure is not None
    assert restored.failure.failure_type == "execution"


def test_failed_backtest_result_rejects_partial_metrics() -> None:
    payload = {
        "schema_version": "1.0.0",
        "run_id": "run-002",
        "job_id": "job-001",
        "status": "failed",
        "failure": {
            "failure_type": "execution",
            "message": "fill simulation failed",
        },
        "metrics_by_cost_scenario": {"base": {"net_return": 0.01}},
        "trades_uri": "file:///artifacts/run-002/trades.parquet",
        "events_uri": "file:///artifacts/run-002/events.jsonl",
        "content_sha256": "b" * 64,
    }

    with pytest.raises(ValidationError, match="failed result must not include partial metrics"):
        BacktestResult.model_validate(payload)
