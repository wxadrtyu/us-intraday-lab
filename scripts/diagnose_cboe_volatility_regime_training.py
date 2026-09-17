"""Run the frozen Cboe volatility-regime training feasibility diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import run_diagnostic


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
            raise RuntimeError(f"CBOE_DIAGNOSTIC_IMMUTABLE_COLLISION:{path}")
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
            "# Cboe Volatility-Regime Training Feasibility", "",
            f"- Status: **{summary['status']}**",
            f"- Decision: **{summary['decision']}**",
            f"- Training event rows: {summary['event_rows']:,}",
            f"- Fully covered rows: {summary['covered_event_rows']:,}",
            f"- Cells completed: {summary['cells_completed']:,}",
            f"- Retained cells: {summary['retained_cells']:,}",
            f"- Retained families: {families}",
            f"- Event SHA-256: `{summary['event_sha256']}`",
            f"- Feature SHA-256: `{summary['feature_sha256']}`",
            f"- Cell table SHA-256: `{summary['cells_sha256']}`",
            f"- Strategy versions created: **{summary['strategy_versions_created']}**",
            "- Development or consumed data loaded: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**", "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--expected-event-sha256", required=True)
    parser.add_argument("--expected-feature-sha256", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    arguments = parser.parse_args()
    cells, raw_summary = run_diagnostic(
        events_path=arguments.events, features_path=arguments.features,
        expected_event_sha256=arguments.expected_event_sha256,
        expected_feature_sha256=arguments.expected_feature_sha256,
    )
    _write_parquet_immutable(arguments.output_parquet, cells)
    summary = _json_safe({**raw_summary, "cells_sha256": _sha256(arguments.output_parquet)})
    _write_immutable(
        arguments.output_json,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode(),
    )
    _write_immutable(arguments.output_md, render_markdown(summary).encode())
    print(json.dumps({key: summary[key] for key in (
        "status", "decision", "cells_completed", "retained_cells",
        "retained_families", "elapsed_seconds",
    )}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
