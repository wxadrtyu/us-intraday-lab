import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from typer.testing import CliRunner

from us_intraday_lab.cli import app
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    IncidentEvent,
    PaperCheckpoint,
    PaperSession,
    PositionSnapshot,
    ReconciliationResult,
    RiskDecision,
)
from us_intraday_lab.contracts.strategies import (
    ComparisonCondition,
    RiskDefinition,
    StrategyDefinition,
)
from us_intraday_lab.contracts.validation import GateEvidence, GateResult, ValidationDecision
from us_intraday_lab.forward.lifecycle import promote_ranked
from us_intraday_lab.forward.ranking import DEFAULT_WEIGHTS, RankingResult
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.registry.store import RegistryStore
from us_intraday_lab.reporting.paper_daily import (
    daily_report_context,
    render_paper_daily_report,
)
from us_intraday_lab.reporting.strategy_detail import render_strategy_detail_report

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
SESSION_DATE = date(2026, 8, 3)
SESSION_ID = "paper-2026-08-03"
STRATEGY_ID = "strategy-report-a"


def _definition() -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=STRATEGY_ID,
        dsl_version="1.0.0",
        symbols=("SPY", "QQQ", "IWM"),
        signal_bar_size="15min",
        entry=ComparisonCondition(indicator="return_3", op="gt", value=0.01),
        exit=ComparisonCondition(indicator="return_1", op="lt", value=0.0),
        risk=RiskDefinition(
            stop_loss_bps=50,
            take_profit_bps=100,
            max_holding_minutes=60,
            cooldown_minutes=15,
            max_entries_per_session=2,
            sizing_preset="equal_cash_conservative",
        ),
        order_type="market",
    )


def _registry(root: Path) -> RegistryStore:
    store = RegistryStore(root / "data" / "registry" / "strategy_registry.sqlite3")
    definition = _definition()
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    store.register_strategy(
        definition,
        content_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        idempotency_key="register:report-a",
        actor="factory",
        occurred_at=NOW,
    )
    gate_evidence = GateEvidence(
        evidence_id="historical-gate-a",
        metric_name="net_return",
        source_refs=("backtest:a",),
        values={"net_return": 0.10},
    )
    decision = ValidationDecision(
        decision_id="validation-report-a",
        strategy_id=STRATEGY_ID,
        split_id="split-report-a",
        decision="PROMOTE_TO_PAPER_SHADOW",
        gate_results=(
            GateResult(
                reason_code="HISTORICAL_RETURN_GATE",
                threshold=0.0,
                observed=0.10,
                passed=True,
                evidence=gate_evidence,
            ),
        ),
        decided_at=NOW,
    )
    store.record_validation_decision(decision)
    store.transition_strategy(
        STRATEGY_ID,
        to_state="candidate",
        idempotency_key="candidate:report-a",
        actor="validation",
        reason_code="VALIDATION_COMPLETE",
        immutable_refs={"decision_id": decision.decision_id},
        occurred_at=NOW,
    )
    store.transition_strategy(
        STRATEGY_ID,
        to_state="paper_shadow",
        idempotency_key="shadow:report-a",
        actor="validation",
        reason_code="SELECTED_SURVIVOR",
        immutable_refs={"decision_id": decision.decision_id},
        occurred_at=NOW,
    )
    store.transition_strategy(
        STRATEGY_ID,
        to_state="paper_observing",
        idempotency_key="observing:report-a",
        actor="paper",
        reason_code="PAPER_FORWARD_STARTED",
        immutable_refs={"paper_config_id": "paper-v1"},
        occurred_at=NOW,
    )
    promote_ranked(
        store,
        RankingResult(
            strategy_id=STRATEGY_ID,
            evidence_id="forward-report-a",
            rank=1,
            quality_score=0.88,
            component_values=MappingProxyType(
                {
                    "net_return": 0.123,
                    "max_drawdown": 0.02,
                    "profit_factor": 1.8,
                    "expectancy": 4.0,
                    "day_consistency": 0.6,
                    "week_consistency": 0.7,
                    "cost_realization": -0.5,
                    "symbol_concentration": 0.4,
                    "historical_divergence": 0.03,
                }
            ),
            component_scores=MappingProxyType({name: 0.9 for name in DEFAULT_WEIGHTS}),
            weights=DEFAULT_WEIGHTS,
        ),
        occurred_at=NOW,
    )
    return store


def _intent(key: str, *, side: str, reason: str) -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id=SESSION_ID,
        strategy_id=STRATEGY_ID,
        symbol="SPY",
        session=SESSION_DATE,
        side=side,
        order_type="market",
        quantity=10,
        signal_time=NOW,
        eligible_time=NOW + timedelta(minutes=1),
        reason_code=reason,
        idempotency_key=key,
    )  # type: ignore[arg-type]


def _bundle(
    store: PaperStore,
    *,
    key: str,
    side: str,
    reason: str,
    sequence: int,
    status: str,
    price: float | None,
) -> None:
    intent = _intent(key, side=side, reason=reason)
    risk = RiskDecision(
        decision_id=f"risk-{key}",
        idempotency_key=key,
        approved=True,
        reason_code="ENTRY_RISK_APPROVED",
        observed_values={"available_cash": 25_000.0},
        decided_at=NOW + timedelta(minutes=sequence),
    )
    order = BrokerOrder(
        broker_order_id=f"broker-{key}",
        client_order_id=key,
        symbol="SPY",
        side=side,
        order_type="market",
        status=status,
        quantity=10,
        filled_quantity=0 if price is None else 10,
        average_fill_price=price,
        submitted_at=NOW + timedelta(minutes=sequence),
        updated_at=NOW + timedelta(minutes=sequence),
        rejection_reason="TEST_REJECT" if status == "rejected" else None,
    )  # type: ignore[arg-type]
    checkpoint = PaperCheckpoint(
        checkpoint_id=f"checkpoint-{sequence}",
        paper_session_id=SESSION_ID,
        event_sequence=sequence,
        state_sha256=str(sequence).rjust(64, "0"),
        created_at=NOW + timedelta(minutes=sequence),
    )
    store.record_order_bundle(
        intent=intent, risk_decision=risk, broker_order=order, checkpoint=checkpoint
    )


def _paper(root: Path) -> PaperStore:
    store = PaperStore(root / "state" / "paper" / "paper.sqlite3")
    store.create_session(
        PaperSession(
            paper_session_id=SESSION_ID,
            session_date=SESSION_DATE,
            broker_account_id="paper-account-1",
            broker_sdk_version="0.43.5",
            status="closed",
            created_at=NOW,
        )
    )
    _bundle(
        store,
        key="buy-a",
        side="buy",
        reason="entry_signal",
        sequence=1,
        status="filled",
        price=100.0,
    )
    _bundle(
        store,
        key="sell-a",
        side="sell",
        reason="session_close",
        sequence=2,
        status="filled",
        price=102.0,
    )
    _bundle(
        store,
        key="rejected-a",
        side="buy",
        reason="entry_signal",
        sequence=3,
        status="rejected",
        price=None,
    )
    store.append_market_event(
        SESSION_ID,
        MarketBarClosed(
            provider_event_id="absurd-market-price",
            symbol="SPY",
            timeframe="1min",
            bar_start=NOW,
            bar_end=NOW + timedelta(minutes=1),
            available_at=NOW + timedelta(minutes=1),
            open=9_999.0,
            high=10_001.0,
            low=9_998.0,
            close=10_000.0,
            volume=1_000,
        ),
    )
    store.append_position_snapshot(
        PositionSnapshot(
            snapshot_id="final-flat",
            paper_session_id=SESSION_ID,
            positions=(),
            observed_at=NOW + timedelta(hours=6),
        )
    )
    store.append_reconciliation(
        ReconciliationResult(
            reconciliation_id="recon-clean",
            paper_session_id=SESSION_ID,
            status="clean",
            entries_enabled=True,
            exits_enabled=True,
            discrepancy_codes=(),
            startup_steps=("LOAD_CHECKPOINT",),
            broker_account_id="paper-account-1",
            local_state_sha256="a" * 64,
            broker_state_sha256="a" * 64,
            completed_at=NOW,
        )
    )
    store.append_incident(
        IncidentEvent(
            incident_id="incident-warning-a",
            paper_session_id=SESSION_ID,
            severity="warning",
            reason_code="TEST_WARNING",
            observed_values={"handled": True},
            occurred_at=NOW + timedelta(hours=1),
        )
    )
    return store


def test_daily_report_reconciles_exactly_to_stored_broker_evidence(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    paper = _paper(tmp_path)

    context = daily_report_context(
        paper_store=paper, registry_store=registry, session_date=SESSION_DATE
    )
    path = render_paper_daily_report(
        root=tmp_path,
        paper_store=paper,
        registry_store=registry,
        session_date=SESSION_DATE,
    )
    report = path.read_text(encoding="utf-8")

    assert context["daily_pnl"] == 20.0
    assert context["closed_trade_count"] == 1
    assert context["max_drawdown"] == 0.0
    assert context["rejected_order_count"] == 1
    assert context["reconciliation_status"] == "clean"
    assert context["flat_at_close"] is True
    assert "$20.00" in report
    assert "1 笔" in report
    assert "TEST_WARNING" in report
    assert "0.88" in report
    assert "10,000.00" not in report
    assert "不使用 K 线推算成交" in report
    assert path == tmp_path / "reports" / "generated" / "paper" / "2026-08-03.md"


def test_strategy_detail_and_cli_render_stored_definition_gates_and_trades(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    paper = _paper(tmp_path)
    path = render_strategy_detail_report(
        root=tmp_path,
        paper_store=paper,
        registry_store=registry,
        strategy_id=STRATEGY_ID,
    )
    detail = path.read_text(encoding="utf-8")
    assert "HISTORICAL_RETURN_GATE" in detail
    assert "split-report-a" in detail
    assert '"stop_loss_bps": 50' in detail
    assert "$20.00" in detail
    assert "paper_ranked" in detail
    assert "0.123" in detail
    assert "0.2" in detail

    runner = CliRunner()
    daily_result = runner.invoke(
        app,
        ["report", "paper-daily", "--session", "2026-08-03", "--root", str(tmp_path)],
    )
    strategy_result = runner.invoke(
        app,
        ["report", "strategy", "--strategy-id", STRATEGY_ID, "--root", str(tmp_path)],
    )
    assert daily_result.exit_code == 0, daily_result.output
    assert strategy_result.exit_code == 0, strategy_result.output
    assert "reports" in daily_result.output
    assert STRATEGY_ID in strategy_result.output
