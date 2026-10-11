from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.diagnose_daily_technical_multifactor import (
    _best_cells,
    _json_safe,
    _parquet_bytes,
    _sha256,
    _write_immutable,
)
from us_intraday_lab.daily_price_state_multifactor import run_diagnostic

DAILY_SOURCE_SHA256 = "0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701"
EVENT_CUBE_SHA256 = "399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9"


def render_markdown(summary: dict[str, Any]) -> str:
    families = ", ".join(summary["retained_families"]) or "none"
    eligibility = [
        f"  - {family}: {values['pairs']:,} pairs, {values['symbols']:,} symbols, "
        f"{values['sessions']:,} sessions"
        for family, values in summary["family_eligibility"].items()
    ]
    return "\n".join(
        [
            "# Daily price-state multi-factor training diagnostic",
            "",
            f"- Status: **{summary['status']}**",
            f"- Decision: **{summary['decision']}**",
            "- Sample: **527-symbol 2021-2023 coverage-limited sample; not full market**",
            "- Family eligibility:",
            *eligibility,
            f"- Cells completed: {summary['cells_completed']:,}",
            f"- Invalid cells: {summary['invalid_cells']:,}",
            f"- Retained cells: {summary['retained_cells']:,}",
            f"- Retained families: {families}",
            f"- Daily source SHA-256: `{summary['daily_source_sha256']}`",
            f"- Event cube SHA-256: `{summary['event_cube_sha256']}`",
            f"- Cell table SHA-256: `{summary['cells_sha256']}`",
            f"- Strategy versions created: **{summary['strategy_versions_created']}**",
            "- Development or consumed data loaded: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen training-only daily price-state diagnostic."
    )
    parser.add_argument("--daily-root", required=True, type=Path)
    parser.add_argument("--event-cube", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cells, raw_summary = run_diagnostic(
        daily_root=args.daily_root,
        event_cube_path=args.event_cube,
        expected_daily_sha256=DAILY_SOURCE_SHA256,
        expected_event_sha256=EVENT_CUBE_SHA256,
    )
    if (
        raw_summary.get("status") != "COMPLETE"
        or raw_summary.get("cells_completed") != 400
        or raw_summary.get("strategy_versions_created") != 0
        or raw_summary.get("development_or_consumed_loaded") is not False
        or raw_summary.get("paper_activation") is not False
        or raw_summary.get("order_route") != "FORBIDDEN"
    ):
        raise RuntimeError("DAILY_PRICE_STATE_OUTPUT_CONTRACT_INVALID")

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
