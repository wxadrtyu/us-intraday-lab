from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from us_intraday_lab.data.polygon_historical_master import (
    load_historical_master_validation,
)
from us_intraday_lab.data.sip_five_minute_audit import audit_sip_five_minute_files


def _write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text("utf-8") != content:
            raise ValueError(f"immutable audit collision: {path}")
        return
    path.write_text(content, "utf-8")


def _markdown(result: dict[str, Any]) -> str:
    permitted = "YES" if result["strategy_metrics_permitted"] else "NO"
    reasons = result["rejection_reasons"] or ["none"]
    return "\n".join(
        [
            "# Alpaca SIP Five-Minute Full-Market Audit",
            "",
            f"- Strategy metrics permitted: **{permitted}**",
            f"- Source rows: {result['rows']:,}",
            (
                "- Required-clock coverage: "
                f"{result['required_clock_coverage_ratio']:.6%}"
            ),
            f"- Rejection reasons: {', '.join(reasons)}",
            "- Source rows spliced: 0",
            "- Missing data: preserved; never filled or treated as cash",
            "",
        ]
    )


def _source_validation(path: Path) -> dict[str, int | bool]:
    payload = json.loads(path.read_text("utf-8"))
    validation = payload.get("source_validation", payload)
    if validation.get("passed") is False:
        raise RuntimeError("SIP_FIVE_MINUTE_SOURCE_VALIDATION_FAILED")
    partitions = int(validation.get("partitions", -1))
    rows = int(validation.get("rows", -1))
    if partitions != 15_246 or rows < 1:
        raise RuntimeError("SIP_FIVE_MINUTE_SOURCE_VALIDATION_INCOMPLETE")
    return {
        "partitions": partitions,
        "rows": rows,
        "request_grid_valid": validation.get("request_grid_valid") is True,
        "partition_pairing_valid": validation.get("partition_pairing_valid") is True,
        "content_hashes_valid": validation.get("content_hashes_valid") is True,
        "partial_partitions": int(validation.get("partial_partitions", -1)),
    }


def _historical_master_validation(path: Path) -> dict[str, object]:
    return load_historical_master_validation(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Alpaca SIP five-minute full-market readiness."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--source-validation", required=True, type=Path)
    parser.add_argument(
        "--historical-master-validation", required=True, type=Path
    )
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument("--start", default=date(2018, 4, 1), type=date.fromisoformat)
    parser.add_argument("--end", default=date(2026, 3, 31), type=date.fromisoformat)
    args = parser.parse_args()

    calendar = xcals.get_calendar("XNYS")
    expected_sessions = tuple(
        session.date()
        for session in calendar.sessions_in_range(
            pd.Timestamp(args.start), pd.Timestamp(args.end)
        )
    )
    historical_master = _historical_master_validation(
        args.historical_master_validation.resolve()
    )
    result = audit_sip_five_minute_files(
        bars_glob=(
            args.root.resolve()
            / "data"
            / "staging"
            / "alpaca_sip_5min_v1"
            / "*.parquet"
        ).as_posix(),
        decisions_path=args.decisions.resolve(),
        assets_path=args.assets.resolve(),
        expected_sessions=expected_sessions,
        historical_master_validated=True,
        source_validation=_source_validation(args.source_validation.resolve()),
    )
    result["historical_master_source_namespace"] = historical_master[
        "source_namespace"
    ]
    result["historical_master_validation_report_sha256"] = historical_master[
        "validation_report_sha256"
    ]
    _write_immutable(
        args.output_json,
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
    )
    _write_immutable(args.output_md, _markdown(result))
    print(
        json.dumps(
            {
                "strategy_metrics_permitted": result["strategy_metrics_permitted"],
                "required_clock_coverage_ratio": result[
                    "required_clock_coverage_ratio"
                ],
                "rejection_reasons": result["rejection_reasons"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
