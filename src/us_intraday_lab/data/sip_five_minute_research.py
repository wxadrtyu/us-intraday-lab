"""Audit-gated, causal, read-only views over Alpaca SIP five-minute bars."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

_ROLE_BOUNDS = {
    "fit": (date(2022, 1, 1), date(2023, 12, 31)),
    "development_selection": (date(2024, 1, 1), date(2025, 12, 31)),
    "historical_stress_only": (date(2018, 1, 1), date(2020, 12, 31)),
    "consumed_diagnostic_only": (date(2026, 1, 1), date(2026, 3, 31)),
}
_CATALOG_CONTRACT = "causal-membership-cutoff-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sql_literal(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _load_audit(path: Path) -> tuple[dict[str, Any], str]:
    before = path.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    payload = json.loads(before)
    if not isinstance(payload, dict) or path.read_bytes() != before:
        raise RuntimeError("SIP_FIVE_MINUTE_AUDIT_HASH_MISMATCH")
    source = payload.get("source_validation", {})
    passed = (
        payload.get("strategy_metrics_permitted") is True
        and payload.get("historical_master_validated") is True
        and payload.get("rows_spliced") == 0
        and isinstance(source, dict)
        and source.get("request_grid_valid") is True
        and source.get("partition_pairing_valid") is True
        and source.get("content_hashes_valid") is True
        and source.get("partial_partitions") == 0
    )
    if not passed:
        raise RuntimeError("SIP_FIVE_MINUTE_AUDIT_BLOCKED")
    return payload, digest


def _decisions_path(root: Path) -> tuple[Path, str]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    catalog = root / "data" / "catalog" / "monthly_universe_sip_v2"
    for manifest_path in catalog.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if (
            manifest.get("start_month") == "2018-04-01"
            and manifest.get("end_month") == "2026-03-01"
        ):
            candidates.append((manifest_path.parent, manifest))
    if len(candidates) != 1:
        raise RuntimeError(f"SIP_FIVE_MINUTE_UNIVERSE_AMBIGUOUS:{len(candidates)}")
    directory, manifest = candidates[0]
    decisions = directory / "decisions.parquet"
    if not decisions.is_file() or manifest.get("content_sha256") != _sha256(decisions):
        raise RuntimeError("SIP_FIVE_MINUTE_UNIVERSE_HASH_MISMATCH")
    return decisions, str(manifest["dataset_id"])


def _build_catalog(
    *,
    path: Path,
    bars_glob: Path,
    decisions: Path,
    role: str,
    start: date,
    end: date,
    audit: dict[str, Any],
    audit_sha256: str,
    universe_id: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    connection = duckdb.connect(str(temporary))
    try:
        connection.execute(
            f"""
            CREATE VIEW _sip_five_minute_bars AS
            SELECT * FROM read_parquet(
                {_sql_literal(bars_glob.as_posix())}, union_by_name = true
            )
            """
        )
        connection.execute(
            f"""
            CREATE VIEW _sip_monthly_membership AS
            SELECT * FROM read_parquet({_sql_literal(decisions.as_posix())})
            """
        )
        connection.execute(
            f"""
            CREATE VIEW research_bars AS
            SELECT
                upper(b.symbol) AS symbol,
                b.timestamp,
                CAST(timezone('America/New_York', b.timestamp) AS DATE)
                    AS session_date,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
                b.trade_count,
                b.vwap,
                b.asof,
                b.provider,
                b.feed,
                TRUE AS available,
                d.eligible AS membership_eligible,
                d.information_cutoff,
                d.median_dollar_volume,
                d.decision_reason
            FROM _sip_five_minute_bars AS b
            INNER JOIN _sip_monthly_membership AS d
              ON upper(b.symbol) = upper(d.symbol)
             AND CAST(date_trunc(
                   'month',
                   CAST(timezone('America/New_York', b.timestamp) AS DATE)
                 ) AS DATE) = CAST(d.month AS DATE)
            WHERE d.eligible IS TRUE
              AND CAST(d.information_cutoff AS DATE)
                  < CAST(timezone('America/New_York', b.timestamp) AS DATE)
              AND CAST(timezone('America/New_York', b.timestamp) AS DATE)
                  BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'
            """
        )
        connection.execute(
            f"""
            CREATE VIEW research_metadata AS
            SELECT
                {_sql_literal(role)}::VARCHAR AS role,
                {_sql_literal(audit_sha256)}::VARCHAR AS audit_sha256,
                {_sql_literal(audit["historical_master_validation_report_sha256"])}
                    ::VARCHAR AS historical_master_validation_report_sha256,
                {_sql_literal(universe_id)}::VARCHAR AS universe_dataset_id,
                {_sql_literal(_CATALOG_CONTRACT)}::VARCHAR AS catalog_contract,
                0::INTEGER AS rows_spliced,
                TRUE AS source_read_only
            """
        )
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    try:
        if path.exists():
            temporary.unlink()
        else:
            temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def open_sip_five_minute_research_view(
    *, root: Path, audit_path: Path, role: str
) -> duckdb.DuckDBPyConnection:
    """Open a hash-addressed read-only view for one frozen causal date role."""
    if role not in _ROLE_BOUNDS:
        raise ValueError(f"SIP_FIVE_MINUTE_ROLE_INVALID:{role}")
    resolved_root = root.resolve()
    audit, audit_sha256 = _load_audit(audit_path.resolve())
    decisions, universe_id = _decisions_path(resolved_root)
    bars_root = resolved_root / "data" / "staging" / "alpaca_sip_5min_v1"
    if not next(bars_root.glob("*.parquet"), None):
        raise RuntimeError("SIP_FIVE_MINUTE_BARS_MISSING")

    start, end = _ROLE_BOUNDS[role]
    catalog = (
        resolved_root
        / "data"
        / "catalog"
        / "sip_five_minute_research_v1"
        / f"{_CATALOG_CONTRACT}-{audit_sha256}-{role}.duckdb"
    )
    if not catalog.exists():
        _build_catalog(
            path=catalog,
            bars_glob=bars_root / "*.parquet",
            decisions=decisions,
            role=role,
            start=start,
            end=end,
            audit=audit,
            audit_sha256=audit_sha256,
            universe_id=universe_id,
        )
    connection = duckdb.connect(str(catalog), read_only=True)
    metadata = connection.execute(
        """
        SELECT role, audit_sha256, universe_dataset_id, catalog_contract,
               rows_spliced, source_read_only
        FROM research_metadata
        """
    ).fetchone()
    expected = (role, audit_sha256, universe_id, _CATALOG_CONTRACT, 0, True)
    if metadata != expected:
        connection.close()
        raise RuntimeError("SIP_FIVE_MINUTE_RESEARCH_CATALOG_MISMATCH")
    access_mode = connection.execute("SELECT lower(current_setting('access_mode'))").fetchone()
    if access_mode != ("read_only",):
        connection.close()
        raise RuntimeError("SIP_FIVE_MINUTE_RESEARCH_CATALOG_NOT_READ_ONLY")
    return connection
