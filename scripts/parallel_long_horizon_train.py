from __future__ import annotations

import argparse
import json
import multiprocessing
from datetime import date
from pathlib import Path

from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.long_horizon.orchestrator import (
    LocalFiveMinuteResearchBackend,
    _checkpointed_evaluate,
    _sha256,
)
from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal
from us_intraday_lab.long_horizon.splits import create_long_horizon_split
from us_intraday_lab.long_horizon.variants import generate_long_horizon_variants

_BACKEND: LocalFiveMinuteResearchBackend | None = None
_DATASET_ID = ""
_EXPERIMENT_ROOT = Path()
_SESSIONS: tuple[date, ...] = ()


def _initialize_worker(
    root: str,
    dataset_id: str,
    experiment_root: str,
    sessions: tuple[date, ...],
) -> None:
    global _BACKEND, _DATASET_ID, _EXPERIMENT_ROOT, _SESSIONS
    _BACKEND = LocalFiveMinuteResearchBackend(root=Path(root), dataset_id=dataset_id)
    _DATASET_ID = dataset_id
    _EXPERIMENT_ROOT = Path(experiment_root)
    _SESSIONS = sessions


def _train_one(strategy_record: dict[str, object]) -> str:
    if _BACKEND is None:
        raise RuntimeError("parallel worker was not initialized")
    strategy = StrategyDefinition.model_validate(strategy_record)
    evaluation = _checkpointed_evaluate(
        _BACKEND,
        strategy,
        _SESSIONS,
        phase="train",
        dataset_id=_DATASET_ID,
        experiment_root=_EXPERIMENT_ROOT,
    )
    return evaluation.strategy_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal-dir", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--strategy-id")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be between one and sixteen")
    proposals = tuple(
        LongHorizonHypothesisProposal.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(args.proposal_dir.glob("*.json"))
    )
    if not proposals:
        raise ValueError("proposal directory contains no JSON proposals")
    variants = tuple(
        strategy
        for proposal in proposals
        for strategy in generate_long_horizon_variants(proposal)
        if args.strategy_id is None or strategy.strategy_id == args.strategy_id
    )
    if not variants:
        raise ValueError("strategy-id did not match a generated variant")
    root = args.root.resolve()
    metadata_backend = LocalFiveMinuteResearchBackend(root=root, dataset_id=args.dataset_id)
    sessions = metadata_backend.accepted_sessions(args.dataset_id)
    split = create_long_horizon_split(sessions, split_id=f"{args.dataset_id}-60-20-20-v1")
    experiment_id = (
        "lh-"
        + _sha256(
            {
                "dataset_id": args.dataset_id,
                "proposals": [proposal.model_dump(mode="json") for proposal in proposals],
                "split_id": split.split_id,
            }
        )[:32]
    )
    experiment_root = root / "artifacts" / "long_horizon" / "experiments" / experiment_id
    experiment_root.mkdir(parents=True, exist_ok=True)
    records = tuple(strategy.model_dump(mode="json") for strategy in variants)
    context = multiprocessing.get_context("spawn")
    completed = 0
    with context.Pool(
        processes=args.workers,
        initializer=_initialize_worker,
        initargs=(
            str(root),
            args.dataset_id,
            str(experiment_root),
            split.train_sessions,
        ),
    ) as pool:
        for strategy_id in pool.imap_unordered(_train_one, records, chunksize=1):
            completed += 1
            print(
                json.dumps(
                    {
                        "completed": completed,
                        "strategy_id": strategy_id,
                        "total": len(records),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
