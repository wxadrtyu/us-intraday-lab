import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from us_intraday_lab.contracts.strategies import (
    ComparisonCondition,
    RiskDefinition,
    StrategyDefinition,
)
from us_intraday_lab.contracts.validation import (
    GateEvidence,
    GateResult,
    ValidationDecision,
)
from us_intraday_lab.registry.lifecycle import LifecycleError
from us_intraday_lab.registry.store import (
    IdempotencyConflict,
    ImmutableRecordConflict,
    RegistryStore,
)

NOW = datetime(2026, 8, 2, 3, 0, tzinfo=UTC)


def _definition(strategy_id: str = "strategy-a", *, threshold: float = 0.01) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=strategy_id,
        dsl_version="1.0.0",
        symbols=("SPY", "QQQ", "IWM"),
        signal_bar_size="15min",
        entry=ComparisonCondition(indicator="return_3", op="gt", value=threshold),
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


def _content_hash(definition: StrategyDefinition) -> str:
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decision(strategy_id: str = "strategy-a", *, passed: bool = True) -> ValidationDecision:
    gate = GateResult(
        reason_code="BASE_RETURN_GATE",
        threshold=0.0,
        observed=0.05 if passed else -0.01,
        passed=passed,
        evidence=GateEvidence(
            evidence_id=f"evidence-{strategy_id}",
            metric_name="base_net_return",
            source_refs=("backtest:test",),
            values={"base_net_return": 0.05 if passed else -0.01},
        ),
    )
    return ValidationDecision(
        decision_id=f"decision-{strategy_id}-{'pass' if passed else 'fail'}",
        strategy_id=strategy_id,
        split_id="split-a",
        decision="PROMOTE_TO_PAPER_SHADOW" if passed else "REJECT",
        gate_results=(gate,),
        decided_at=NOW,
    )


@pytest.fixture
def store(tmp_path: Path) -> RegistryStore:
    return RegistryStore(tmp_path / "registry.sqlite3")


def _register(store: RegistryStore, strategy_id: str = "strategy-a"):
    definition = _definition(strategy_id)
    return store.register_strategy(
        definition,
        content_sha256=_content_hash(definition),
        idempotency_key=f"register:{strategy_id}",
        actor="factory",
        occurred_at=NOW,
    )


def _promote_to_candidate(store: RegistryStore, strategy_id: str = "strategy-a") -> None:
    decision = _decision(strategy_id)
    store.record_validation_decision(decision)
    store.transition_strategy(
        strategy_id,
        to_state="candidate",
        idempotency_key=f"candidate:{strategy_id}",
        actor="validation-service",
        reason_code="ALL_HARD_GATES_PASSED",
        immutable_refs={"decision_id": decision.decision_id},
        occurred_at=NOW,
    )


def test_store_enables_sqlite_safety_pragmas_and_creates_required_tables(
    store: RegistryStore,
) -> None:
    with sqlite3.connect(store.path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert journal_mode == "wal"
    assert foreign_keys == 0  # Per-connection; RegistryStore enables it on every owned connection.
    assert {
        "strategy_definitions",
        "validation_decisions",
        "registry_events",
        "strategy_current_state",
    } <= tables
    assert store.connection_pragmas() == {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": 5_000,
    }


def test_registration_atomically_appends_generated_event_and_current_state(
    store: RegistryStore,
) -> None:
    event = _register(store)

    assert event.from_state is None
    assert event.to_state == "generated"
    assert store.get_current_state("strategy-a") == "generated"
    assert store.get_strategy_definition("strategy-a") == _definition()
    assert store.list_events("strategy-a") == (event,)


def test_all_allowed_lifecycle_paths(store: RegistryStore) -> None:
    _register(store)
    _promote_to_candidate(store)
    store.transition_strategy(
        "strategy-a",
        to_state="paper_shadow",
        idempotency_key="paper:strategy-a",
        actor="validation-service",
        reason_code="SELECTED_SURVIVOR",
        immutable_refs={"decision_id": _decision().decision_id},
        occurred_at=NOW,
    )
    store.transition_strategy(
        "strategy-a",
        to_state="rejected",
        idempotency_key="reject-paper:strategy-a",
        actor="validation-service",
        reason_code="PAPER_SHADOW_REJECTED",
        immutable_refs={"evidence_id": "paper-evidence-a"},
        occurred_at=NOW,
    )

    _register(store, "strategy-b")
    _promote_to_candidate(store, "strategy-b")
    store.transition_strategy(
        "strategy-b",
        to_state="rejected",
        idempotency_key="reject-candidate:strategy-b",
        actor="validation-service",
        reason_code="VALIDATION_REVIEW_REJECTED",
        immutable_refs={"decision_id": _decision("strategy-b").decision_id},
        occurred_at=NOW,
    )

    assert store.get_current_state("strategy-a") == "rejected"
    assert store.get_current_state("strategy-b") == "rejected"
    assert tuple(event.to_state for event in store.list_events("strategy-a")) == (
        "generated",
        "candidate",
        "paper_shadow",
        "rejected",
    )


def test_skipping_validation_or_illegal_reentry_is_rejected_without_partial_event(
    store: RegistryStore,
) -> None:
    _register(store)

    with pytest.raises(LifecycleError, match="ILLEGAL_REGISTRY_TRANSITION"):
        store.transition_strategy(
            "strategy-a",
            to_state="paper_shadow",
            idempotency_key="skip-validation",
            actor="factory",
            reason_code="SKIP",
            immutable_refs={"decision_id": "missing"},
            occurred_at=NOW,
        )

    assert store.get_current_state("strategy-a") == "generated"
    assert len(store.list_events("strategy-a")) == 1


def test_promotion_requires_stored_passing_decision_for_same_strategy(
    store: RegistryStore,
) -> None:
    _register(store)
    store.transition_strategy(
        "strategy-a",
        to_state="candidate",
        idempotency_key="candidate:awaiting-decision",
        actor="validation-service",
        reason_code="VALIDATION_COMPLETE",
        immutable_refs={"experiment_id": "experiment-a"},
        occurred_at=NOW,
    )
    failing = _decision(passed=False)
    store.record_validation_decision(failing)

    with pytest.raises(LifecycleError, match="PASSING_VALIDATION_DECISION_REQUIRED"):
        store.transition_strategy(
            "strategy-a",
            to_state="paper_shadow",
            idempotency_key="paper-with-failure",
            actor="validation-service",
            reason_code="PROMOTE",
            immutable_refs={"decision_id": failing.decision_id},
            occurred_at=NOW,
        )

    assert store.get_current_state("strategy-a") == "candidate"


def test_candidate_state_records_evaluation_entry_without_claiming_gate_success(
    store: RegistryStore,
) -> None:
    _register(store)

    event = store.transition_strategy(
        "strategy-a",
        to_state="candidate",
        idempotency_key="candidate:strategy-a:no-decision-yet",
        actor="validation-service",
        reason_code="VALIDATION_COMPLETE",
        immutable_refs={"experiment_id": "experiment-a"},
        occurred_at=NOW,
    )

    assert event.to_state == "candidate"
    assert store.get_current_state("strategy-a") == "candidate"


def test_event_idempotency_is_exact_and_conflicts_do_not_mutate_state(store: RegistryStore) -> None:
    first = _register(store)
    repeated = _register(store)
    assert repeated == first

    with pytest.raises(IdempotencyConflict, match="IDEMPOTENCY_KEY_CONTENT_MISMATCH"):
        store.register_strategy(
            _definition(),
            content_sha256=_content_hash(_definition()),
            idempotency_key="register:strategy-a",
            actor="different-actor",
            occurred_at=NOW,
        )

    assert store.list_events("strategy-a") == (first,)


def test_definitions_and_decisions_are_immutable(store: RegistryStore) -> None:
    _register(store)
    decision = _decision()
    store.record_validation_decision(decision)
    assert store.record_validation_decision(decision) == decision

    changed = decision.model_copy(update={"split_id": "other-split"})
    with pytest.raises(ImmutableRecordConflict, match="IMMUTABLE_DECISION_CONFLICT"):
        store.record_validation_decision(changed)

    changed_definition = _definition(threshold=0.02)
    with pytest.raises(ImmutableRecordConflict, match="IMMUTABLE_STRATEGY_CONFLICT"):
        store.register_strategy(
            changed_definition,
            content_sha256=_content_hash(changed_definition),
            idempotency_key="register:changed",
            actor="factory",
            occurred_at=NOW,
        )


@pytest.mark.parametrize(
    "table", ["strategy_definitions", "validation_decisions", "registry_events"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_raw_sql_cannot_rewrite_or_delete_immutable_ledger_rows(
    store: RegistryStore,
    table: str,
    operation: str,
) -> None:
    _register(store)
    store.record_validation_decision(_decision())
    sql = (
        f"UPDATE {table} SET created_at = created_at"
        if operation == "UPDATE" and table == "strategy_definitions"
        else f"UPDATE {table} SET strategy_id = strategy_id"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )

    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"),
    ):
        connection.execute(sql)


def test_derived_current_state_rejects_unknown_database_values(store: RegistryStore) -> None:
    _register(store)

    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match="DERIVED_STATE|CHECK constraint failed",
        ),
    ):
        connection.execute("UPDATE strategy_current_state SET current_state = 'unapproved'")


def test_derived_current_state_cannot_be_rewritten_without_matching_event(
    store: RegistryStore,
) -> None:
    _register(store)

    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match="DERIVED_STATE_REQUIRES_MATCHING_EVENT",
        ),
    ):
        connection.execute("UPDATE strategy_current_state SET current_state = 'candidate'")

    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match="DERIVED_STATE_CANNOT_BE_DELETED",
        ),
    ):
        connection.execute("DELETE FROM strategy_current_state")


def test_wrong_definition_hash_is_rejected_before_any_write(store: RegistryStore) -> None:
    with pytest.raises(ValueError, match="content_sha256"):
        store.register_strategy(
            _definition(),
            content_sha256="0" * 64,
            idempotency_key="register:bad-hash",
            actor="factory",
            occurred_at=NOW,
        )

    assert store.get_current_state("strategy-a") is None


def test_transition_retry_returns_original_event_after_state_has_advanced(
    store: RegistryStore,
) -> None:
    _register(store)
    decision = _decision()
    store.record_validation_decision(decision)
    arguments = {
        "to_state": "candidate",
        "idempotency_key": "candidate:retry",
        "actor": "validation-service",
        "reason_code": "ALL_HARD_GATES_PASSED",
        "immutable_refs": {"decision_id": decision.decision_id},
        "occurred_at": NOW,
    }

    first = store.transition_strategy("strategy-a", **arguments)  # type: ignore[arg-type]
    repeated = store.transition_strategy("strategy-a", **arguments)  # type: ignore[arg-type]

    assert repeated == first
    assert len(store.list_events("strategy-a")) == 2


def test_failed_current_state_update_rolls_back_the_appended_event(store: RegistryStore) -> None:
    _register(store)
    decision = _decision()
    store.record_validation_decision(decision)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_test_state_update
            BEFORE UPDATE ON strategy_current_state
            BEGIN
                SELECT RAISE(ABORT, 'TEST_STATE_UPDATE_FAILURE');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="TEST_STATE_UPDATE_FAILURE"):
        store.transition_strategy(
            "strategy-a",
            to_state="candidate",
            idempotency_key="candidate:forced-failure",
            actor="validation-service",
            reason_code="ALL_HARD_GATES_PASSED",
            immutable_refs={"decision_id": decision.decision_id},
            occurred_at=NOW,
        )

    assert store.get_current_state("strategy-a") == "generated"
    assert tuple(event.to_state for event in store.list_events("strategy-a")) == ("generated",)


def test_concurrent_same_request_writes_exactly_one_event(store: RegistryStore) -> None:
    definition = _definition()
    content_hash = _content_hash(definition)

    def register_once() -> str:
        return store.register_strategy(
            definition,
            content_sha256=content_hash,
            idempotency_key="register:concurrent",
            actor="factory",
            occurred_at=NOW,
        ).event_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        event_ids = tuple(executor.map(lambda _: register_once(), range(8)))

    assert len(set(event_ids)) == 1
    assert len(store.list_events("strategy-a")) == 1
