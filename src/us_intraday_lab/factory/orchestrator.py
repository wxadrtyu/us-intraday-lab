"""Resumable, hash-chained orchestration for one gated strategy research run."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from us_intraday_lab.contracts.backtests import CostScenario
from us_intraday_lab.contracts.hypotheses import (
    HypothesisProposal,
    ParameterName,
    ParameterValue,
)
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.contracts.validation import (
    GateResult,
    ValidationDecision,
    WalkForwardWindowResult,
)
from us_intraday_lab.factory.experiments import ExperimentManifest, create_experiment_manifest
from us_intraday_lab.factory.variants import GeneratedVariant, generate_strategy_variants
from us_intraday_lab.registry.store import RegistryStore
from us_intraday_lab.validation.gates import (
    HARD_GATE_REASON_CODES,
    CandidateGateEvidence,
    HardGateEvaluation,
    evaluate_hard_gates,
)
from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullDistribution,
    NullSequenceScore,
    NullTestResult,
)
from us_intraday_lab.validation.ranking import RankedCandidate, RankingEvidence, rank_survivors
from us_intraday_lab.validation.splits import (
    IsolatedChronologicalViews,
    create_chronological_split,
)
from us_intraday_lab.validation.stability import (
    ParameterNeighborhoodConfig,
    PerturbationObservation,
    StartDateConfig,
    StartDateObservation,
    assess_parameter_neighborhood,
    assess_start_date_sensitivity,
    assess_symbol_concentration,
)

ResearchPhase = Literal["train", "validation", "final_test"]
ResearchStage = Literal[
    "PROPOSAL_ACCEPTED",
    "VARIANTS_GENERATED",
    "TRAIN_COMPLETE",
    "VALIDATION_COMPLETE",
    "SELECTION_SEALED",
    "FINAL_TEST_COMPLETE",
    "GATES_COMPLETE",
    "REGISTRY_COMPLETE",
    "REPORT_COMPLETE",
]
RESEARCH_STAGES: tuple[ResearchStage, ...] = (
    "PROPOSAL_ACCEPTED",
    "VARIANTS_GENERATED",
    "TRAIN_COMPLETE",
    "VALIDATION_COMPLETE",
    "SELECTION_SEALED",
    "FINAL_TEST_COMPLETE",
    "GATES_COMPLETE",
    "REGISTRY_COMPLETE",
    "REPORT_COMPLETE",
)
MAX_STAGE_BYTES = 100_000_000
_SCENARIOS: tuple[CostScenario, ...] = ("optimistic", "base", "stress")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class AcceptedResearchDataset(_ClosedModel):
    dataset_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calendar_name: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    sessions: tuple[date, ...] = Field(min_length=10, max_length=100_000)
    accepted_at: datetime

    @field_validator("accepted_at")
    @classmethod
    def validate_accepted_at(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("accepted_at must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_sessions(self) -> AcceptedResearchDataset:
        if tuple(sorted(self.sessions)) != self.sessions or len(set(self.sessions)) != len(
            self.sessions
        ):
            raise ValueError("dataset sessions must be sorted and unique")
        return self


class PhaseEvidence(_ClosedModel):
    strategy_id: str = Field(min_length=1)
    phase: ResearchPhase
    job_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_by_cost_scenario: Mapping[CostScenario, Mapping[str, float]]
    cost_1_5x_net_return: float
    profit_by_symbol: Mapping[str, float]
    session_net_returns: Mapping[str, float]
    source_refs: tuple[str, ...] = Field(min_length=1)
    null_evidence: NullEvidenceSummary | None = None

    @model_validator(mode="after")
    def validate_complete_metrics(self) -> PhaseEvidence:
        if set(self.metrics_by_cost_scenario) != set(_SCENARIOS):
            raise ValueError("phase evidence requires all three cost scenarios")
        required = {"net_return", "max_drawdown", "profit_factor", "trade_count"}
        for scenario in _SCENARIOS:
            metrics = self.metrics_by_cost_scenario[scenario]
            if not required <= set(metrics):
                raise ValueError("phase evidence lacks required metrics")
            if any(
                type(value) not in {int, float} or not math.isfinite(value)
                for value in metrics.values()
            ):
                raise ValueError("phase metrics must be exact finite numbers")
        if set(self.profit_by_symbol) != {"SPY", "QQQ", "IWM"}:
            raise ValueError("profit_by_symbol must contain SPY, QQQ, and IWM")
        if not self.session_net_returns:
            raise ValueError("session_net_returns must not be empty")
        return self


class RobustnessPoint(_ClosedModel):
    observation_id: str = Field(min_length=1)
    net_return: float
    max_drawdown: float = Field(ge=0.0, le=1.0)


class StartDatePoint(_ClosedModel):
    offset_sessions: int = Field(strict=True)
    net_return: float
    max_drawdown: float = Field(ge=0.0, le=1.0)


class NullEvidenceSummary(_ClosedModel):
    passed: bool = Field(strict=True)
    seed: int = Field(strict=True, ge=0, le=2**64 - 1)
    repetitions: int = Field(strict=True, ge=1, le=10_000)
    percentile: float = Field(gt=0.0, lt=1.0)
    observed_profit: float
    permutation_threshold: float
    timestamp_shift_threshold: float
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_opportunity_ids: tuple[str, ...] = Field(min_length=1)
    trade_count_by_symbol_session: Mapping[str, int]
    permutation_statistics: tuple[float, ...] = Field(min_length=1, max_length=10_000)
    permutation_accepted_entry_counts: tuple[int, ...] = Field(min_length=1, max_length=10_000)
    permutation_rejected_entry_counts: tuple[int, ...] = Field(min_length=1, max_length=10_000)
    timestamp_shift_statistics: tuple[float, ...] = Field(min_length=1, max_length=10_000)
    timestamp_shift_accepted_entry_counts: tuple[int, ...] = Field(min_length=1, max_length=10_000)
    timestamp_shift_rejected_entry_counts: tuple[int, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_result(self) -> NullEvidenceSummary:
        derived = self.observed_profit > self.permutation_threshold and self.observed_profit > (
            self.timestamp_shift_threshold
        )
        if derived != self.passed:
            raise ValueError("null passed flag must agree with both thresholds")
        covered = {
            symbol
            for key in self.trade_count_by_symbol_session
            for symbol in ("SPY", "QQQ", "IWM")
            if key.endswith(f":{symbol}")
        }
        if covered != {"SPY", "QQQ", "IWM"}:
            raise ValueError("null evidence must cover SPY, QQQ, and IWM")
        sequences = (
            self.permutation_statistics,
            self.permutation_accepted_entry_counts,
            self.permutation_rejected_entry_counts,
            self.timestamp_shift_statistics,
            self.timestamp_shift_accepted_entry_counts,
            self.timestamp_shift_rejected_entry_counts,
        )
        if any(len(sequence) != self.repetitions for sequence in sequences):
            raise ValueError("null distributions must exactly match repetitions")
        return self


PhaseEvidence.model_rebuild()


class RobustnessEvidence(_ClosedModel):
    strategy_id: str = Field(min_length=1)
    walk_forward_net_returns: tuple[float, ...] = Field(min_length=1, max_length=10_000)
    parameter_points: tuple[RobustnessPoint, ...] = Field(min_length=2, max_length=200)
    start_date_points: tuple[StartDatePoint, ...] = Field(min_length=2, max_length=200)
    null_evidence: NullEvidenceSummary
    source_refs: tuple[str, ...] = Field(min_length=1)


class ResearchBackend(Protocol):
    def run_phase(
        self,
        *,
        variant: GeneratedVariant,
        phase: str,
        sessions: tuple[date, ...],
        experiment_id: str,
    ) -> PhaseEvidence: ...

    def robustness_evidence(
        self,
        *,
        variant: GeneratedVariant,
        validation_results: tuple[PhaseEvidence, ...],
        experiment_id: str,
    ) -> RobustnessEvidence: ...


class ResearchIntegrityError(RuntimeError):
    """Raised when resumable artifacts no longer match their immutable hashes."""


@dataclass(frozen=True, slots=True)
class ResearchRunSummary:
    experiment_id: str
    completed_stages: tuple[ResearchStage, ...]
    variant_count: int
    final_test_strategy_ids: tuple[str, ...]
    survivor_ids: tuple[str, ...]
    rejected_count: int
    gate_result_counts: Mapping[str, int]
    run_directory: Path
    registry_path: Path
    report_path: Path


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class _StageStore:
    def __init__(self, *, root: Path, experiment_id: str) -> None:
        if re.fullmatch(r"experiment-[0-9a-f]{64}", experiment_id) is None:
            raise ValueError("experiment_id must be a canonical experiment identifier")
        self.run_directory = root / "artifacts" / "research" / experiment_id
        self.stage_directory = self.run_directory / "stages"
        self.stage_directory.mkdir(parents=True, exist_ok=True)
        self.experiment_id = experiment_id

    def path_for(self, stage: ResearchStage) -> Path:
        index = RESEARCH_STAGES.index(stage) + 1
        return self.stage_directory / f"{index:02d}_{stage}.json"

    def load_all(self) -> dict[ResearchStage, dict[str, Any]]:
        loaded: dict[ResearchStage, dict[str, Any]] = {}
        previous_hash: str | None = None
        missing_seen = False
        for stage in RESEARCH_STAGES:
            path = self.path_for(stage)
            if not path.exists():
                missing_seen = True
                continue
            if missing_seen:
                raise ResearchIntegrityError("STAGE_SEQUENCE_GAP")
            raw = path.read_bytes()
            if len(raw) > MAX_STAGE_BYTES:
                raise ResearchIntegrityError("STAGE_SIZE_EXCEEDED")
            try:
                envelope = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ResearchIntegrityError("STAGE_JSON_INVALID") from error
            if type(envelope) is not dict:
                raise ResearchIntegrityError("STAGE_ENVELOPE_INVALID")
            expected_keys = {
                "schema_version",
                "experiment_id",
                "stage",
                "previous_stage_sha256",
                "payload",
                "stage_sha256",
            }
            if set(envelope) != expected_keys:
                raise ResearchIntegrityError("STAGE_ENVELOPE_INVALID")
            signed = {key: value for key, value in envelope.items() if key != "stage_sha256"}
            if (
                envelope["schema_version"] != "1.0.0"
                or envelope["experiment_id"] != self.experiment_id
                or envelope["stage"] != stage
                or envelope["previous_stage_sha256"] != previous_hash
                or envelope["stage_sha256"] != _sha256_json(signed)
            ):
                raise ResearchIntegrityError("STAGE_HASH_MISMATCH")
            payload = envelope["payload"]
            if type(payload) is not dict:
                raise ResearchIntegrityError("STAGE_PAYLOAD_INVALID")
            loaded[stage] = cast(dict[str, Any], payload)
            previous_hash = cast(str, envelope["stage_sha256"])
        return loaded

    def write(
        self,
        stage: ResearchStage,
        payload: dict[str, Any],
        *,
        loaded: Mapping[ResearchStage, dict[str, Any]],
    ) -> None:
        expected_index = len(loaded)
        if RESEARCH_STAGES[expected_index] != stage:
            raise ResearchIntegrityError("STAGE_SEQUENCE_INVALID")
        previous_hash: str | None = None
        if expected_index:
            previous_path = self.path_for(RESEARCH_STAGES[expected_index - 1])
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            previous_hash = cast(str, previous["stage_sha256"])
        signed = {
            "schema_version": "1.0.0",
            "experiment_id": self.experiment_id,
            "stage": stage,
            "previous_stage_sha256": previous_hash,
            "payload": payload,
        }
        envelope = {**signed, "stage_sha256": _sha256_json(signed)}
        content = (_canonical_json(envelope) + "\n").encode("utf-8")
        if len(content) > MAX_STAGE_BYTES:
            raise ResearchIntegrityError("STAGE_SIZE_EXCEEDED")
        temporary: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{stage}-",
                suffix=".tmp",
                dir=self.stage_directory,
            )
            temporary = Path(raw_path)
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, self.path_for(stage))
            except FileExistsError as error:
                raise ResearchIntegrityError("STAGE_CONCURRENT_WRITE") from error
            temporary.unlink()
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _variant_payload(variant: GeneratedVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "content_sha256": variant.content_sha256,
        "selection_reason": variant.selection_reason,
        "parameters": dict(variant.parameters),
        "definition": variant.definition.model_dump(mode="json"),
    }


def _variant_from_payload(payload: Mapping[str, Any]) -> GeneratedVariant:
    definition = StrategyDefinition.model_validate(payload["definition"])
    variant_id = cast(str, payload["variant_id"])
    content_sha256 = cast(str, payload["content_sha256"])
    if definition.strategy_id != variant_id:
        raise ResearchIntegrityError("VARIANT_IDENTITY_MISMATCH")
    derived_hash = hashlib.sha256(
        _canonical_json(definition.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    if derived_hash != content_sha256:
        raise ResearchIntegrityError("VARIANT_CONTENT_HASH_MISMATCH")
    return GeneratedVariant(
        variant_id=variant_id,
        content_sha256=content_sha256,
        selection_reason=cast(Any, payload["selection_reason"]),
        parameters=MappingProxyType(
            cast(dict[ParameterName, ParameterValue], dict(payload["parameters"]))
        ),
        definition=definition,
    )


def _ensure_stage(
    store: _StageStore,
    loaded: dict[ResearchStage, dict[str, Any]],
    stage: ResearchStage,
    producer: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if stage in loaded:
        return loaded[stage]
    payload = producer()
    store.write(stage, payload, loaded=loaded)
    loaded[stage] = payload
    return payload


def _split_for(dataset: AcceptedResearchDataset) -> Any:
    split_id = (
        "split-"
        + _sha256_json(
            {
                "dataset_id": dataset.dataset_id,
                "sessions": [item.isoformat() for item in dataset.sessions],
            }
        )[:16]
    )
    return create_chronological_split(dataset.sessions, split_id=split_id)


def _manifest_for(
    *,
    proposal: HypothesisProposal,
    dataset: AcceptedResearchDataset,
    code_revision: str,
) -> ExperimentManifest:
    return create_experiment_manifest(
        proposal=proposal,
        dataset_id=dataset.dataset_id,
        calendar_version=f"{dataset.calendar_name}@{dataset.calendar_version}",
        split_definition=_split_for(dataset),
        code_revision=code_revision,
        created_at=dataset.accepted_at,
    )


def run_research(
    *,
    proposal: HypothesisProposal,
    dataset: AcceptedResearchDataset,
    backend: ResearchBackend,
    root: Path,
    code_revision: str,
) -> ResearchRunSummary:
    if type(proposal) is not HypothesisProposal:
        raise TypeError("proposal must be an exact HypothesisProposal")
    retained_proposal = HypothesisProposal.model_validate(proposal)
    retained_dataset = AcceptedResearchDataset.model_validate(dataset)
    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    manifest = _manifest_for(
        proposal=retained_proposal,
        dataset=retained_dataset,
        code_revision=code_revision,
    )
    store = _StageStore(root=root.resolve(), experiment_id=manifest.experiment_id)
    loaded = store.load_all()
    proposal_payload = {
        "proposal": retained_proposal.model_dump(mode="json"),
        "dataset": retained_dataset.model_dump(mode="json"),
        "manifest": manifest.model_dump(mode="json"),
    }
    if "PROPOSAL_ACCEPTED" in loaded and loaded["PROPOSAL_ACCEPTED"] != proposal_payload:
        raise ResearchIntegrityError("EXPERIMENT_INPUT_MISMATCH")
    _ensure_stage(
        store,
        loaded,
        "PROPOSAL_ACCEPTED",
        lambda: proposal_payload,
    )
    return _execute(
        proposal=retained_proposal,
        dataset=retained_dataset,
        manifest=manifest,
        backend=backend,
        root=root.resolve(),
        store=store,
        loaded=loaded,
    )


def resume_research(
    *,
    experiment_id: str,
    backend: ResearchBackend,
    root: Path,
    code_revision: str,
) -> ResearchRunSummary:
    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    store = _StageStore(root=root.resolve(), experiment_id=experiment_id)
    loaded = store.load_all()
    if "PROPOSAL_ACCEPTED" not in loaded:
        raise ResearchIntegrityError("PROPOSAL_STAGE_MISSING")
    first = loaded["PROPOSAL_ACCEPTED"]
    proposal = HypothesisProposal.model_validate(first["proposal"])
    dataset = AcceptedResearchDataset.model_validate(first["dataset"])
    manifest = ExperimentManifest.model_validate(first["manifest"])
    if manifest.experiment_id != experiment_id:
        raise ResearchIntegrityError("EXPERIMENT_INPUT_MISMATCH")
    if len(loaded) < len(RESEARCH_STAGES) and code_revision != manifest.code_revision:
        raise ResearchIntegrityError("CODE_REVISION_MISMATCH")
    return _execute(
        proposal=proposal,
        dataset=dataset,
        manifest=manifest,
        backend=backend,
        root=root.resolve(),
        store=store,
        loaded=loaded,
    )


def _phase_items(payload: Mapping[str, Any]) -> tuple[PhaseEvidence, ...]:
    return tuple(PhaseEvidence.model_validate(item) for item in payload["items"])


def _preselected(validation: tuple[PhaseEvidence, ...]) -> tuple[str, ...]:
    survivors = []
    for item in validation:
        base = item.metrics_by_cost_scenario["base"]
        if (
            base["net_return"] > 0.0
            and item.cost_1_5x_net_return > 0.0
            and base["trade_count"] >= 100.0
            and base["max_drawdown"] <= 0.08
            and base["profit_factor"] >= 1.15
        ):
            survivors.append(item.strategy_id)
    return tuple(sorted(survivors))


def _walk_forward_results(
    *,
    strategy_id: str,
    returns: tuple[float, ...],
    manifest: ExperimentManifest,
) -> tuple[WalkForwardWindowResult, ...]:
    split = manifest.split_definition
    return tuple(
        WalkForwardWindowResult(
            window_id=f"{strategy_id}:wf:{index}",
            strategy_id=strategy_id,
            train_start=split.train_sessions[0],
            train_end=split.train_sessions[-1],
            validation_start=split.validation_sessions[index % len(split.validation_sessions)],
            validation_end=split.validation_sessions[index % len(split.validation_sessions)],
            metrics_by_cost_scenario={"base": {"net_return": value}},
        )
        for index, value in enumerate(returns)
    )


def _null_result(summary: NullEvidenceSummary, variant: GeneratedVariant) -> NullTestResult:
    accepted = sum(summary.trade_count_by_symbol_session.values())
    distributions = (
        NullDistribution(
            method="SESSION_SIGNAL_PERMUTATION",
            statistics=summary.permutation_statistics,
            accepted_entry_counts=summary.permutation_accepted_entry_counts,
            rejected_entry_counts=summary.permutation_rejected_entry_counts,
            percentile_threshold=summary.permutation_threshold,
        ),
        NullDistribution(
            method="SESSION_SAFE_TIMESTAMP_SHIFT",
            statistics=summary.timestamp_shift_statistics,
            accepted_entry_counts=summary.timestamp_shift_accepted_entry_counts,
            rejected_entry_counts=summary.timestamp_shift_rejected_entry_counts,
            percentile_threshold=summary.timestamp_shift_threshold,
        ),
    )
    return NullTestResult(
        passed=summary.passed,
        reason_code="PASSED_NULL_TEST" if summary.passed else "NULL_TEST_FAILED",
        observed_score=NullSequenceScore(summary.observed_profit, accepted, 0),
        seed=summary.seed,
        repetitions=summary.repetitions,
        percentile=summary.percentile,
        evidence_sha256=summary.evidence_sha256,
        evidence_opportunity_ids=summary.evidence_opportunity_ids,
        scoring_config=HoldingRuleScoringConfig(
            scoring_id=f"{variant.variant_id}:holding-rule",
            rule_version="strategy-dsl-1.0.0",
            cost_model_id="cost-base-1.0.0",
            cooldown_minutes=variant.definition.risk.cooldown_minutes,
            max_entries_per_session=variant.definition.risk.max_entries_per_session,
            max_concurrent_positions=3,
        ),
        framework_operation_bound=1,
        distributions=distributions,
        trade_count_by_symbol_session=summary.trade_count_by_symbol_session,
    )


def _gate_input(
    *,
    variant: GeneratedVariant,
    phase: PhaseEvidence,
    robustness: RobustnessEvidence,
    manifest: ExperimentManifest,
) -> CandidateGateEvidence:
    parameter_observations = tuple(
        PerturbationObservation(point.observation_id, point.net_return, point.max_drawdown)
        for point in robustness.parameter_points
    )
    start_observations = tuple(
        StartDateObservation(point.offset_sessions, point.net_return, point.max_drawdown)
        for point in robustness.start_date_points
    )
    base = phase.metrics_by_cost_scenario["base"]
    return CandidateGateEvidence(
        strategy_id=variant.variant_id,
        split_id=manifest.split_definition.split_id,
        source_refs=tuple(dict.fromkeys((*phase.source_refs, *robustness.source_refs))),
        base_net_return=base["net_return"],
        cost_1_5x_net_return=phase.cost_1_5x_net_return,
        closed_trades=int(base["trade_count"]),
        max_drawdown=base["max_drawdown"],
        profit_factor=base["profit_factor"],
        walk_forward_results=_walk_forward_results(
            strategy_id=variant.variant_id,
            returns=robustness.walk_forward_net_returns,
            manifest=manifest,
        ),
        parameter_neighborhood=assess_parameter_neighborhood(
            parameter_observations,
            config=ParameterNeighborhoodConfig(
                baseline_id=variant.variant_id,
                neighbor_ids=tuple(item.observation_id for item in parameter_observations),
            ),
        ),
        symbol_concentration=assess_symbol_concentration(phase.profit_by_symbol),
        start_date_stability=assess_start_date_sensitivity(
            start_observations,
            config=StartDateConfig(
                offsets=tuple(item.offset_sessions for item in start_observations)
            ),
        ),
        null_test=_null_result(robustness.null_evidence, variant),
    )


def _decision_id(experiment_id: str, strategy_id: str, gates: list[dict[str, Any]]) -> str:
    return "decision-" + _sha256_json(
        {
            "experiment_id": experiment_id,
            "gate_results": gates,
            "strategy_id": strategy_id,
        }
    )


def _execute(
    *,
    proposal: HypothesisProposal,
    dataset: AcceptedResearchDataset,
    manifest: ExperimentManifest,
    backend: ResearchBackend,
    root: Path,
    store: _StageStore,
    loaded: dict[ResearchStage, dict[str, Any]],
) -> ResearchRunSummary:
    import pandas as pd

    variants_payload = _ensure_stage(
        store,
        loaded,
        "VARIANTS_GENERATED",
        lambda: {
            "variants": [_variant_payload(item) for item in generate_strategy_variants(proposal)]
        },
    )
    variants = tuple(_variant_from_payload(item) for item in variants_payload["variants"])
    split = manifest.split_definition
    isolated_views = IsolatedChronologicalViews(
        pd.DataFrame({"session_date": dataset.sessions}),
        split,
    )

    train_payload = _ensure_stage(
        store,
        loaded,
        "TRAIN_COMPLETE",
        lambda: {
            "items": [
                backend.run_phase(
                    variant=variant,
                    phase="train",
                    sessions=split.train_sessions,
                    experiment_id=manifest.experiment_id,
                ).model_dump(mode="json")
                for variant in variants
            ]
        },
    )
    train = _phase_items(train_payload)
    if tuple(item.strategy_id for item in train) != tuple(
        item.variant_id for item in variants
    ) or any(item.phase != "train" for item in train):
        raise ResearchIntegrityError("TRAIN_STRATEGY_ORDER_MISMATCH")
    train_view = isolated_views.training_view()
    if tuple(train_view["session_date"]) != split.train_sessions:
        raise ResearchIntegrityError("TRAIN_SESSION_ISOLATION_MISMATCH")
    validation_payload = _ensure_stage(
        store,
        loaded,
        "VALIDATION_COMPLETE",
        lambda: {
            "items": [
                backend.run_phase(
                    variant=variant,
                    phase="validation",
                    sessions=split.validation_sessions,
                    experiment_id=manifest.experiment_id,
                ).model_dump(mode="json")
                for variant in variants
            ]
        },
    )
    validation = _phase_items(validation_payload)
    if tuple(item.strategy_id for item in validation) != tuple(
        item.variant_id for item in variants
    ) or any(item.phase != "validation" for item in validation):
        raise ResearchIntegrityError("VALIDATION_STRATEGY_ORDER_MISMATCH")
    validation_view = isolated_views.validation_view()
    if tuple(validation_view["session_date"]) != split.validation_sessions:
        raise ResearchIntegrityError("VALIDATION_SESSION_ISOLATION_MISMATCH")

    def selection_payload() -> dict[str, Any]:
        survivor_ids = _preselected(validation)
        selection_hash = _sha256_json(
            {
                "experiment_id": manifest.experiment_id,
                "result_hashes": [item.result_sha256 for item in validation],
                "survivor_ids": survivor_ids,
            }
        )
        return {
            "survivor_ids": list(survivor_ids),
            "selection_manifest_sha256": selection_hash,
        }

    selection = _ensure_stage(
        store,
        loaded,
        "SELECTION_SEALED",
        selection_payload,
    )
    final_ids = tuple(cast(list[str], selection["survivor_ids"]))
    expected_final_ids = _preselected(validation)
    expected_selection_hash = _sha256_json(
        {
            "experiment_id": manifest.experiment_id,
            "result_hashes": [item.result_sha256 for item in validation],
            "survivor_ids": expected_final_ids,
        }
    )
    if (
        final_ids != expected_final_ids
        or selection.get("selection_manifest_sha256") != expected_selection_hash
    ):
        raise ResearchIntegrityError("SELECTION_MANIFEST_MISMATCH")
    if final_ids:
        final_evaluator = isolated_views.seal_selection(
            survivor_ids=final_ids,
            selection_manifest_sha256=expected_selection_hash,
        )
        final_view = final_evaluator.final_test_view(strategy_ids=final_ids)
        authorized_final_sessions = tuple(final_view["session_date"])
        if authorized_final_sessions != split.final_test_sessions:
            raise ResearchIntegrityError("FINAL_TEST_SESSION_ISOLATION_MISMATCH")
    else:
        authorized_final_sessions = ()
    by_variant = {item.variant_id: item for item in variants}
    final_payload = _ensure_stage(
        store,
        loaded,
        "FINAL_TEST_COMPLETE",
        lambda: {
            "items": [
                backend.run_phase(
                    variant=by_variant[strategy_id],
                    phase="final_test",
                    sessions=authorized_final_sessions,
                    experiment_id=manifest.experiment_id,
                ).model_dump(mode="json")
                for strategy_id in final_ids
            ]
        },
    )
    final_results = _phase_items(final_payload)
    if tuple(item.strategy_id for item in final_results) != final_ids or any(
        item.phase != "final_test" for item in final_results
    ):
        raise ResearchIntegrityError("FINAL_TEST_SELECTION_MISMATCH")

    def gates_payload() -> dict[str, Any]:
        validation_by_id = {item.strategy_id: item for item in validation}
        final_by_id = {item.strategy_id: item for item in final_results}
        evaluations: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        robustness_rows: list[dict[str, Any]] = []
        passing_ranking_inputs: list[RankingEvidence] = []
        for variant in variants:
            robustness = backend.robustness_evidence(
                variant=variant,
                validation_results=validation,
                experiment_id=manifest.experiment_id,
            )
            if robustness.strategy_id != variant.variant_id:
                raise ResearchIntegrityError("ROBUSTNESS_STRATEGY_MISMATCH")
            robustness_rows.append(robustness.model_dump(mode="json"))
            phase = final_by_id.get(variant.variant_id, validation_by_id[variant.variant_id])
            evaluation = evaluate_hard_gates(
                _gate_input(
                    variant=variant,
                    phase=phase,
                    robustness=robustness,
                    manifest=manifest,
                )
            )
            gate_rows = [item.model_dump(mode="json") for item in evaluation.gate_results]
            evaluation_row = {
                "strategy_id": variant.variant_id,
                "split_id": evaluation.split_id,
                "passed": evaluation.passed,
                "failure_reason_codes": list(evaluation.failure_reason_codes),
                "gate_results": gate_rows,
            }
            evaluations.append(evaluation_row)
            decision = ValidationDecision(
                decision_id=_decision_id(
                    manifest.experiment_id,
                    variant.variant_id,
                    gate_rows,
                ),
                strategy_id=variant.variant_id,
                split_id=evaluation.split_id,
                decision="PROMOTE_TO_PAPER_SHADOW" if evaluation.passed else "REJECT",
                gate_results=evaluation.gate_results,
                decided_at=dataset.accepted_at,
            )
            decisions.append(decision.model_dump(mode="json"))
            if evaluation.passed:
                if variant.variant_id not in final_by_id:
                    raise ResearchIntegrityError("UNTESTED_STRATEGY_PASSED_GATES")
                validation_result = validation_by_id[variant.variant_id]
                final_result = final_by_id[variant.variant_id]
                validation_base = validation_result.metrics_by_cost_scenario["base"]
                final_base = final_result.metrics_by_cost_scenario["base"]
                wf_fraction = sum(
                    value > 0.0 for value in robustness.walk_forward_net_returns
                ) / len(robustness.walk_forward_net_returns)
                passing_ranking_inputs.append(
                    RankingEvidence(
                        strategy_id=variant.variant_id,
                        strategy_content_sha256=variant.content_sha256,
                        gate_evaluation=evaluation,
                        validation_net_return=validation_base["net_return"],
                        final_test_net_return=final_base["net_return"],
                        validation_max_drawdown=validation_base["max_drawdown"],
                        final_test_max_drawdown=final_base["max_drawdown"],
                        validation_profit_factor=validation_base["profit_factor"],
                        final_test_profit_factor=final_base["profit_factor"],
                        profitable_walk_forward_fraction=wf_fraction,
                        validation_cost_sensitivity=_cost_sensitivity(validation_result),
                        final_test_cost_sensitivity=_cost_sensitivity(final_result),
                    )
                )
        rankings = rank_survivors(tuple(passing_ranking_inputs))
        return {
            "evaluations": evaluations,
            "decisions": decisions,
            "rankings": [
                {
                    "strategy_id": item.strategy_id,
                    "strategy_content_sha256": item.strategy_content_sha256,
                    "score": item.score,
                    "normalized_components": dict(item.normalized_components),
                    "component_weights": dict(item.component_weights),
                }
                for item in rankings
            ],
            "robustness": robustness_rows,
        }

    gates = _ensure_stage(store, loaded, "GATES_COMPLETE", gates_payload)
    _validate_gates_payload(gates, variants=variants)

    registry_path = root / "data" / "registry" / "strategy_registry.sqlite3"

    def registry_payload() -> dict[str, Any]:
        registry = RegistryStore(registry_path)
        decisions = {
            item["strategy_id"]: ValidationDecision.model_validate(item)
            for item in gates["decisions"]
        }
        evaluations = {item["strategy_id"]: item for item in gates["evaluations"]}
        states: dict[str, str] = {}
        for variant in variants:
            prefix = f"{manifest.experiment_id}:{variant.variant_id}"
            registry.register_strategy(
                variant.definition,
                content_sha256=variant.content_sha256,
                idempotency_key=f"{prefix}:generated",
                actor="research-orchestrator",
                occurred_at=dataset.accepted_at,
            )
            registry.transition_strategy(
                variant.variant_id,
                to_state="candidate",
                idempotency_key=f"{prefix}:candidate",
                actor="research-orchestrator",
                reason_code="VALIDATION_COMPLETE",
                immutable_refs={
                    "experiment_id": manifest.experiment_id,
                    "validation_result_sha256": next(
                        item.result_sha256
                        for item in validation
                        if item.strategy_id == variant.variant_id
                    ),
                },
                occurred_at=dataset.accepted_at,
            )
            decision = decisions[variant.variant_id]
            registry.record_validation_decision(decision)
            passed = bool(evaluations[variant.variant_id]["passed"])
            registry.transition_strategy(
                variant.variant_id,
                to_state="paper_shadow" if passed else "rejected",
                idempotency_key=f"{prefix}:{'paper_shadow' if passed else 'rejected'}",
                actor="research-orchestrator",
                reason_code="ALL_HARD_GATES_PASSED" if passed else "HARD_GATES_FAILED",
                immutable_refs={
                    "decision_id": decision.decision_id,
                    "experiment_id": manifest.experiment_id,
                },
                occurred_at=dataset.accepted_at,
            )
            state = registry.get_current_state(variant.variant_id)
            if state is None:
                raise ResearchIntegrityError("REGISTRY_STATE_MISSING")
            states[variant.variant_id] = state
        return {
            "registry_path": registry_path.relative_to(root).as_posix(),
            "states": states,
        }

    registry = _ensure_stage(store, loaded, "REGISTRY_COMPLETE", registry_payload)
    retained_registry_path = _retained_artifact_path(
        root,
        registry["registry_path"],
        expected_prefix=Path("data") / "registry",
    )
    if not retained_registry_path.is_file():
        raise ResearchIntegrityError("REGISTRY_ARTIFACT_MISSING")
    registry_verifier = RegistryStore(retained_registry_path)
    expected_states = cast(dict[str, str], registry["states"])
    if set(expected_states) != {variant.variant_id for variant in variants}:
        raise ResearchIntegrityError("REGISTRY_STATE_MISMATCH")
    expected_passed = {
        item["strategy_id"]: bool(item["passed"])
        for item in cast(list[dict[str, Any]], gates["evaluations"])
    }
    for variant in variants:
        expected_state = "paper_shadow" if expected_passed[variant.variant_id] else "rejected"
        if expected_states[variant.variant_id] != expected_state:
            raise ResearchIntegrityError("REGISTRY_STATE_MISMATCH")
        if registry_verifier.get_current_state(variant.variant_id) != expected_states.get(
            variant.variant_id
        ):
            raise ResearchIntegrityError("REGISTRY_STATE_MISMATCH")
        if registry_verifier.get_strategy_definition(variant.variant_id) != variant.definition:
            raise ResearchIntegrityError("REGISTRY_DEFINITION_MISMATCH")

    def report_payload() -> dict[str, Any]:
        from us_intraday_lab.reporting.research import render_research_report

        path = render_research_report(
            root=root,
            experiment_id=manifest.experiment_id,
            stage_payloads=cast("Mapping[str, Mapping[str, Any]]", loaded),
        )
        return {
            "report_path": path.relative_to(root).as_posix(),
            "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    report = _ensure_stage(store, loaded, "REPORT_COMPLETE", report_payload)
    report_path = _retained_artifact_path(
        root,
        report["report_path"],
        expected_prefix=Path("reports") / "generated" / "research",
    )
    if (
        not report_path.is_file()
        or hashlib.sha256(report_path.read_bytes()).hexdigest() != report["report_sha256"]
    ):
        raise ResearchIntegrityError("REPORT_HASH_MISMATCH")

    evaluations = cast(list[dict[str, Any]], gates["evaluations"])
    survivor_ids = tuple(
        item["strategy_id"] for item in cast(list[dict[str, Any]], gates["rankings"])
    )
    return ResearchRunSummary(
        experiment_id=manifest.experiment_id,
        completed_stages=tuple(stage for stage in RESEARCH_STAGES if stage in loaded),
        variant_count=len(variants),
        final_test_strategy_ids=final_ids,
        survivor_ids=survivor_ids,
        rejected_count=sum(not bool(item["passed"]) for item in evaluations),
        gate_result_counts=MappingProxyType(
            {item["strategy_id"]: len(item["gate_results"]) for item in evaluations}
        ),
        run_directory=store.run_directory,
        registry_path=retained_registry_path,
        report_path=report_path,
    )


def _cost_sensitivity(item: PhaseEvidence) -> float:
    base = item.metrics_by_cost_scenario["base"]["net_return"]
    if base <= 0.0:
        return 1.0
    return min(max((base - item.cost_1_5x_net_return) / base, 0.0), 1.0)


def _validate_gates_payload(
    payload: Mapping[str, Any],
    *,
    variants: tuple[GeneratedVariant, ...],
) -> None:
    strategy_ids = tuple(item.variant_id for item in variants)
    evaluations = cast(list[dict[str, Any]], payload["evaluations"])
    decisions = tuple(
        ValidationDecision.model_validate(item) for item in cast(list[Any], payload["decisions"])
    )
    robustness = tuple(
        RobustnessEvidence.model_validate(item) for item in cast(list[Any], payload["robustness"])
    )
    if (
        tuple(item["strategy_id"] for item in evaluations) != strategy_ids
        or tuple(item.strategy_id for item in decisions) != strategy_ids
        or tuple(item.strategy_id for item in robustness) != strategy_ids
    ):
        raise ResearchIntegrityError("GATE_STRATEGY_ORDER_MISMATCH")
    passed_ids: set[str] = set()
    for raw, decision in zip(evaluations, decisions, strict=True):
        gate_results = tuple(
            GateResult.model_validate(item) for item in cast(list[Any], raw["gate_results"])
        )
        evaluation = HardGateEvaluation(
            strategy_id=cast(str, raw["strategy_id"]),
            split_id=cast(str, raw["split_id"]),
            gate_results=gate_results,
            passed=raw["passed"],
            failure_reason_codes=tuple(raw["failure_reason_codes"]),
        )
        if tuple(item.reason_code for item in gate_results) != HARD_GATE_REASON_CODES:
            raise ResearchIntegrityError("GATE_ORDER_MISMATCH")
        if decision.gate_results != gate_results or decision.strategy_id != evaluation.strategy_id:
            raise ResearchIntegrityError("GATE_DECISION_MISMATCH")
        if evaluation.passed:
            passed_ids.add(evaluation.strategy_id)
    rankings = tuple(
        RankedCandidate(
            strategy_id=item["strategy_id"],
            strategy_content_sha256=item["strategy_content_sha256"],
            score=item["score"],
            normalized_components=item["normalized_components"],
            component_weights=item["component_weights"],
        )
        for item in cast(list[dict[str, Any]], payload["rankings"])
    )
    if {item.strategy_id for item in rankings} != passed_ids:
        raise ResearchIntegrityError("RANKING_SURVIVOR_MISMATCH")


def _retained_artifact_path(
    root: Path,
    relative: object,
    *,
    expected_prefix: Path,
) -> Path:
    if type(relative) is not str or not relative:
        raise ResearchIntegrityError("ARTIFACT_PATH_INVALID")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(expected_prefix):
        raise ResearchIntegrityError("ARTIFACT_PATH_INVALID")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ResearchIntegrityError("ARTIFACT_PATH_INVALID")
    return resolved


def load_accepted_research_dataset(
    *,
    root: Path,
    dataset_id: str,
) -> AcceptedResearchDataset:
    """Bind orchestration to one currently accepted immutable local dataset."""

    from us_intraday_lab.data.catalog import accept_dataset, connect_catalog
    from us_intraday_lab.data.snapshot import verify_snapshot

    accept_dataset(dataset_id, root=root)
    manifest = verify_snapshot(dataset_id, root=root)
    with connect_catalog(root=root) as connection:
        rows = connection.execute(
            "SELECT DISTINCT session_date FROM bars_1m ORDER BY session_date"
        ).fetchall()
    sessions = tuple(row[0] for row in rows)
    return AcceptedResearchDataset(
        dataset_id=manifest.dataset_id,
        content_sha256=manifest.content_sha256,
        calendar_name=manifest.calendar_name,
        calendar_version=manifest.calendar_version,
        sessions=sessions,
        accepted_at=manifest.created_at,
    )


def current_code_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{7,64}", revision) is None:
        raise ValueError("research root must expose a hexadecimal Git revision")
    return revision


def load_research_inputs(
    *,
    experiment_id: str,
    root: Path,
) -> tuple[HypothesisProposal, AcceptedResearchDataset, ExperimentManifest]:
    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    store = _StageStore(root=root.resolve(), experiment_id=experiment_id)
    loaded = store.load_all()
    if "PROPOSAL_ACCEPTED" not in loaded:
        raise ResearchIntegrityError("PROPOSAL_STAGE_MISSING")
    first = loaded["PROPOSAL_ACCEPTED"]
    return (
        HypothesisProposal.model_validate(first["proposal"]),
        AcceptedResearchDataset.model_validate(first["dataset"]),
        ExperimentManifest.model_validate(first["manifest"]),
    )


class BacktestResearchBackend:
    """Local deterministic engine adapter used by the public research CLI."""

    def __init__(
        self,
        *,
        root: Path,
        dataset: AcceptedResearchDataset,
        initial_cash: float = 100_000.0,
    ) -> None:
        if not isinstance(root, Path) or not root.is_dir():
            raise ValueError("root must be an existing directory")
        if type(initial_cash) not in {int, float} or not math.isfinite(initial_cash):
            raise ValueError("initial_cash must be an exact finite number")
        if initial_cash <= 0.0:
            raise ValueError("initial_cash must be positive")
        self._root = root.resolve()
        self._dataset = AcceptedResearchDataset.model_validate(dataset)
        self._initial_cash = float(initial_cash)
        self._phase_frames: dict[tuple[date, ...], tuple[Any, Any]] = {}

    def _load_frames(self, sessions: tuple[date, ...]) -> tuple[Any, Any]:
        if not sessions:
            raise ValueError("phase sessions must not be empty")
        retained = self._phase_frames.get(sessions)
        if retained is None:
            from us_intraday_lab.data.catalog import connect_catalog

            placeholders = ", ".join("?" for _session in sessions)
            with connect_catalog(root=self._root) as connection:
                minute_bars = connection.execute(
                    f"SELECT * FROM bars_1m WHERE session_date IN ({placeholders}) "
                    "ORDER BY session_date, timestamp, symbol",
                    list(sessions),
                ).df()
                signal_bars = connection.execute(
                    f"SELECT * FROM bars_15m WHERE session_date IN ({placeholders}) "
                    "ORDER BY session_date, available_at, symbol",
                    list(sessions),
                ).df()
            retained = (minute_bars, signal_bars)
            self._phase_frames[sessions] = retained
        return retained

    def run_phase(
        self,
        *,
        variant: GeneratedVariant,
        phase: str,
        sessions: tuple[date, ...],
        experiment_id: str,
    ) -> PhaseEvidence:
        from us_intraday_lab.backtest.costs import COST_SCENARIOS
        from us_intraday_lab.backtest.engine import (
            CALENDAR_ID,
            ENGINE_ID,
            BacktestEngine,
            input_data_sha256,
            write_backtest_artifacts,
        )
        from us_intraday_lab.contracts.backtests import BacktestJob, BacktestResult, CostModelIds
        from us_intraday_lab.strategy.compiler import compile_strategy

        if phase not in {"train", "validation", "final_test"}:
            raise ValueError("phase must be train, validation, or final_test")
        minute_bars, signal_bars = self._load_frames(sessions)
        session_set = set(sessions)
        minute_phase = cast(
            Any,
            minute_bars.loc[minute_bars["session_date"].isin(session_set)].copy(deep=True),
        )
        signal_phase = cast(
            Any,
            signal_bars.loc[signal_bars["session_date"].isin(session_set)].copy(deep=True),
        )
        if minute_phase.empty or signal_phase.empty:
            raise ValueError(f"{phase} phase has no bars")
        compiled = compile_strategy(variant.definition)
        job = BacktestJob.create(
            schema_version="1.0.0",
            strategy_id=compiled.definition_fingerprint,
            dataset_id=self._dataset.dataset_id,
            engine_id=ENGINE_ID,
            calendar_id=CALENDAR_ID,
            input_data_sha256=input_data_sha256(minute_phase, signal_phase),
            initial_cash=self._initial_cash,
            closeout_buffer_minutes=5,
            cost_model_ids=CostModelIds(
                optimistic=COST_SCENARIOS["optimistic"].model_id,
                base=COST_SCENARIOS["base"].model_id,
                stress=COST_SCENARIOS["stress"].model_id,
            ),
        )
        run = BacktestEngine(job=job, strategy=compiled).run(
            minute_bars=minute_phase,
            signal_bars=signal_phase,
        )
        result_path = write_backtest_artifacts(run, root=self._root)
        result = BacktestResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        metrics = {scenario: dict(run.scenarios[scenario].metrics) for scenario in _SCENARIOS}
        base = metrics["base"]
        session_returns = {
            session.isoformat(): float(base.get(f"pnl_by_session:{session.isoformat()}", 0.0))
            / self._initial_cash
            for session in sessions
        }
        cost_1_5x = base["net_return"] - 0.5 * base["cost_paid"] / self._initial_cash
        null_evidence = (
            _null_evidence_from_run(
                variant=variant,
                run=run,
                minute_bars=minute_phase,
                initial_cash=self._initial_cash,
                result_sha256=result.content_sha256,
            )
            if phase == "validation"
            else None
        )
        return PhaseEvidence(
            strategy_id=variant.variant_id,
            phase=cast(ResearchPhase, phase),
            job_id=job.job_id,
            run_id=run.run_id,
            result_sha256=result.content_sha256,
            metrics_by_cost_scenario=metrics,
            cost_1_5x_net_return=cost_1_5x,
            profit_by_symbol={
                symbol: float(base.get(f"pnl_by_symbol:{symbol}", 0.0))
                for symbol in ("SPY", "QQQ", "IWM")
            },
            session_net_returns=session_returns,
            source_refs=(
                f"experiment:{experiment_id}",
                f"job:{job.job_id}",
                f"result:{result.content_sha256}",
            ),
            null_evidence=null_evidence,
        )

    def robustness_evidence(
        self,
        *,
        variant: GeneratedVariant,
        validation_results: tuple[PhaseEvidence, ...],
        experiment_id: str,
    ) -> RobustnessEvidence:
        current = next(
            item for item in validation_results if item.strategy_id == variant.variant_id
        )
        neighbors = tuple(
            item for item in validation_results if item.strategy_id != variant.variant_id
        )[:5]
        if len(neighbors) < 2:
            raise ValueError("robustness requires at least two generated neighbor strategies")
        session_returns = tuple(
            current.session_net_returns[key] for key in sorted(current.session_net_returns)
        )
        offsets = (-1, 0, 1)
        start_points = tuple(
            StartDatePoint(
                offset_sessions=offset,
                net_return=_compound_returns(
                    session_returns[:-1]
                    if offset < 0
                    else session_returns[1:]
                    if offset > 0
                    else session_returns
                ),
                max_drawdown=current.metrics_by_cost_scenario["base"]["max_drawdown"],
            )
            for offset in offsets
        )
        null_evidence = current.null_evidence or _safe_failed_null_evidence(
            variant=variant,
            phase=current,
            reason="eligible opportunity ledger unavailable",
            initial_cash=self._initial_cash,
        )
        return RobustnessEvidence(
            strategy_id=variant.variant_id,
            walk_forward_net_returns=session_returns,
            parameter_points=tuple(
                RobustnessPoint(
                    observation_id=item.strategy_id,
                    net_return=item.metrics_by_cost_scenario["base"]["net_return"],
                    max_drawdown=item.metrics_by_cost_scenario["base"]["max_drawdown"],
                )
                for item in neighbors
            ),
            start_date_points=start_points,
            null_evidence=null_evidence,
            source_refs=(
                f"experiment:{experiment_id}",
                f"validation-result:{current.result_sha256}",
                "null-status:fail-closed-no-eligible-opportunity-ledger",
            ),
        )


def _compound_returns(values: tuple[float, ...]) -> float:
    if not values:
        raise ValueError("return sequence must not be empty")
    return math.prod(1.0 + value for value in values) - 1.0


def _null_evidence_from_run(
    *,
    variant: GeneratedVariant,
    run: Any,
    minute_bars: Any,
    initial_cash: float,
    result_sha256: str,
) -> NullEvidenceSummary:
    import pandas as pd

    from us_intraday_lab.backtest.costs import COST_SCENARIOS
    from us_intraday_lab.validation.null_tests import (
        NullOpportunity,
        NullTestConfig,
        run_null_tests,
    )

    base = run.scenarios["base"]
    signals = tuple(
        event
        for event in base.events
        if event.event_type == "SIGNAL_ENTER_LONG" and event.symbol is not None
    )
    if not signals:
        return _safe_failed_null_evidence_from_values(
            variant=variant,
            observed_profit=base.metrics["net_return"] * initial_cash,
            trade_count=int(base.metrics["trade_count"]),
            first_session=min(item.isoformat() for item in minute_bars["session_date"]),
            result_sha256=result_sha256,
            reason="no eligible entry signals",
        )
    ordered_signals = tuple(
        sorted(signals, key=lambda item: (item.session, item.event_time, item.symbol or ""))
    )
    matched: set[int] = set()
    for trade in sorted(base.trades, key=lambda item: item.entry_time):
        candidates = [
            index
            for index, signal in enumerate(ordered_signals)
            if index not in matched
            and signal.symbol == trade.symbol
            and signal.session == trade.session
            and signal.event_time <= trade.entry_time
        ]
        if candidates:
            matched.add(max(candidates, key=lambda index: ordered_signals[index].event_time))

    grouped = {
        (symbol, session): group.sort_values("timestamp")
        for (symbol, session), group in minute_bars.groupby(["symbol", "session_date"], sort=False)
    }
    opportunities: list[NullOpportunity] = []
    base_cost = COST_SCENARIOS["base"]
    for index, signal in enumerate(ordered_signals):
        assert signal.symbol is not None
        group = grouped.get((signal.symbol, signal.session))
        if group is None:
            continue
        timestamps = pd.to_datetime(group["timestamp"], utc=True)
        eligible = group.loc[timestamps > pd.Timestamp(signal.event_time)]
        if eligible.empty:
            continue
        entry_row = eligible.iloc[0]
        entry_time = pd.Timestamp(entry_row["timestamp"]).tz_convert("UTC").to_pydatetime()
        target = entry_time + timedelta(minutes=variant.definition.risk.max_holding_minutes)
        exits = group.loc[pd.to_datetime(group["timestamp"], utc=True) >= pd.Timestamp(target)]
        exit_row = exits.iloc[0] if not exits.empty else group.iloc[-1]
        exit_time = pd.Timestamp(exit_row["timestamp"]).tz_convert("UTC").to_pydatetime()
        entry_price = float(entry_row["open"])
        exit_price = float(exit_row["open"])
        quantity = max(1, math.floor((initial_cash / 3.0) / entry_price))
        profit = (
            quantity * (exit_price - entry_price)
            - base_cost.variable_cost(entry_price * quantity, quantity)
            - base_cost.variable_cost(exit_price * quantity, quantity)
        )
        opportunity_id = (
            "opportunity-"
            + _sha256_json(
                {
                    "entry_time": entry_time.isoformat(),
                    "signal_time": signal.event_time.isoformat(),
                    "strategy_id": variant.variant_id,
                    "symbol": signal.symbol,
                }
            )[:32]
        )
        opportunities.append(
            NullOpportunity(
                opportunity_id=opportunity_id,
                symbol=signal.symbol,
                session=signal.session,
                signal_time=signal.event_time,
                entry_time=entry_time,
                exit_time=exit_time,
                entered=index in matched,
                holding_rule_net_profit=profit,
            )
        )
    canonical = tuple(
        sorted(
            opportunities,
            key=lambda item: (
                item.session,
                item.signal_time,
                item.symbol,
                item.opportunity_id,
            ),
        )
    )
    try:
        result = run_null_tests(
            canonical,
            config=NullTestConfig(seed=int(variant.content_sha256[:16], 16)),
            scoring_config=HoldingRuleScoringConfig(
                scoring_id=f"{variant.variant_id}:holding-rule",
                rule_version="strategy-dsl-1.0.0-fixed-holding",
                cost_model_id="cost-base-1.0.0",
                cooldown_minutes=variant.definition.risk.cooldown_minutes,
                max_entries_per_session=variant.definition.risk.max_entries_per_session,
                max_concurrent_positions=3,
            ),
        )
    except (TypeError, ValueError) as error:
        return _safe_failed_null_evidence_from_values(
            variant=variant,
            observed_profit=base.metrics["net_return"] * initial_cash,
            trade_count=int(base.metrics["trade_count"]),
            first_session=min(item.isoformat() for item in minute_bars["session_date"]),
            result_sha256=result_sha256,
            reason=str(error),
        )
    by_method = {item.method: item for item in result.distributions}
    permutation = by_method["SESSION_SIGNAL_PERMUTATION"]
    shift = by_method["SESSION_SAFE_TIMESTAMP_SHIFT"]
    return NullEvidenceSummary(
        passed=result.passed,
        seed=result.seed,
        repetitions=result.repetitions,
        percentile=result.percentile,
        observed_profit=result.observed_profit,
        permutation_threshold=permutation.percentile_threshold,
        timestamp_shift_threshold=shift.percentile_threshold,
        evidence_sha256=result.evidence_sha256,
        evidence_opportunity_ids=result.evidence_opportunity_ids,
        trade_count_by_symbol_session=result.trade_count_by_symbol_session,
        permutation_statistics=permutation.statistics,
        permutation_accepted_entry_counts=permutation.accepted_entry_counts,
        permutation_rejected_entry_counts=permutation.rejected_entry_counts,
        timestamp_shift_statistics=shift.statistics,
        timestamp_shift_accepted_entry_counts=shift.accepted_entry_counts,
        timestamp_shift_rejected_entry_counts=shift.rejected_entry_counts,
    )


def _safe_failed_null_evidence(
    *,
    variant: GeneratedVariant,
    phase: PhaseEvidence,
    reason: str,
    initial_cash: float,
) -> NullEvidenceSummary:
    return _safe_failed_null_evidence_from_values(
        variant=variant,
        observed_profit=phase.metrics_by_cost_scenario["base"]["net_return"] * initial_cash,
        trade_count=int(phase.metrics_by_cost_scenario["base"]["trade_count"]),
        first_session=min(phase.session_net_returns),
        result_sha256=phase.result_sha256,
        reason=reason,
    )


def _safe_failed_null_evidence_from_values(
    *,
    variant: GeneratedVariant,
    observed_profit: float,
    trade_count: int,
    first_session: str,
    result_sha256: str,
    reason: str,
) -> NullEvidenceSummary:
    repetitions = 200
    threshold = max(observed_profit, 0.0)
    evidence_sha256 = _sha256_json(
        {
            "reason": reason,
            "result_sha256": result_sha256,
            "strategy_id": variant.variant_id,
        }
    )
    return NullEvidenceSummary(
        passed=False,
        seed=int(variant.content_sha256[:16], 16),
        repetitions=repetitions,
        percentile=0.95,
        observed_profit=observed_profit,
        permutation_threshold=threshold,
        timestamp_shift_threshold=threshold,
        evidence_sha256=evidence_sha256,
        evidence_opportunity_ids=(f"{variant.variant_id}:null-failed:{evidence_sha256[:16]}",),
        trade_count_by_symbol_session={
            f"{first_session}:SPY": trade_count,
            f"{first_session}:QQQ": 0,
            f"{first_session}:IWM": 0,
        },
        permutation_statistics=(threshold,) * repetitions,
        permutation_accepted_entry_counts=(trade_count,) * repetitions,
        permutation_rejected_entry_counts=(0,) * repetitions,
        timestamp_shift_statistics=(threshold,) * repetitions,
        timestamp_shift_accepted_entry_counts=(trade_count,) * repetitions,
        timestamp_shift_rejected_entry_counts=(0,) * repetitions,
    )
