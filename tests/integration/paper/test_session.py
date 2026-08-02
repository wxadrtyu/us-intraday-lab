from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from tests.fakes.market_data import iex_minute_bar
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.paper import PaperSession
from us_intraday_lab.paper.market_data import (
    IexSubscription,
    MarketDataPipeline,
    ProviderTransitionDiagnostic,
)
from us_intraday_lab.paper.session import PaperSessionService, SessionStrategy
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.strategy.features import FEATURE_SET_VERSION

SESSION_DATE = date(2026, 8, 3)
SESSION_OPEN = datetime(2026, 8, 3, 13, 30, tzinfo=UTC)
SESSION_ID = "paper-session-2026-08-03"
EXECUTION_AT = SESSION_OPEN + timedelta(minutes=16)
CLOSEOUT_AT = datetime(2026, 8, 3, 19, 55, tzinfo=UTC)


class _AlwaysEnterStrategy:
    strategy_id = "strategy-spy"
    symbol = "SPY"
    lifecycle_state = "paper_shadow"
    stop_loss_bps = 50
    risk_fraction = 0.005
    max_position_fraction = 0.25
    daily_loss_limit = 500.0
    account_loss_limit = 1_000.0
    strategy_loss_limit = 250.0

    def should_enter(self, bar: MarketBarClosed) -> bool:
        return bar.symbol == self.symbol


def _bars() -> tuple[MarketBarClosed, ...]:
    return tuple(
        iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN + timedelta(minutes=minute))
        for minute in range(15)
    )


def _store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(
        PaperSession(
            paper_session_id=SESSION_ID,
            session_date=SESSION_DATE,
            broker_account_id="fake-paper-account",
            broker_sdk_version="fake-1.0",
            status="running",
            created_at=SESSION_OPEN,
        )
    )
    return store


def _pipeline(tmp_path: Path) -> MarketDataPipeline:
    return MarketDataPipeline(
        store=_store(tmp_path),
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY",),
    )


def test_subscription_is_restricted_to_alpaca_iex_production_symbols() -> None:
    subscription = IexSubscription(symbols=("SPY", "QQQ", "IWM"))

    assert subscription.provider == "alpaca"
    assert subscription.feed == "iex"
    with pytest.raises(ValueError, match="PRODUCTION_SYMBOL"):
        IexSubscription(symbols=("AAPL",))  # type: ignore[arg-type]


def test_out_of_order_and_duplicate_minutes_emit_one_session_anchored_bar(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline(tmp_path)
    bars = tuple(
        iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN + timedelta(minutes=minute))
        for minute in range(15)
    )

    emitted: list[MarketBarClosed] = []
    arrival_order = tuple(
        bars[index]
        for index in (1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 14)
    )
    for bar in arrival_order + (bars[7],):
        emitted.extend(pipeline.ingest(bar))

    assert len(emitted) == 1
    aggregate = emitted[0]
    assert aggregate.provider == "alpaca"
    assert aggregate.feed == "iex"
    assert aggregate.timeframe == "15min"
    assert aggregate.bar_start == SESSION_OPEN
    assert aggregate.bar_end == SESSION_OPEN + timedelta(minutes=15)
    stored = pipeline.store.list_market_events(SESSION_ID)
    assert len(tuple(item for item in stored if item.timeframe == "1min")) == 15
    assert len(tuple(item for item in stored if item.timeframe == "15min")) == 1


def test_gap_or_stale_stream_opens_the_entry_circuit(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)
    pipeline.ingest(iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN))
    pipeline.ingest(
        iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN + timedelta(minutes=2))
    )

    gap = pipeline.health(observed_at=SESSION_OPEN + timedelta(minutes=3))
    stale = pipeline.health(observed_at=SESSION_OPEN + timedelta(minutes=6))

    assert gap.entries_enabled is False
    assert "MARKET_DATA_GAP" in gap.reason_codes
    assert stale.entries_enabled is False
    assert "MARKET_DATA_STALE" in stale.reason_codes


def test_provider_transition_diagnostics_never_enter_production_bars(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline(tmp_path)
    diagnostic = ProviderTransitionDiagnostic(
        symbol="SPY",
        compared_provider="polygon",
        compared_feed="sip",
        observed_at=SESSION_OPEN,
        difference_bps=2.5,
    )

    pipeline.record_provider_transition_diagnostic(diagnostic)

    assert pipeline.provider_transition_diagnostics == (diagnostic,)
    assert pipeline.store.list_market_events(SESSION_ID) == ()


def test_pipeline_rejects_schema_or_feature_version_drift(tmp_path: Path) -> None:
    store = _store(tmp_path)
    arguments = {
        "store": store,
        "paper_session_id": SESSION_ID,
        "session_date": SESSION_DATE,
        "reorder_window": timedelta(minutes=2),
        "stale_after": timedelta(minutes=2),
        "required_symbols": ("SPY",),
    }
    with pytest.raises(RuntimeError, match="MARKET_SCHEMA_VERSION_MISMATCH"):
        MarketDataPipeline(
            **arguments,
            expected_market_schema_version="9.9.9",
            expected_feature_set_version=FEATURE_SET_VERSION,
        )
    with pytest.raises(RuntimeError, match="FEATURE_SET_VERSION_MISMATCH"):
        MarketDataPipeline(
            **arguments,
            expected_market_schema_version="1.0.0",
            expected_feature_set_version="15m-v9.9.9",
        )


def test_missing_required_symbol_stream_disables_entries(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY", "QQQ"),
    )
    pipeline.ingest(iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN))

    health = pipeline.health(observed_at=SESSION_OPEN + timedelta(minutes=1))

    assert health.entries_enabled is False
    assert "REQUIRED_SYMBOL_STREAM_MISSING" in health.reason_codes


def test_automated_session_is_restart_safe_and_closes_flat(tmp_path: Path) -> None:
    store = _store(tmp_path)
    broker = FakePaperBroker(now=EXECUTION_AT)
    strategy: SessionStrategy = _AlwaysEnterStrategy()
    pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY",),
    )
    service = PaperSessionService(
        store=store,
        broker=broker,
        market_data=pipeline,
        strategies=(strategy,),
        session_date=SESSION_DATE,
        closeout_buffer_minutes=5,
    )
    assert service.start(completed_at=SESSION_OPEN).status == "clean"
    broker.queue_submit_behavior(SubmitBehavior.FILL)

    first = service.process_bars(_bars(), observed_at=EXECUTION_AT)

    assert first.entries_enabled is True
    assert first.submitted_entry_count == 1
    intent = store.get_order_intent(broker.submitted_idempotency_keys[0])
    assert intent is not None
    assert intent.eligible_time == EXECUTION_AT
    assert broker.positions()[0].symbol == "SPY"
    assert store.get_strategy_session_state(SESSION_ID, "strategy-spy").entry_count == 1

    restarted_pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY",),
    )
    restarted = PaperSessionService(
        store=store,
        broker=broker,
        market_data=restarted_pipeline,
        strategies=(strategy,),
        session_date=SESSION_DATE,
        closeout_buffer_minutes=5,
    )
    assert restarted.start(completed_at=EXECUTION_AT).status == "clean"
    repeated = restarted.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert repeated.submitted_entry_count == 0
    assert len(broker.submitted_idempotency_keys) == 1

    broker.set_now(CLOSEOUT_AT)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    closeout = restarted.closeout(closeout_at=CLOSEOUT_AT)
    assert closeout.clean is True
    assert broker.positions() == ()
