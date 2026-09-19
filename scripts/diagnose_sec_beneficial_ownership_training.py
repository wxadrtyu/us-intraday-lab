"""Run the frozen SEC beneficial-ownership training diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.diagnose_cboe_volatility_regime_training import (
    _json_safe,
    _sha256,
    _write_immutable,
    _write_parquet_immutable,
    render_markdown,
)
from us_intraday_lab.sec_beneficial_ownership_feasibility import run_diagnostic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-event-sha256", required=True)
    parser.add_argument("--expected-feature-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-parquet", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    arguments = parser.parse_args()
    cells, raw_summary = run_diagnostic(
        events_path=arguments.events,
        features_path=arguments.features,
        manifest_path=arguments.manifest,
        expected_event_sha256=arguments.expected_event_sha256,
        expected_feature_sha256=arguments.expected_feature_sha256,
        expected_manifest_sha256=arguments.expected_manifest_sha256,
    )
    _write_parquet_immutable(arguments.output_parquet, cells)
    summary = _json_safe(
        {**raw_summary, "cells_sha256": _sha256(arguments.output_parquet)}
    )
    _write_immutable(
        arguments.output_json,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode(),
    )
    markdown = render_markdown(summary).replace(
        "Cboe Volatility-Regime", "SEC Beneficial-Ownership Disclosure"
    )
    _write_immutable(arguments.output_md, markdown.encode())
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
