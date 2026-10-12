"""Run the frozen consumed-period full-market session-decomposition campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import pandas as pd

from us_intraday_lab.daily_technical_multifactor import (
    _daily_source_files,
    _file_sha256,
    _tree_sha256,
)
from us_intraday_lab.full_market_daily_multifactor import (
    attach_point_in_time_eligibility,
)
from us_intraday_lab.full_market_session_decomposition import (
    FAMILIES,
    LOOKBACKS,
    AtomicCheckpoint,
    RunIdentity,
    build_session_features,
    evaluate_cells_sequential,
    score_column,
    score_session_families,
    specifications,
)

DATA_ROOT = Path(r"E:\us-intraday-lab-data\us-market")
DAILY_ROOT = DATA_ROOT / "data" / "staging" / "alpaca_sip_1day_v2"
UNIVERSE_ROOT = (
    DATA_ROOT
    / "data"
    / "catalog"
    / "monthly_universe_sip_v2"
    / "us-market-monthly-universe-sip-v2-3dc89bc9ab09e193372b2071"
)
EXPECTED_DAILY_SHA256 = "0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701"
EXPECTED_UNIVERSE_SHA256 = "3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81"
EXPECTED_SOURCE_ROWS = 6_533_779
EXPECTED_SOURCE_SYMBOLS = 9_817
EXPECTED_SOURCE_SESSIONS = 881
EXPECTED_ELIGIBLE_SYMBOL_MONTHS = 81_774
EXPECTED_ELIGIBLE_SYMBOLS = 3_270


def _combined_sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(_file_sha256(path)))
    return digest.hexdigest()


def _load_daily(paths: list[Path]) -> pd.DataFrame:
    parquet_paths = [str(path) for path in paths if path.suffix == ".parquet"]
    connection = duckdb.connect()
    try:
        frame = connection.execute(
            """
            SELECT upper(symbol) AS symbol,
                   CAST(timestamp AS DATE) AS session_date,
                   open, high, low, close, volume, vwap, trade_count
            FROM read_parquet(?, union_by_name=true)
            WHERE CAST(timestamp AS DATE)
                  BETWEEN DATE '2020-07-01' AND DATE '2023-12-29'
            ORDER BY symbol, session_date
            """,
            [parquet_paths],
        ).df()
    finally:
        connection.close()
    observed = (len(frame), frame["symbol"].nunique(), frame["session_date"].nunique())
    expected = (EXPECTED_SOURCE_ROWS, EXPECTED_SOURCE_SYMBOLS, EXPECTED_SOURCE_SESSIONS)
    if observed != expected:
        raise RuntimeError(f"FULL_MARKET_SESSION_SOURCE_COUNTS_INVALID:{observed}")
    return frame


def _load_universe() -> pd.DataFrame:
    decisions_path = UNIVERSE_ROOT / "decisions.parquet"
    if _file_sha256(decisions_path) != EXPECTED_UNIVERSE_SHA256:
        raise RuntimeError("FULL_MARKET_SESSION_UNIVERSE_HASH_MISMATCH")
    universe = pd.read_parquet(decisions_path)
    universe["month"] = pd.to_datetime(universe["month"])
    training = universe.loc[
        universe["month"].between("2021-01-01", "2023-12-01")
        & universe["eligible"].eq(True)
    ]
    observed = (len(training), training["symbol"].nunique())
    expected = (EXPECTED_ELIGIBLE_SYMBOL_MONTHS, EXPECTED_ELIGIBLE_SYMBOLS)
    if observed != expected:
        raise RuntimeError(f"FULL_MARKET_SESSION_UNIVERSE_COUNTS_INVALID:{observed}")
    return universe


def prepare_panel() -> tuple[pd.DataFrame, dict[str, object]]:
    source_files = _daily_source_files(DAILY_ROOT)
    daily_sha256 = _tree_sha256(source_files)
    if daily_sha256 != EXPECTED_DAILY_SHA256:
        raise RuntimeError("FULL_MARKET_SESSION_SOURCE_HASH_MISMATCH")
    daily = _load_daily(source_files)
    universe = _load_universe()
    features = build_session_features(daily)
    eligible_bars = attach_point_in_time_eligibility(daily, universe)
    eligible_features = eligible_bars.loc[:, ["symbol", "session_date"]].merge(
        features,
        on=["symbol", "session_date"],
        how="left",
        validate="one_to_one",
    )
    scores = eligible_features.loc[:, ["symbol", "session_date"]].copy()
    for lookback in LOOKBACKS:
        scored = score_session_families(eligible_features, lookback)
        renamed = scored.rename(
            columns={family: score_column(family, lookback) for family in FAMILIES}
        )
        scores = scores.merge(
            renamed.loc[
                :, ["symbol", "session_date", *[score_column(f, lookback) for f in FAMILIES]]
            ],
            on=["symbol", "session_date"],
            how="left",
            validate="one_to_one",
        )
    outcomes = daily.loc[
        pd.to_datetime(daily["session_date"]).between("2021-01-01", "2023-12-31"),
        ["symbol", "session_date", "open", "close", "volume", "trade_count"],
    ]
    panel = outcomes.merge(
        scores,
        on=["symbol", "session_date"],
        how="left",
        validate="one_to_one",
    ).sort_values(["session_date", "symbol"], kind="stable", ignore_index=True)
    audit = {
        "daily_source_sha256": daily_sha256,
        "universe_sha256": EXPECTED_UNIVERSE_SHA256,
        "source_rows": len(daily),
        "source_symbols": int(daily["symbol"].nunique()),
        "source_sessions": int(daily["session_date"].nunique()),
        "panel_rows": len(panel),
        "panel_symbols": int(panel["symbol"].nunique()),
        "panel_sessions": int(panel["session_date"].nunique()),
        "consumed_period": True,
        "independent_oos": False,
    }
    return panel, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    result_root = workspace / "state" / "full-market-session-decomposition-v1"
    result_root.mkdir(parents=True, exist_ok=True)
    panel, source_audit = prepare_panel()
    panel.to_parquet(result_root / "panel.parquet", index=False, compression="zstd")
    design_path = (
        workspace
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-10-12-full-market-session-decomposition-design.md"
    )
    module_path = workspace / "src" / "us_intraday_lab" / "full_market_session_decomposition.py"
    dependency_path = workspace / "src" / "us_intraday_lab" / "full_market_daily_multifactor.py"
    script_path = Path(__file__).resolve()
    gate_payload = {
        "annualized_return_strictly_above": 0.40,
        "max_drawdown_below": 0.20,
        "information_ratio_at_least": 1.0,
        "z_score_at_least": 3.0,
        "positive_folds_at_least": 4,
        "folds": 5,
        "costs": [0.0009, 0.0018],
        "delay_sessions": 1,
        "neighborhood_share_at_least": 0.70,
        "bonferroni_at_most": 0.05,
        "native_max_t_repetitions": 500,
    }
    gate_sha256 = hashlib.sha256(
        json.dumps(gate_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity = RunIdentity(
        daily_source_sha256=EXPECTED_DAILY_SHA256,
        universe_sha256=EXPECTED_UNIVERSE_SHA256,
        design_sha256=_file_sha256(design_path),
        code_sha256=_combined_sha256((module_path, dependency_path, script_path)),
        gate_sha256=gate_sha256,
    )
    specs = specifications()
    checkpoint = AtomicCheckpoint.open(
        result_root / "checkpoint.json", identity, total_cells=len(specs)
    )
    records = evaluate_cells_sequential(panel, specs, checkpoint, result_root / "cells")
    summary = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "campaign": "full-market-session-decomposition-v1",
        "source_audit": source_audit,
        "identity": asdict(identity),
        "gate_policy": gate_payload,
        "cells_completed": len(records),
        "invalid_cells": sum(not bool(record["valid"]) for record in records),
        "basic_pre_null_passed": sum(
            bool(record["basic_pre_null_passed"]) for record in records
        ),
        "consumed_period": True,
        "independent_oos": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    output_root = workspace / "research" / "results"
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "2026-10-12-full-market-session-decomposition-cells.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    (output_root / "2026-10-12-full-market-session-decomposition-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()

