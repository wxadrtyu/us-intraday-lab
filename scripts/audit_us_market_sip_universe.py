from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from us_intraday_lab.data.monthly_universe import monthly_cutoffs
from us_intraday_lab.data.sip_universe_audit import audit_sip_universe


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _daily_frame(path: Path) -> pd.DataFrame:
    shards = sorted(path.glob("*.parquet"))
    if not shards:
        return pd.DataFrame(columns=["symbol", "session_date", "volume"])
    connection = duckdb.connect()
    try:
        return connection.execute(
            """
            SELECT upper(symbol) AS symbol, CAST(timestamp AS DATE) AS session_date,
                   max(volume) AS volume
            FROM read_parquet(?, union_by_name = true)
            GROUP BY 1, 2
            """,
            [(path / "*.parquet").as_posix()],
        ).fetch_df()
    finally:
        connection.close()


def _validate_shards(path: Path) -> tuple[bool, int]:
    partials = len(list(path.glob("*.tmp"))) + len(list(path.glob("*.tmp.parquet")))
    hashes_valid = True
    for manifest_path in path.glob("*.json"):
        record = json.loads(manifest_path.read_text("utf-8"))
        parquet = manifest_path.with_suffix(".parquet")
        if not parquet.is_file() or record.get("content_sha256") != _sha256_file(parquet):
            hashes_valid = False
    return hashes_valid, partials


def _select_universe(root: Path, start_month: date, end_month: date) -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for manifest_path in (
        root / "data" / "catalog" / "monthly_universe_sip_v1"
    ).glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if (
            manifest.get("start_month") == start_month.isoformat()
            and manifest.get("end_month") == end_month.isoformat()
        ):
            candidates.append((manifest_path.parent, manifest))
    if len(candidates) != 1:
        raise RuntimeError(f"expected exactly one matching SIP universe, found {len(candidates)}")
    return candidates[0]


def _markdown(result: dict[str, Any]) -> str:
    permitted = "YES" if result["strategy_metrics_permitted"] else "NO"
    reasons = result["rejection_reasons"] or ["none"]
    return "\n".join(
        [
            "# Alpaca SIP Full-Market Universe Audit",
            "",
            f"- Strategy metrics permitted: **{permitted}**",
            f"- SIP daily rows: {result['sip_daily_rows']:,}",
            f"- Observed months: {len(result['observed_months'])}",
            f"- Partial partitions: {result['partial_partitions']}",
            f"- Rejection reasons: {', '.join(reasons)}",
            "- Source rows spliced: 0",
            "- Missing data: preserved; never filled or treated as cash",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Alpaca SIP full-market universe readiness.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument("--start-month", default=date(2018, 4, 1), type=date.fromisoformat)
    parser.add_argument("--end-month", default=date(2026, 3, 1), type=date.fromisoformat)
    parser.add_argument("--independent-historical-master", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    universe_path, universe_manifest = _select_universe(root, args.start_month, args.end_month)
    decisions = pd.read_parquet(universe_path / "decisions.parquet", columns=["month"])
    expected = tuple(monthly_cutoffs(args.start_month, args.end_month)["month"])
    observed = tuple(sorted(pd.to_datetime(decisions["month"]).dt.date.unique()))
    sip_root = root / "data" / "staging" / "alpaca_sip_1day_v1"
    hashes_valid, partials = _validate_shards(sip_root)
    result = audit_sip_universe(
        expected_months=expected,
        observed_months=observed,
        sip_daily=_daily_frame(sip_root),
        iex_daily=_daily_frame(root / "data" / "staging" / "alpaca_iex_1day_v2"),
        independent_historical_master=args.independent_historical_master,
        hashes_valid=hashes_valid,
        partial_partitions=partials,
    )
    result["universe_dataset_id"] = universe_manifest["dataset_id"]
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    args.output_md.write_text(_markdown(result), "utf-8")
    print(json.dumps({"strategy_metrics_permitted": result["strategy_metrics_permitted"], "rejection_reasons": result["rejection_reasons"]}, sort_keys=True))


if __name__ == "__main__":
    main()
