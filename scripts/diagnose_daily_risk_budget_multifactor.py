from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

try:
    from scripts.diagnose_daily_technical_multifactor import (
        _json_safe,
        _sha256,
        _write_immutable,
    )
except ModuleNotFoundError:
    from diagnose_daily_technical_multifactor import _json_safe, _sha256, _write_immutable

from us_intraday_lab.daily_risk_budget_multifactor import run_diagnostic

DAILY_SOURCE_SHA256 = "0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701"
SYMBOL_CONTAINER_SHA256 = "399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9"


def _parquet_bytes(path: Path, cells: pd.DataFrame) -> bytes:
    export = cells.copy()
    for column in ("standard_9bp", "cost_18bp", "delay_1session_9bp"):
        export[column] = export[column].map(
            lambda value: json.dumps(_json_safe(value), sort_keys=True)
        )
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    try:
        export.to_parquet(temporary, index=False, compression="zstd")
        return temporary.read_bytes()
    finally:
        temporary.unlink(missing_ok=True)


def _best_cells(cells: pd.DataFrame) -> list[dict[str, object]]:
    valid = cells.loc[cells["valid"].eq(True)].copy()
    if valid.empty:
        return []
    valid["standard_annualized_return"] = valid["standard_9bp"].map(
        lambda value: float(value["annualized_return"])
    )
    valid["standard_information_ratio"] = valid["standard_9bp"].map(
        lambda value: float(value["information_ratio"])
    )
    valid["standard_max_drawdown"] = valid["standard_9bp"].map(
        lambda value: float(value["max_drawdown"])
    )
    ranked = valid.sort_values(
        [
            "retention_floor_passed",
            "standard_annualized_return",
            "standard_information_ratio",
            "family",
            "signal_lag",
            "holding_sessions",
            "top_count",
        ],
        ascending=[False, False, False, True, True, True, True],
        kind="stable",
    ).head(10)
    columns = [
        "family",
        "signal_lag",
        "holding_sessions",
        "top_count",
        "signal_sessions",
        "retention_floor_passed",
        "standard_annualized_return",
        "standard_information_ratio",
        "standard_max_drawdown",
    ]
    return [_json_safe(row) for row in ranked.loc[:, columns].to_dict("records")]


def render_markdown(summary: dict[str, Any]) -> str:
    families = ", ".join(summary["retained_families"]) or "none"
    return "\n".join(
        [
            "# Daily risk-budget multi-factor training diagnostic",
            "",
            f"- Status: **{summary['status']}**",
            f"- Decision: **{summary['decision']}**",
            "- Sample: **527-symbol 2021-2023 coverage-limited sample; not full market**",
            f"- Symbols with daily bars: {summary['symbols']:,}",
            f"- Cells completed: {summary['cells_completed']:,}",
            f"- Invalid cells: {summary['invalid_cells']:,}",
            f"- Retained cells: {summary['retained_cells']:,}",
            f"- Retained families: {families}",
            f"- Daily source SHA-256: `{summary['daily_source_sha256']}`",
            f"- Symbol container SHA-256: `{summary['symbol_container_sha256']}`",
            f"- Cell table SHA-256: `{summary['cells_sha256']}`",
            f"- Strategy versions created: **{summary['strategy_versions_created']}**",
            "- Development or consumed data loaded: **false**",
            "- News or issuer-event data loaded: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen training-only daily risk-budget multi-factor diagnostic."
    )
    parser.add_argument("--daily-root", required=True, type=Path)
    parser.add_argument("--symbol-container", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cells, raw_summary = run_diagnostic(
        daily_root=args.daily_root,
        symbol_container_path=args.symbol_container,
        expected_daily_sha256=DAILY_SOURCE_SHA256,
        expected_symbol_container_sha256=SYMBOL_CONTAINER_SHA256,
    )
    if (
        raw_summary.get("status") != "COMPLETE"
        or raw_summary.get("cells_completed") != 400
        or raw_summary.get("strategy_versions_created") != 0
        or raw_summary.get("development_or_consumed_loaded") is not False
        or raw_summary.get("news_or_issuer_event_data_loaded") is not False
        or raw_summary.get("paper_activation") is not False
        or raw_summary.get("order_route") != "FORBIDDEN"
    ):
        raise RuntimeError("DAILY_RISK_BUDGET_OUTPUT_CONTRACT_INVALID")
    parquet_content = _parquet_bytes(args.output_parquet, cells)
    _write_immutable(args.output_parquet, parquet_content)
    summary = _json_safe(
        {
            **raw_summary,
            "cells_path": str(args.output_parquet.resolve()),
            "cells_sha256": _sha256(args.output_parquet),
            "best_training_cells": _best_cells(cells),
        }
    )
    _write_immutable(
        args.output_json,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    _write_immutable(args.output_md, render_markdown(summary).encode("utf-8"))
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "status",
                    "decision",
                    "cells_completed",
                    "invalid_cells",
                    "retained_cells",
                    "retained_families",
                    "runtime_seconds",
                )
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
