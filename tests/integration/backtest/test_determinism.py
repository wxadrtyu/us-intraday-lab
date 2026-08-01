from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _backtest_command(
    *,
    root: Path,
    dataset_id: str,
    strategy: Path | None = None,
) -> list[str]:
    strategy = strategy or (
        Path(__file__).parents[2] / "fixtures" / "strategies" / "valid_momentum_pullback.json"
    )
    return [
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
    ]


def _run_clean_process(
    *,
    root: Path,
    dataset_id: str,
    hash_seed: str,
) -> tuple[Path, dict[str, object], dict[str, bytes]]:
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        _backtest_command(root=root, dataset_id=dataset_id),
        cwd=Path(__file__).parents[3],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result_path = Path(completed.stdout.strip().splitlines()[-1])
    artifact_dir = result_path.parent
    contents = {
        path.relative_to(artifact_dir).as_posix(): path.read_bytes()
        for path in sorted(artifact_dir.rglob("*"))
        if path.is_file()
    }
    return result_path, json.loads(contents["result.json"]), contents


def test_two_clean_processes_produce_identical_deterministic_artifacts(
    accepted_backtest_dataset_pair: tuple[Path, Path, str],
) -> None:
    first_root, second_root, dataset_id = accepted_backtest_dataset_pair
    assert not (first_root / "artifacts").exists()
    assert not (second_root / "artifacts").exists()

    first_path, first_result, first_contents = _run_clean_process(
        root=first_root,
        dataset_id=dataset_id,
        hash_seed="101",
    )
    second_path, second_result, second_contents = _run_clean_process(
        root=second_root,
        dataset_id=dataset_id,
        hash_seed="202",
    )

    assert first_path.relative_to(first_root) == second_path.relative_to(second_root)
    assert first_contents == second_contents
    assert first_result == second_result
    assert first_path == (
        first_root / "artifacts" / "backtests" / first_result["run_id"] / "result.json"
    )
    assert first_result["content_sha256"] == second_result["content_sha256"]
    assert {name: _sha256(content) for name, content in first_contents.items()} == {
        name: _sha256(content) for name, content in second_contents.items()
    }

    metrics = first_result["metrics_by_cost_scenario"]
    assert set(metrics) == {"optimistic", "base", "stress"}
    assert all(metrics[scenario]["trade_count"] > 0 for scenario in metrics)
    assert all(metrics[scenario]["cost_paid"] > 0 for scenario in metrics)
    events = [json.loads(line) for line in first_contents["events.jsonl"].decode().splitlines()]
    intents = [json.loads(line) for line in first_contents["intents.jsonl"].decode().splitlines()]
    assert intents
    assert {
        "eligible_time",
        "idempotency_key",
        "limit_price",
        "order_type",
        "quantity",
        "reason_code",
        "scenario",
        "side",
    } <= intents[0].keys()
    finalized = [event for event in events if event["event_type"] == "SESSION_FINALIZED"]
    assert len(finalized) == 3
    assert all(event["details"]["position_count"] == 0 for event in finalized)


def test_cli_fails_nonzero_with_typed_failure_on_artifact_collision(
    accepted_backtest_dataset: tuple[Path, str],
) -> None:
    root, dataset_id = accepted_backtest_dataset
    result_path, _, _ = _run_clean_process(
        root=root,
        dataset_id=dataset_id,
        hash_seed="303",
    )
    (result_path.parent / "unexpected.txt").write_text("collision\n", encoding="utf-8")

    completed = subprocess.run(
        _backtest_command(root=root, dataset_id=dataset_id),
        cwd=Path(__file__).parents[3],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert '"status":"failed"' in completed.stderr
    assert '"failure_type":"artifact_write"' in completed.stderr
    assert "different content" in completed.stderr


def test_cli_missing_strategy_returns_typed_failed_result(
    accepted_backtest_dataset: tuple[Path, str],
) -> None:
    root, dataset_id = accepted_backtest_dataset
    completed = subprocess.run(
        _backtest_command(
            root=root,
            dataset_id=dataset_id,
            strategy=root / "missing-strategy.json",
        ),
        cwd=Path(__file__).parents[3],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stderr.strip().splitlines()[-1])
    assert result["status"] == "failed"
    assert result["failure"]["failure_type"] == "strategy_validation"
    assert result["events_uri"] is None
    assert result["intents_uri"] is None
    assert result["trades_uri"] is None


def test_cli_unaccepted_dataset_returns_typed_failed_result(tmp_path: Path) -> None:
    root = tmp_path / "empty-root"
    root.mkdir()
    completed = subprocess.run(
        _backtest_command(root=root, dataset_id="missing-dataset"),
        cwd=Path(__file__).parents[3],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stderr.strip().splitlines()[-1])
    assert result["status"] == "failed"
    assert result["failure"]["failure_type"] == "dataset_validation"
    assert result["events_uri"] is None
    assert result["intents_uri"] is None
    assert result["trades_uri"] is None
