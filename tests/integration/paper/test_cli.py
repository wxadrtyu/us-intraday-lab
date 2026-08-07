from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from typer.testing import CliRunner

from tests.fakes.broker import FakePaperBroker
from us_intraday_lab import cli
from us_intraday_lab.cli import PAPER_SESSION_STATES, app


def test_paper_cli_exposes_only_paper_workflow_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["paper", "--help"])

    assert result.exit_code == 0
    for command in ("preflight", "run", "reconcile", "closeout"):
        assert command in result.stdout
    lowered = result.stdout.lower()
    assert "--live" not in lowered
    assert "--base-url" not in lowered


def test_paper_session_keeps_forward_lifecycle_strategies_running() -> None:
    assert PAPER_SESSION_STATES == (
        "paper_shadow",
        "paper_observing",
        "paper_ranked",
        "leader",
    )


def test_first_preflight_passes_connection_checks_without_session_or_registry(
    tmp_path, monkeypatch
) -> None:
    broker = FakePaperBroker(now=datetime(2026, 8, 7, 14, 0, tzinfo=UTC))
    monkeypatch.setattr(
        FakePaperBroker,
        "endpoint",
        "https://paper-api.alpaca.markets",
        raising=False,
    )
    monkeypatch.setattr(
        cli.AlpacaPaperBroker,
        "from_environment",
        classmethod(lambda cls: broker),
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    result = CliRunner().invoke(app, ["paper", "preflight", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["preflight_passed"] is True
    assert payload["ready_for_paper_run"] is False
    assert payload["readiness_blockers"] == [
        "STRATEGY_REGISTRY_MISSING",
        "NO_ENABLED_PAPER_STRATEGY",
        "PAPER_SESSION_NOT_STARTED",
    ]
    assert payload["preflight_submitted_orders"] == 0
    assert broker.submit_attempted_idempotency_keys == []


def test_sip_comparison_is_explicitly_diagnostic_only() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["data", "diagnose-sip-difference", "--help"])

    assert result.exit_code == 0
    assert "diagnostic" in result.stdout.lower()
