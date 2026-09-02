"""Compare live-DataFrame feature construction with the frozen research cube."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
from v11098_live_frame_adapter import feature_cube_from_bars

DECISIONS = (2, 5, 11, 17, 23, 41, 77)


def _recent_bars(root: Path, sessions: int):
    paths = v12._verified_paths(root, "alpaca")
    connection = duckdb.connect()
    try:
        dates = connection.execute(
            """
            SELECT DISTINCT session_date FROM read_parquet(?)
            WHERE symbol='SPY' ORDER BY session_date DESC LIMIT ?
            """,
            [paths, sessions],
        ).fetch_df()
        start = dates["session_date"].min()
        return connection.execute(
            """
            SELECT timestamp,symbol,open,high,low,close,volume
            FROM read_parquet(?) WHERE session_date >= ?
            ORDER BY timestamp,symbol
            """,
            [paths, start],
        ).fetch_df()
    finally:
        connection.close()


def validate(root: Path, sessions: int = 100) -> dict:
    bars = _recent_bars(root, sessions)
    live = feature_cube_from_bars(bars)
    comparisons = []
    maximum = 0.0
    mismatches = 0
    compared_sessions = None
    views = (
        ("sector", live, sector.SectorFlowLeadershipCube(root, "alpaca", 0)),
        ("parent", live._v11098_parent_cube, v34.Cube(root, "alpaca", 0)),
    )
    for view, live_view, reference in views:
        reference_index = {
            pd.Timestamp(day).date(): index for index, day in enumerate(reference.sessions)
        }
        left = np.asarray(
            [
                index
                for index in range(20, len(live_view.sessions))
                if pd.Timestamp(live_view.sessions[index]).date() in reference_index
            ]
        )
        if len(left) < 20:
            raise RuntimeError("V11098_INSUFFICIENT_COMMON_PARITY_SESSIONS")
        compared_sessions = (
            len(left) if compared_sessions is None else min(compared_sessions, len(left))
        )
        right = np.asarray(
            [reference_index[pd.Timestamp(live_view.sessions[index]).date()] for index in left]
        )
        for decision in DECISIONS:
            live_factors = live_view.factors(decision)
            reference_factors = reference.factors(decision)
            for name in sorted(live_factors.keys() & reference_factors.keys()):
                first = np.asarray(live_factors[name])[left]
                second = np.asarray(reference_factors[name])[right]
                finite_mismatch = np.isfinite(first) != np.isfinite(second)
                finite = np.isfinite(first) & np.isfinite(second)
                error = (
                    float(np.max(np.abs(first[finite] - second[finite]))) if finite.any() else 0.0
                )
                count = int(np.count_nonzero(finite_mismatch))
                maximum = max(maximum, error)
                mismatches += count
                comparisons.append(
                    {
                        "view": view,
                        "decision_bar": decision,
                        "factor": name,
                        "maximum_absolute_error": error,
                        "finite_mask_mismatches": count,
                    }
                )
    passed = maximum <= 1e-12 and mismatches == 0
    return {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if passed else "FAILED",
        "recent_sessions": len(live.sessions),
        "compared_sessions": compared_sessions,
        "decision_bars": list(DECISIONS),
        "factor_comparisons": len(comparisons),
        "maximum_absolute_error": maximum,
        "finite_mask_mismatches": mismatches,
        "passed": passed,
        "details": [
            item
            for item in comparisons
            if item["maximum_absolute_error"] > 1e-12 or item["finite_mask_mismatches"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sessions", default=100, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = validate(args.root, args.sessions)
    v12._atomic(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key != "details"}))
    if not result["passed"]:
        print(json.dumps({"details": result["details"][:20]}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
