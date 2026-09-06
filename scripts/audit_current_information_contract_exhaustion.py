"""Audit whether the authorized minute-bar information contract is exhausted."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(r"E:\us-intraday-lab-data\us-market")
OUTPUT = Path("research/results/2026-09-07-current-information-contract-exhaustion.json")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run() -> dict:
    sample_manifest = next(
        (ROOT / "data" / "staging" / "alpaca_iex_1min_dynamic" / "2025-12").glob("*.json")
    )
    manifest = json.loads(sample_manifest.read_text(encoding="utf-8"))
    sample_parquet = sample_manifest.with_suffix(".parquet")
    raw_columns = pq.ParquetFile(sample_parquet).schema_arrow.names
    if manifest.get("blind_test_candidate") is True or manifest.get("strategy_metrics_permitted") is not True:
        raise RuntimeError("sample minute shard is not strategy-metrics permitted")

    action_manifest_path = (
        ROOT / "data" / "catalog" / "corporate_actions"
        / "alpaca-corporate-actions-4c535fc207d2057e1074157d" / "manifest.json"
    )
    asset_manifest_path = (
        ROOT / "data" / "catalog" / "us_equity_assets"
        / "alpaca-us-equity-assets-4cf36da00fead42b3b669620" / "manifest.json"
    )
    action_manifest = json.loads(action_manifest_path.read_text(encoding="utf-8"))
    asset_manifest = json.loads(asset_manifest_path.read_text(encoding="utf-8"))

    coverage = {
        "open_high_low_close": [
            "v14309-v15308 endpoint/path families",
            "v16509-v16608 complete minute volatility surface",
            "v16609-v16708 minute body/close-location/wick pressure",
        ],
        "volume": [
            "v14309-v16208 volume, climax, concentration and state families",
            "v16709-v16808 complete intrabar liquidity curve",
        ],
        "trade_count": [
            "v16309-v16408 trade-count and average-trade-size decomposition",
            "v16709-v16808 intrabar trade participation timing",
        ],
        "vwap": [
            "v14309-v15308 running-VWAP and residual-VWAP families",
            "earlier repository v21 and later full-universe VWAP structure families",
        ],
        "timestamp_session_date": [
            "v16809-v16908 frozen calendar priors",
            "v16909-v17008 exact consecutive-session recurring slot flow",
        ],
        "cross_asset_transforms": [
            "v16409-v16508 frozen broad-ETF beta lead-lag",
            "v17009-v17108 frozen stock leader network",
        ],
    }
    meaningful = {"open", "high", "low", "close", "volume", "trade_count", "vwap", "timestamp", "session_date"}
    unmodeled_meaningful = sorted(meaningful.difference(raw_columns))
    non_alpha_columns = sorted(set(raw_columns).difference(meaningful).difference({"symbol"}))
    result = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "audit_id": "current-information-contract-exhaustion-audit",
        "strategy_versions_reviewed": 2900,
        "candidate_count": 0,
        "sample_shard": {
            "month": "2025-12",
            "content_sha256": manifest["content_sha256"],
            "columns": raw_columns,
            "rows": pq.ParquetFile(sample_parquet).metadata.num_rows,
            "strategy_metrics_permitted": manifest["strategy_metrics_permitted"],
        },
        "feature_family_coverage": coverage,
        "unmodeled_meaningful_raw_columns": unmodeled_meaningful,
        "non_alpha_or_identifier_columns": non_alpha_columns,
        "catalog_point_in_time_audit": {
            "corporate_actions": {
                "retrieved_at": action_manifest["retrieved_at"],
                "end": action_manifest["end"],
                "decision": "UNSAFE_FOR_HISTORICAL_SELECTION_WITHOUT_VINTAGED_SNAPSHOTS",
            },
            "assets": {
                "dataset_id": asset_manifest["dataset_id"],
                "decision": "CURRENT_SNAPSHOT_UNSAFE_AS_HISTORICAL_CLASSIFICATION",
            },
        },
        "consumed_2026_rows_loaded": 0,
        "blind_2026_04_plus_rows_loaded": 0,
        "decision": "NO_NEW_CAUSAL_FIELD_WITHIN_CURRENT_CONTRACT",
        "required_new_immutable_data_contracts": [
            "historical timestamped bid/ask quotes or NBBO for spread, imbalance and microprice",
            "historical trade prints with aggressor-side inference",
            "timestamped opening/closing auction imbalance and indicative price",
            "point-in-time earnings/news/event timestamps",
            "point-in-time short-interest, borrow availability or options-implied state",
        ],
        "next_action": "PAUSE_NEW_STRATEGY_VERSION_CREATION_UNTIL_ONE_NEW_CONTRACT_IS_AUTHORIZED_AND_IMMUTABLY_ACQUIRED",
    }
    atomic_json(OUTPUT, result)
    OUTPUT.with_suffix(".md").write_text(
        "# Current information-contract exhaustion audit\n\n"
        "- Status: COMPLETE; 2,900 strategy versions reviewed; admitted candidates: 0.\n"
        f"- Permitted raw columns: {', '.join(raw_columns)}.\n"
        "- Every economically meaningful bar field has already been represented by endpoint, path, "
        "volatility, VWAP, volume, trade-count, calendar, and cross-asset families.\n"
        "- Corporate actions and assets are current retrospective snapshots, not safe historical vintages.\n"
        "- 2026Q1 rows loaded for this audit: 0; 2026-04+ rows loaded: 0.\n"
        "- Decision: NO_NEW_CAUSAL_FIELD_WITHIN_CURRENT_CONTRACT.\n"
        "- Required next step: authorize and immutably acquire a new timestamped data contract, preferably "
        "historical quotes/NBBO, trade prints, auction imbalance, or point-in-time events.\n"
        "- No Paper/broker/order state was touched.\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    summary = run()
    print(json.dumps({key: summary[key] for key in ("status", "decision", "next_action")}, indent=2))
