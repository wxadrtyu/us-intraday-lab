from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, cast

import pandas as pd

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import EngineRun
from us_intraday_lab.backtest.metrics import EquityPoint, TradeRecord
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.long_horizon.engine import (
    FIVE_MINUTE_ENGINE_ID,
    FIVE_MINUTE_FEATURE_SET_VERSION,
    FiveMinuteBacktestEngine,
    five_minute_input_sha256,
)
from us_intraday_lab.long_horizon.final_ledger import (
    CampaignFinalLedger,
    FinalTestIsolationError,
)
from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.metrics import (
    LongHorizonOosMetrics,
    compute_long_horizon_oos_metrics,
)
from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal
from us_intraday_lab.long_horizon.snapshot import read_five_minute_snapshot
from us_intraday_lab.long_horizon.splits import LongHorizonSplit, create_long_horizon_split
from us_intraday_lab.long_horizon.variants import generate_long_horizon_variants
from us_intraday_lab.strategy.compiler import compile_strategy
from us_intraday_lab.strategy.validator import FIVE_MINUTE_SYMBOL_SCOPES
from us_intraday_lab.validation.stability import assess_symbol_concentration


class NoLongHorizonCandidateError(RuntimeError):
    """Raised when fewer than four validation survivors satisfy pre-final floors."""


@dataclass(frozen=True, slots=True)
class PhaseEvaluation:
    strategy_id: str
    sessions: tuple[date, ...]
    base_session_returns: tuple[float, ...]
    stress_session_returns: tuple[float, ...]
    cost_1_5x_session_returns: tuple[float, ...]
    closed_trades: int
    max_drawdown: float
    profit_factor: float
    pnl_by_symbol: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.sessions:
            raise ValueError("phase evaluation requires a strategy and sessions")
        if not (
            len(self.sessions)
            == len(self.base_session_returns)
            == len(self.stress_session_returns)
            == len(self.cost_1_5x_session_returns)
        ):
            raise ValueError("phase return evidence must cover every session")
        if self.closed_trades < 0 or not 0.0 <= self.max_drawdown <= 1.0:
            raise ValueError("phase trade and drawdown evidence is invalid")
        values = (
            *self.base_session_returns,
            *self.stress_session_returns,
            *self.cost_1_5x_session_returns,
            self.profit_factor,
            *self.pnl_by_symbol.values(),
        )
        if any(
            not math.isfinite(value) or value <= -1.0 for value in values[: len(self.sessions) * 3]
        ):
            raise ValueError("phase session returns must be finite and greater than -1")
        if not math.isfinite(self.profit_factor) or any(
            not math.isfinite(value) for value in self.pnl_by_symbol.values()
        ):
            raise ValueError("phase summary evidence must be finite")

    @property
    def base_total_return(self) -> float:
        return math.prod(1.0 + value for value in self.base_session_returns) - 1.0

    @property
    def stress_total_return(self) -> float:
        return math.prod(1.0 + value for value in self.stress_session_returns) - 1.0

    @property
    def stress_annualized_return(self) -> float:
        return float((1.0 + self.stress_total_return) ** (252 / len(self.sessions)) - 1.0)

    @property
    def cost_1_5x_total_return(self) -> float:
        return math.prod(1.0 + value for value in self.cost_1_5x_session_returns) - 1.0

    @property
    def cost_1_5x_annualized_return(self) -> float:
        return float((1.0 + self.cost_1_5x_total_return) ** (252 / len(self.sessions)) - 1.0)


class LongHorizonResearchBackend(Protocol):
    def accepted_sessions(self, dataset_id: str) -> tuple[date, ...]: ...

    def evaluate(
        self,
        strategy: StrategyDefinition,
        sessions: tuple[date, ...],
        *,
        phase: str,
    ) -> PhaseEvaluation: ...

    def benchmark_returns(
        self,
        strategy: StrategyDefinition,
        sessions: tuple[date, ...],
    ) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class CampaignSelection:
    experiment_id: str
    dataset_id: str
    split: LongHorizonSplit
    winner_id: str
    survivor_ids: tuple[str, ...]
    survivor_strategies: tuple[StrategyDefinition, ...]
    validation_evaluations: tuple[PhaseEvaluation, ...]
    selection_manifest: Path
    selection_sha256: str

    @property
    def winner_strategy(self) -> StrategyDefinition:
        return next(
            strategy
            for strategy in self.survivor_strategies
            if strategy.strategy_id == self.winner_id
        )

    @property
    def winner_validation(self) -> PhaseEvaluation:
        return next(
            result for result in self.validation_evaluations if result.strategy_id == self.winner_id
        )


@dataclass(frozen=True, slots=True)
class CampaignFinalization:
    experiment_id: str
    dataset_id: str
    winner_id: str
    final_consumed: bool
    final_evidence_sha256: str
    oos_metrics: LongHorizonOosMetrics


def _phase_from_record(record: Mapping[str, object]) -> PhaseEvaluation:
    return PhaseEvaluation(
        strategy_id=str(record["strategy_id"]),
        sessions=tuple(
            date.fromisoformat(str(value)) for value in cast(list[object], record["sessions"])
        ),
        base_session_returns=tuple(
            float(cast("float | int", value))
            for value in cast(list[object], record["base_session_returns"])
        ),
        stress_session_returns=tuple(
            float(cast("float | int", value))
            for value in cast(list[object], record["stress_session_returns"])
        ),
        cost_1_5x_session_returns=tuple(
            float(cast("float | int", value))
            for value in cast(list[object], record["cost_1_5x_session_returns"])
        ),
        closed_trades=int(cast(int, record["closed_trades"])),
        max_drawdown=float(cast(float, record["max_drawdown"])),
        profit_factor=float(cast(float, record["profit_factor"])),
        pnl_by_symbol={
            str(symbol): float(cast("float | int", value))
            for symbol, value in cast(dict[str, object], record["pnl_by_symbol"]).items()
        },
    )


def load_campaign_selection(path: Path) -> CampaignSelection:
    """Load and structurally validate one content-addressed selection manifest."""

    raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    return CampaignSelection(
        experiment_id=str(raw["experiment_id"]),
        dataset_id=str(raw["dataset_id"]),
        split=LongHorizonSplit.model_validate(raw["split"]),
        winner_id=str(raw["winner_id"]),
        survivor_ids=tuple(str(value) for value in cast(list[object], raw["survivor_ids"])),
        survivor_strategies=tuple(
            StrategyDefinition.model_validate(value)
            for value in cast(list[object], raw["survivor_strategies"])
        ),
        validation_evaluations=tuple(
            _phase_from_record(cast(dict[str, object], value))
            for value in cast(list[object], raw["validation_evaluations"])
        ),
        selection_manifest=path.resolve(),
        selection_sha256=str(raw["selection_sha256"]),
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else str(item),
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _stage(
    experiment_root: Path,
    *,
    stage: str,
    payload: Mapping[str, object],
) -> str:
    log = experiment_root / "events.jsonl"
    previous = "0" * 64
    if log.is_file():
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        if lines:
            previous = str(json.loads(lines[-1])["event_sha256"])
    record = {
        "occurred_at": datetime.now(UTC).isoformat(),
        "payload": dict(payload),
        "previous_event_sha256": previous,
        "stage": stage,
    }
    record["event_sha256"] = _sha256(record)
    with log.open("a", encoding="utf-8", newline="\n") as sink:
        sink.write(_canonical_json(record) + "\n")
    return cast(str, record["event_sha256"])


def _phase_record(evaluation: PhaseEvaluation) -> dict[str, object]:
    return {
        "strategy_id": evaluation.strategy_id,
        "sessions": [value.isoformat() for value in evaluation.sessions],
        "base_session_returns": list(evaluation.base_session_returns),
        "stress_session_returns": list(evaluation.stress_session_returns),
        "cost_1_5x_session_returns": list(evaluation.cost_1_5x_session_returns),
        "closed_trades": evaluation.closed_trades,
        "max_drawdown": evaluation.max_drawdown,
        "profit_factor": evaluation.profit_factor,
        "pnl_by_symbol": dict(sorted(evaluation.pnl_by_symbol.items())),
    }


def _checkpointed_evaluate(
    backend: LongHorizonResearchBackend,
    strategy: StrategyDefinition,
    sessions: tuple[date, ...],
    *,
    phase: str,
    dataset_id: str,
    experiment_root: Path,
) -> PhaseEvaluation:
    cache_key = _sha256(
        {
            "dataset_id": dataset_id,
            "engine_id": FIVE_MINUTE_ENGINE_ID,
            "feature_set_version": FIVE_MINUTE_FEATURE_SET_VERSION,
            "phase": phase,
            "sessions": sessions,
            "strategy": strategy.model_dump(mode="json"),
        }
    )
    checkpoint = experiment_root / "checkpoints" / phase / f"{cache_key}.json"
    if checkpoint.is_file():
        try:
            envelope = cast(dict[str, object], json.loads(checkpoint.read_text(encoding="utf-8")))
            if envelope.get("cache_key") != cache_key:
                raise ValueError("phase checkpoint cache key mismatch")
            evaluation = _phase_from_record(cast(dict[str, object], envelope["evaluation"]))
        except (KeyError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError("phase checkpoint is invalid") from error
        if evaluation.strategy_id != strategy.strategy_id or evaluation.sessions != sessions:
            raise ValueError("phase checkpoint scope mismatch")
        return evaluation
    evaluation = backend.evaluate(strategy, sessions, phase=phase)
    if evaluation.strategy_id != strategy.strategy_id or evaluation.sessions != sessions:
        raise ValueError("backend phase evaluation scope mismatch")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"cache_key": cache_key, "evaluation": _phase_record(evaluation)},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, checkpoint)
    return evaluation


def _passes_train(evaluation: PhaseEvaluation) -> bool:
    return (
        evaluation.base_total_return > 0.0
        and evaluation.cost_1_5x_total_return > 0.0
        and evaluation.max_drawdown <= 0.08
        and evaluation.profit_factor >= 1.0
    )


def _passes_validation(evaluation: PhaseEvaluation) -> bool:
    matching_scopes = tuple(
        scope for scope in FIVE_MINUTE_SYMBOL_SCOPES if set(evaluation.pnl_by_symbol) == set(scope)
    )
    if len(matching_scopes) != 1:
        raise ValueError("evaluation uses an unsupported symbol scope")
    symbol_scope = matching_scopes[0]
    return (
        evaluation.base_total_return > 0.0
        and evaluation.cost_1_5x_total_return > 0.0
        and evaluation.max_drawdown <= 0.08
        and evaluation.profit_factor >= 1.15
        and assess_symbol_concentration(
            evaluation.pnl_by_symbol,
            required_symbols=symbol_scope,
        ).passed
    )


def _default_backend(root: Path, dataset_id: str) -> LocalFiveMinuteResearchBackend:
    return LocalFiveMinuteResearchBackend(root=root, dataset_id=dataset_id)


def screen_long_horizon_campaign(
    proposals: tuple[LongHorizonHypothesisProposal, ...],
    *,
    dataset_id: str,
    root: Path,
    backend: LongHorizonResearchBackend | None = None,
) -> CampaignSelection:
    """Run train/validation selection without constructing or reading final data."""

    if type(proposals) is not tuple or not proposals:
        raise TypeError("proposals must be a non-empty exact tuple")
    if any(type(proposal) is not LongHorizonHypothesisProposal for proposal in proposals):
        raise TypeError("proposals must contain exact long-horizon proposals")
    if len({proposal.proposal_id for proposal in proposals}) != len(proposals):
        raise ValueError("proposal_id values must be unique within a campaign")
    effective_backend = backend or _default_backend(root, dataset_id)
    sessions = effective_backend.accepted_sessions(dataset_id)
    split = create_long_horizon_split(sessions, split_id=f"{dataset_id}-60-20-20-v1")
    proposal_records = [proposal.model_dump(mode="json") for proposal in proposals]
    experiment_id = (
        "lh-"
        + _sha256(
            {"dataset_id": dataset_id, "proposals": proposal_records, "split_id": split.split_id}
        )[:32]
    )
    experiment_root = root.resolve() / "artifacts" / "long_horizon" / "experiments" / experiment_id
    experiment_root.mkdir(parents=True, exist_ok=True)
    _stage(
        experiment_root,
        stage="PROPOSAL_ACCEPTED",
        payload={
            "dataset_id": dataset_id,
            "proposal_ids": [item.proposal_id for item in proposals],
        },
    )
    variants_by_proposal = {
        proposal.proposal_id: generate_long_horizon_variants(proposal) for proposal in proposals
    }
    variants = tuple(
        strategy
        for proposal in proposals
        for strategy in variants_by_proposal[proposal.proposal_id]
    )
    proposal_by_strategy_id = {
        strategy.strategy_id: proposal_id
        for proposal_id, strategies in variants_by_proposal.items()
        for strategy in strategies
    }
    if len({strategy.strategy_id for strategy in variants}) != len(variants):
        raise ValueError("generated strategy identities must be campaign-unique")
    _stage(
        experiment_root,
        stage="VARIANTS_GENERATED",
        payload={"variant_count": len(variants)},
    )
    train_results = tuple(
        _checkpointed_evaluate(
            effective_backend,
            strategy,
            split.train_sessions,
            phase="train",
            dataset_id=dataset_id,
            experiment_root=experiment_root,
        )
        for strategy in variants
    )
    _stage(
        experiment_root,
        stage="TRAIN_COMPLETE",
        payload={"evaluated": len(train_results), "passed": sum(map(_passes_train, train_results))},
    )
    train_survivor_ids = {result.strategy_id for result in train_results if _passes_train(result)}
    train_survivors = tuple(
        strategy for strategy in variants if strategy.strategy_id in train_survivor_ids
    )
    if len(train_survivors) < 4:
        raise NoLongHorizonCandidateError("fewer than four variants passed training floors")
    train_by_id = {result.strategy_id: result for result in train_results}
    ranked_train = tuple(
        strategy
        for proposal in proposals
        for strategy in sorted(
            (
                item
                for item in train_survivors
                if proposal_by_strategy_id[item.strategy_id] == proposal.proposal_id
            ),
            key=lambda item: (
                -train_by_id[item.strategy_id].cost_1_5x_annualized_return,
                item.strategy_id,
            ),
        )[:4]
    )
    validation_results = tuple(
        _checkpointed_evaluate(
            effective_backend,
            strategy,
            split.validation_sessions,
            phase="validation",
            dataset_id=dataset_id,
            experiment_root=experiment_root,
        )
        for strategy in ranked_train
    )
    _stage(
        experiment_root,
        stage="VALIDATION_COMPLETE",
        payload={
            "evaluated": len(validation_results),
            "passed": sum(map(_passes_validation, validation_results)),
        },
    )
    passing_validation = tuple(
        result for result in validation_results if _passes_validation(result)
    )
    eligible_families: list[list[PhaseEvaluation]] = []
    for proposal in proposals:
        family = [
            result
            for result in passing_validation
            if proposal_by_strategy_id[result.strategy_id] == proposal.proposal_id
        ]
        family.sort(key=lambda result: (-result.cost_1_5x_annualized_return, result.strategy_id))
        if len(family) >= 4:
            eligible_families.append(family)
    if not eligible_families:
        raise NoLongHorizonCandidateError("fewer than four variants passed validation floors")
    eligible_families.sort(
        key=lambda family: (
            -family[0].cost_1_5x_annualized_return,
            family[0].strategy_id,
        )
    )
    selected_results = tuple(eligible_families[0][:4])
    if selected_results[0].cost_1_5x_annualized_return < 0.10:
        raise NoLongHorizonCandidateError(
            "best validation variant is below ten percent annualized after 1.5x costs"
        )
    winner_id = selected_results[0].strategy_id
    survivor_ids = tuple(sorted(result.strategy_id for result in selected_results))
    survivor_strategies = tuple(
        sorted(
            (strategy for strategy in variants if strategy.strategy_id in survivor_ids),
            key=lambda strategy: strategy.strategy_id,
        )
    )
    manifest_payload = {
        "dataset_id": dataset_id,
        "experiment_id": experiment_id,
        "proposal_ids": sorted(proposal.proposal_id for proposal in proposals),
        "split": split.model_dump(mode="json"),
        "survivor_ids": list(survivor_ids),
        "survivor_strategies": [item.model_dump(mode="json") for item in survivor_strategies],
        "validation_evaluations": [_phase_record(item) for item in selected_results],
        "winner_id": winner_id,
    }
    selection_sha256 = _sha256(manifest_payload)
    manifest = {**manifest_payload, "selection_sha256": selection_sha256}
    manifest_path = experiment_root / f"selection-{selection_sha256}.json"
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)
    _stage(
        experiment_root,
        stage="SELECTION_SEALED",
        payload={
            "selection_sha256": selection_sha256,
            "survivor_ids": list(survivor_ids),
            "winner_id": winner_id,
        },
    )
    return CampaignSelection(
        experiment_id=experiment_id,
        dataset_id=dataset_id,
        split=split,
        winner_id=winner_id,
        survivor_ids=survivor_ids,
        survivor_strategies=survivor_strategies,
        validation_evaluations=selected_results,
        selection_manifest=manifest_path,
        selection_sha256=selection_sha256,
    )


def finalize_long_horizon_campaign(
    selection: CampaignSelection,
    *,
    root: Path,
    backend: LongHorizonResearchBackend | None = None,
) -> CampaignFinalization:
    """Reserve, evaluate, and consume the final interval exactly once."""

    if type(selection) is not CampaignSelection:
        raise TypeError("selection must be an exact CampaignSelection")
    manifest = json.loads(selection.selection_manifest.read_text(encoding="utf-8"))
    retained_hash = manifest.pop("selection_sha256", None)
    if retained_hash != selection.selection_sha256 or _sha256(manifest) != retained_hash:
        raise ValueError("selection manifest content hash mismatch")
    ledger = CampaignFinalLedger(root.resolve() / "state" / "long_horizon_final.sqlite3")
    if ledger.is_consumed(dataset_id=selection.dataset_id, split_id=selection.split.split_id):
        raise FinalTestIsolationError("CAMPAIGN_FINAL_ALREADY_CONSUMED")
    token = ledger.reserve(
        dataset_id=selection.dataset_id,
        split_id=selection.split.split_id,
        survivor_ids=selection.survivor_ids,
    )
    experiment_root = selection.selection_manifest.parent
    _stage(
        experiment_root,
        stage="CAMPAIGN_FINAL_RESERVED",
        payload={"reservation_token": token, "selection_sha256": selection.selection_sha256},
    )
    effective_backend = backend or _default_backend(root, selection.dataset_id)
    final_result = effective_backend.evaluate(
        selection.winner_strategy,
        selection.split.final_test_sessions,
        phase="final_test",
    )
    validation = selection.winner_validation
    strategy_returns = validation.base_session_returns + final_result.base_session_returns
    stressed_returns = validation.cost_1_5x_session_returns + final_result.cost_1_5x_session_returns
    benchmark = effective_backend.benchmark_returns(
        selection.winner_strategy, validation.sessions
    ) + effective_backend.benchmark_returns(selection.winner_strategy, final_result.sessions)
    metrics = compute_long_horizon_oos_metrics(
        strategy_session_returns=strategy_returns,
        benchmark_session_returns=benchmark,
        cost_1_5x_session_returns=stressed_returns,
    )
    final_stage_hash = _stage(
        experiment_root,
        stage="FINAL_TEST_COMPLETE",
        payload={
            "final": _phase_record(final_result),
            "oos_metrics": asdict(metrics),
            "winner_id": selection.winner_id,
        },
    )
    evidence_sha256 = _sha256(
        {
            "final_stage_hash": final_stage_hash,
            "metrics": asdict(metrics),
            "selection_sha256": selection.selection_sha256,
        }
    )
    ledger.consume(
        token=token,
        proposal_id=selection.winner_id,
        evidence_sha256=evidence_sha256,
    )
    return CampaignFinalization(
        experiment_id=selection.experiment_id,
        dataset_id=selection.dataset_id,
        winner_id=selection.winner_id,
        final_consumed=True,
        final_evidence_sha256=evidence_sha256,
        oos_metrics=metrics,
    )


def _session_returns(
    equity_curve: tuple[EquityPoint, ...],
    *,
    initial_cash: float,
) -> tuple[float, ...]:
    ending: dict[date, float] = {}
    for point in equity_curve:
        ending[point.session] = point.equity
    previous = initial_cash
    returns: list[float] = []
    for session in sorted(ending):
        current = ending[session]
        returns.append(current / previous - 1.0)
        previous = current
    return tuple(returns)


def cost_adjusted_trade_session_returns(
    trades: tuple[TradeRecord, ...],
    sessions: tuple[date, ...],
    *,
    initial_cash: float,
    cost_multiplier: float,
) -> tuple[float, ...]:
    evidence = {session: [0.0, 0.0] for session in sessions}
    for trade in trades:
        if trade.session not in evidence:
            raise ValueError("trade falls outside requested phase sessions")
        evidence[trade.session][0] += trade.gross_pnl
        evidence[trade.session][1] += trade.cost_paid
    equity = initial_cash
    returns: list[float] = []
    for session in sessions:
        gross_pnl, base_cost = evidence[session]
        pnl = gross_pnl - cost_multiplier * base_cost
        returns.append(pnl / equity)
        equity += pnl
    return tuple(returns)


def matched_benchmark_session_returns(
    trades: tuple[TradeRecord, ...],
    benchmark_bars: pd.DataFrame,
    sessions: tuple[date, ...],
    *,
    initial_cash: float,
) -> tuple[float, ...]:
    """Match benchmark exposure to each strategy trade's time and cash notional."""

    if initial_cash <= 0.0 or not math.isfinite(initial_cash):
        raise ValueError("initial_cash must be finite and positive")
    required = {"session_date", "available_at", "open", "close"}
    if missing := sorted(required.difference(benchmark_bars.columns)):
        raise ValueError("benchmark bars lack required columns: " + ",".join(missing))
    bars = benchmark_bars.loc[:, sorted(required)].copy()
    bars["available_at"] = pd.to_datetime(bars["available_at"], utc=True)
    if bars.duplicated(["session_date", "available_at"]).any():
        raise ValueError("benchmark bars must be unique by session and availability")
    observed_sessions = tuple(sorted(bars["session_date"].unique()))
    if observed_sessions != sessions:
        raise ValueError("benchmark does not exactly cover requested sessions")
    by_time = bars.set_index(["session_date", "available_at"])
    pnl_by_session = {session: 0.0 for session in sessions}
    for trade in trades:
        if trade.session not in pnl_by_session:
            raise ValueError("trade falls outside requested benchmark sessions")
        entry_key = (trade.session, pd.Timestamp(trade.entry_time))
        exit_key = (trade.session, pd.Timestamp(trade.exit_time))
        try:
            entry_row = by_time.loc[entry_key]
            exit_row = by_time.loc[exit_key]
        except KeyError as exc:
            raise ValueError("benchmark lacks a strategy trade timestamp") from exc
        benchmark_entry = float(entry_row["open"])
        benchmark_exit = float(exit_row["close"] if trade.forced else exit_row["open"])
        if min(benchmark_entry, benchmark_exit) <= 0.0:
            raise ValueError("benchmark prices must be positive")
        strategy_notional = trade.entry_price * trade.quantity
        pnl_by_session[trade.session] += strategy_notional * (
            benchmark_exit / benchmark_entry - 1.0
        )
    equity = initial_cash
    returns: list[float] = []
    for session in sessions:
        pnl = pnl_by_session[session]
        returns.append(pnl / equity)
        equity += pnl
        if equity <= 0.0:
            raise ValueError("matched benchmark equity must remain positive")
    return tuple(returns)


class LocalFiveMinuteResearchBackend:
    """Project-owned adapter from immutable bars to the conservative engine."""

    def __init__(self, *, root: Path, dataset_id: str) -> None:
        self.root = root.resolve()
        self.dataset_id = dataset_id
        self._hf_store: HfFiveMinuteSnapshotStore | None = None
        self._legacy_bars: pd.DataFrame | None = None
        self._phase_bars: dict[tuple[date, ...], pd.DataFrame] = {}
        self._runs: dict[tuple[str, tuple[date, ...]], EngineRun] = {}
        if dataset_id.startswith("hf-finnhub-5min-"):
            self._hf_store = HfFiveMinuteSnapshotStore(root=self.root, dataset_id=dataset_id)
            observed_order = self._hf_store.symbols
        else:
            self._legacy_bars = read_five_minute_snapshot(dataset_id, root=self.root)
            observed = set(self._legacy_bars["symbol"].astype(str))
            matching_scope = next(
                (scope for scope in FIVE_MINUTE_SYMBOL_SCOPES if set(scope) == observed),
                None,
            )
            if matching_scope is None:
                raise ValueError("backend dataset uses an unsupported symbol scope")
            observed_order = matching_scope
        if observed_order not in FIVE_MINUTE_SYMBOL_SCOPES:
            raise ValueError("backend dataset uses an unsupported symbol scope")
        self.symbols = observed_order

    def accepted_sessions(self, dataset_id: str) -> tuple[date, ...]:
        if dataset_id != self.dataset_id:
            raise ValueError("backend dataset identity mismatch")
        if self._hf_store is not None:
            return self._hf_store.accepted_sessions
        if self._legacy_bars is None:
            raise RuntimeError("backend has no data store")
        return tuple(sorted(self._legacy_bars["session_date"].unique()))

    def _read_sessions(self, sessions: tuple[date, ...]) -> pd.DataFrame:
        cached = self._phase_bars.get(sessions)
        if cached is not None:
            return cached
        if self._hf_store is not None:
            selected = self._hf_store.read_sessions(sessions)
        else:
            if self._legacy_bars is None:
                raise RuntimeError("backend has no data store")
            selected = self._legacy_bars.loc[
                self._legacy_bars["session_date"].isin(sessions)
            ].copy()
        selected["available_at"] = pd.to_datetime(selected["timestamp"], utc=True) + pd.Timedelta(
            minutes=5
        )
        self._phase_bars[sessions] = selected
        return selected

    def _run_strategy(
        self,
        strategy: StrategyDefinition,
        sessions: tuple[date, ...],
    ) -> EngineRun:
        if strategy.symbols != self.symbols:
            raise ValueError("strategy symbol scope does not match backend dataset")
        compiled = compile_strategy(strategy)
        cache_key = (compiled.definition_fingerprint, sessions)
        cached = self._runs.get(cache_key)
        if cached is not None:
            return cached
        selected = self._read_sessions(sessions)
        if tuple(sorted(selected["session_date"].unique())) != sessions:
            raise ValueError("backend phase does not exactly cover requested sessions")
        job = BacktestJob.create(
            schema_version="1.0.0",
            strategy_id=compiled.definition_fingerprint,
            dataset_id=self.dataset_id,
            engine_id=FIVE_MINUTE_ENGINE_ID,
            calendar_id="XNYS@long-horizon-v1",
            input_data_sha256=five_minute_input_sha256(selected),
            initial_cash=100_000.0,
            closeout_buffer_minutes=5,
            cost_model_ids=CostModelIds(
                **{
                    scenario: COST_SCENARIOS[scenario].model_id
                    for scenario in ("optimistic", "base", "stress")
                }
            ),
        )
        run = FiveMinuteBacktestEngine(job=job, strategy=compiled).run(bars_5m=selected)
        self._runs[cache_key] = run
        return run

    def evaluate(
        self,
        strategy: StrategyDefinition,
        sessions: tuple[date, ...],
        *,
        phase: str,
    ) -> PhaseEvaluation:
        del phase
        run = self._run_strategy(strategy, sessions)
        base = run.scenarios["base"]
        stress = run.scenarios["stress"]
        pnl_by_symbol = {
            symbol: math.fsum(trade.net_pnl for trade in base.trades if trade.symbol == symbol)
            for symbol in self.symbols
        }
        return PhaseEvaluation(
            strategy_id=strategy.strategy_id,
            sessions=sessions,
            base_session_returns=_session_returns(
                base.equity_curve, initial_cash=base.initial_cash
            ),
            stress_session_returns=_session_returns(
                stress.equity_curve, initial_cash=stress.initial_cash
            ),
            cost_1_5x_session_returns=cost_adjusted_trade_session_returns(
                base.trades,
                sessions,
                initial_cash=base.initial_cash,
                cost_multiplier=1.5,
            ),
            closed_trades=len(base.trades),
            max_drawdown=base.metrics["max_drawdown"],
            profit_factor=base.metrics["profit_factor"],
            pnl_by_symbol=pnl_by_symbol,
        )

    def benchmark_returns(
        self,
        strategy: StrategyDefinition,
        sessions: tuple[date, ...],
    ) -> tuple[float, ...]:
        benchmark_symbol = {
            ("AAPL", "QQQ"): "QQQ",
            ("SPY", "IWM"): "SPY",
            ("SPY", "TQQQ"): "SPY",
            ("TQQQ", "UPRO"): "UPRO",
            ("TQQQ", "SOXL"): "TQQQ",
        }[self.symbols]
        bars = self._read_sessions(sessions)
        benchmark_bars = bars.loc[bars["symbol"] == benchmark_symbol].sort_values(
            ["session_date", "available_at"], kind="stable"
        )
        trades = self._run_strategy(strategy, sessions).scenarios["base"].trades
        return matched_benchmark_session_returns(
            trades,
            benchmark_bars,
            sessions,
            initial_cash=100_000.0,
        )
