from __future__ import annotations

from typer.testing import CliRunner

from us_intraday_lab.cli import app


def test_paper_cli_exposes_only_paper_workflow_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["paper", "--help"])

    assert result.exit_code == 0
    for command in ("preflight", "run", "reconcile", "closeout"):
        assert command in result.stdout
    lowered = result.stdout.lower()
    assert "--live" not in lowered
    assert "--base-url" not in lowered


def test_sip_comparison_is_explicitly_diagnostic_only() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["data", "diagnose-sip-difference", "--help"])

    assert result.exit_code == 0
    assert "diagnostic" in result.stdout.lower()
