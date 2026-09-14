from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from us_intraday_lab.data.polygon_historical_master import (
    POLYGON_REFERENCE_NAMESPACE,
    validate_historical_master,
)


def _write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text("utf-8") != content:
            raise ValueError(f"immutable audit collision: {path}")
        return
    path.write_text(content, encoding="utf-8")


def _symbols(values: Iterable[object]) -> set[str]:
    return {str(value).strip().upper() for value in values if str(value).strip()}


def compare_symbols(
    *, polygon: set[str], alpaca: set[str], decisions: set[str]
) -> dict[str, object]:
    polygon_symbols = _symbols(polygon)
    alpaca_symbols = _symbols(alpaca)
    decision_symbols = _symbols(decisions)
    return {
        "alpaca_asset_symbols_not_in_polygon": sorted(
            alpaca_symbols.difference(polygon_symbols)
        ),
        "polygon_symbols_not_in_alpaca_assets": sorted(
            polygon_symbols.difference(alpaca_symbols)
        ),
        "decision_symbols_not_in_polygon": sorted(
            decision_symbols.difference(polygon_symbols)
        ),
        "polygon_symbols": len(polygon_symbols),
        "alpaca_asset_symbols": len(alpaca_symbols),
        "decision_symbols": len(decision_symbols),
    }


def _polygon_symbols(root: Path) -> set[str]:
    source = (
        root.resolve()
        / "data"
        / "staging"
        / POLYGON_REFERENCE_NAMESPACE
        / "snapshots"
    )
    values: set[str] = set()
    for path in sorted(source.glob("asof=*/tickers.parquet")):
        values.update(_symbols(pd.read_parquet(path, columns=["ticker"])["ticker"]))
    return values


def _markdown(result: dict[str, Any]) -> str:
    permitted = "YES" if result["passed"] else "NO"
    reasons = result["rejection_reasons"] or ["none"]
    comparison = result["cross_source_comparison"]
    return "\n".join(
        [
            "# Polygon Historical Security Master Audit",
            "",
            f"- Validation passed: **{permitted}**",
            f"- Months: {result['months']}",
            f"- Raw pages: {result['raw_pages']:,}",
            f"- Canonical rows: {result['rows']:,}",
            f"- Active rows: {result['active_rows']:,}",
            f"- Inactive rows: {result['inactive_rows']:,}",
            f"- Partial files: {result['partial_files']}",
            f"- Rejection reasons: {', '.join(reasons)}",
            (
                "- Alpaca asset symbols absent from Polygon history: "
                f"{len(comparison['alpaca_asset_symbols_not_in_polygon']):,}"
            ),
            (
                "- Decision symbols absent from Polygon history: "
                f"{len(comparison['decision_symbols_not_in_polygon']):,}"
            ),
            "- Provider splicing: FORBIDDEN",
            "- Paper activation: false",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently audit Polygon historical security-master evidence."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    args = parser.parse_args()

    result = validate_historical_master(
        args.root, start=args.start, end=args.end
    )
    assets = pd.read_parquet(args.assets, columns=["symbol"])
    decisions = pd.read_parquet(args.decisions, columns=["symbol"])
    result["cross_source_comparison"] = compare_symbols(
        polygon=_polygon_symbols(args.root),
        alpaca=_symbols(assets["symbol"]),
        decisions=_symbols(decisions["symbol"]),
    )
    _write_immutable(
        args.output_json,
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
    )
    _write_immutable(args.output_md, _markdown(result))
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "months": result["months"],
                "rows": result["rows"],
                "rejection_reasons": result["rejection_reasons"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
