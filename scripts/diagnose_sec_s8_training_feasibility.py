from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from us_intraday_lab.sec_s8_training_feasibility import run_diagnostic

EVENT_CUBE_SHA256 = "399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9"
COVERAGE_SHA256 = "62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"SEC_S8_DIAGNOSTIC_IMMUTABLE_COLLISION:{path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _parquet_bytes(path: Path, cells: pd.DataFrame) -> bytes:
    export = cells.copy()
    for column in ("standard_9bp", "cost_18bp", "delay_1bar_9bp"):
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
    ranked = valid.sort_values(
        [
            "retention_floor_passed",
            "standard_annualized_return",
            "standard_information_ratio",
            "family",
            "decision_bar",
            "holding_bars",
            "top_count",
        ],
        ascending=[False, False, False, True, True, True, True],
        kind="stable",
    ).head(10)
    columns = [
        "family",
        "decision_bar",
        "holding_bars",
        "top_count",
        "signal_sessions",
        "retention_floor_passed",
        "standard_annualized_return",
        "standard_information_ratio",
    ]
    return [_json_safe(row) for row in ranked.loc[:, columns].to_dict("records")]


def render_markdown(summary: dict[str, Any]) -> str:
    families = ", ".join(summary["retained_families"]) or "none"
    return "\n".join(
        [
            "# SEC original Form S-8 training feasibility",
            "",
            f"- Status: **{summary['status']}**",
            f"- Decision: **{summary['decision']}**",
            "- Sample: **527-symbol 2021-2023 coverage-limited sample; not full market**",
            f"- Admissible issuer-document pairs: {summary['coverage']['issuer_document_pairs']:,}",
            f"- Distinct issuers: {summary['coverage']['distinct_issuers']:,}",
            f"- Active symbol-session states: {summary['active_state_rows']:,}",
            f"- Cells completed: {summary['cells_completed']:,}",
            f"- Invalid cells: {summary['invalid_cells']:,}",
            f"- Retained cells: {summary['retained_cells']:,}",
            f"- Retained families: {families}",
            f"- Event cube SHA-256: `{summary['event_cube_sha256']}`",
            f"- Coverage SHA-256: `{summary['coverage_sha256']}`",
            f"- Cell table SHA-256: `{summary['cells_sha256']}`",
            f"- Strategy versions created: **{summary['strategy_versions_created']}**",
            "- Development or consumed data loaded: **false**",
            "- Primary-document bodies opened: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen training-only SEC original Form S-8 diagnostic."
    )
    parser.add_argument("--event-cube", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cells, raw_summary = run_diagnostic(
        event_cube_path=args.event_cube,
        coverage_path=args.coverage,
        expected_event_sha256=EVENT_CUBE_SHA256,
        expected_coverage_sha256=COVERAGE_SHA256,
    )
    if (
        raw_summary.get("status") != "COMPLETE"
        or raw_summary.get("cells_completed") != 400
        or raw_summary.get("strategy_versions_created") != 0
        or raw_summary.get("development_or_consumed_loaded") is not False
        or raw_summary.get("paper_activation") is not False
        or raw_summary.get("order_route") != "FORBIDDEN"
    ):
        raise RuntimeError("SEC_S8_DIAGNOSTIC_OUTPUT_CONTRACT_INVALID")

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
