from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from us_intraday_lab.news_training_feasibility import run_diagnostic

EVENT_SHA256 = "399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9"
FEATURE_SHA256 = "d5b83060c7bb5e8cc4d97192e1df2518e3313b269b3591d5715f5fc88180b209"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            raise RuntimeError(f"NEWS_DIAGNOSTIC_IMMUTABLE_COLLISION:{path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _write_parquet_immutable(path: Path, cells: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    cells.to_parquet(temporary, index=False, compression="zstd")
    try:
        _write_immutable(path, temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)


def render_markdown(summary: dict[str, Any]) -> str:
    families = ", ".join(summary["retained_families"]) or "none"
    return "\n".join(
        [
            "# Point-in-Time News Training Feasibility",
            "",
            f"- Status: **{summary['status']}**",
            f"- Decision: **{summary['decision']}**",
            f"- Training event rows: {summary['event_rows']:,}",
            f"- Cells completed: {summary['cells_completed']:,}",
            f"- Retained cells: {summary['retained_cells']:,}",
            f"- Retained families: {families}",
            f"- Event SHA-256: `{summary['event_sha256']}`",
            f"- Feature SHA-256: `{summary['feature_sha256']}`",
            f"- Cell table SHA-256: `{summary['cells_sha256']}`",
            f"- Strategy versions created: **{summary['strategy_versions_created']}**",
            "- Development or consumed news loaded: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen training-only point-in-time news diagnostic."
    )
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    args = parser.parse_args()
    cells, raw_summary = run_diagnostic(
        events_path=args.events,
        features_path=args.features,
        expected_event_sha256=EVENT_SHA256,
        expected_feature_sha256=FEATURE_SHA256,
    )
    _write_parquet_immutable(args.output_parquet, cells)
    summary = _json_safe(
        {
            **raw_summary,
            "cells_path": str(args.output_parquet.resolve()),
            "cells_sha256": _sha256(args.output_parquet),
        }
    )
    _write_immutable(
        args.output_json,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode(),
    )
    _write_immutable(args.output_md, render_markdown(summary).encode())
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "status",
                    "decision",
                    "cells_completed",
                    "retained_cells",
                    "retained_families",
                    "elapsed_seconds",
                )
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
