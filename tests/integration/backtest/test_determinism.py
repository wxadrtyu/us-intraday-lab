from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _run_clean_process(
    *,
    root: Path,
    dataset_id: str,
    hash_seed: str,
) -> tuple[Path, dict[str, object], dict[str, bytes]]:
    strategy = (
        Path(__file__).parents[2] / "fixtures" / "strategies" / ("valid_momentum_pullback.json")
    )
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "us_intraday_lab.cli",
            "backtest",
            "run",
            "--strategy",
            str(strategy),
            "--dataset-id",
            dataset_id,
            "--initial-cash",
            "25000",
            "--root",
            str(root),
        ],
        cwd=Path(__file__).parents[3],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result_path = Path(completed.stdout.strip().splitlines()[-1])
    artifact_dir = result_path.parent
    contents = {
        name: (artifact_dir / name).read_bytes()
        for name in ("events.jsonl", "job.json", "result.json", "trades.jsonl")
    }
    return result_path, json.loads(contents["result.json"]), contents


def test_two_clean_processes_produce_identical_deterministic_artifacts(
    accepted_backtest_dataset: tuple[Path, str],
) -> None:
    root, dataset_id = accepted_backtest_dataset

    first_path, first_result, first_contents = _run_clean_process(
        root=root,
        dataset_id=dataset_id,
        hash_seed="101",
    )
    second_path, second_result, second_contents = _run_clean_process(
        root=root,
        dataset_id=dataset_id,
        hash_seed="202",
    )

    assert first_path == second_path
    assert first_contents == second_contents
    assert first_result == second_result
    assert first_path == root / "artifacts" / "backtests" / first_result["run_id"] / "result.json"
    assert first_result["content_sha256"] == second_result["content_sha256"]
    assert {name: _sha256(content) for name, content in first_contents.items()} == {
        name: _sha256(content) for name, content in second_contents.items()
    }

    metrics = first_result["metrics_by_cost_scenario"]
    assert set(metrics) == {"optimistic", "base", "stress"}
    assert all(metrics[scenario]["trade_count"] > 0 for scenario in metrics)
    assert all(metrics[scenario]["cost_paid"] > 0 for scenario in metrics)
    events = [json.loads(line) for line in first_contents["events.jsonl"].decode().splitlines()]
    finalized = [event for event in events if event["event_type"] == "SESSION_FINALIZED"]
    assert len(finalized) == 3
    assert all(event["details"]["position_count"] == 0 for event in finalized)
