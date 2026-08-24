"""Verify the live-frame v1254 state calculation against the research cube."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as research
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as source

from us_intraday_lab.paper.pool import V1254_STATE_STATS, v1254_state_score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sessions", type=int, default=5)
    args = parser.parse_args()
    cube = research.v53.Cube(args.root, "alpaca", 0)
    matrix = research._state_matrix(cube, "prior_close")
    paths = source._verified_paths(args.root, "alpaca")
    connection = duckdb.connect()
    selected_indexes = list(range(len(cube.sessions) - args.sessions, len(cube.sessions)))
    if len(selected_indexes) != args.sessions:
        raise RuntimeError("V1254_PAPER_FACTOR_PARITY_INSUFFICIENT_COMPLETE_SESSIONS")
    selected_dates = sorted(
        {
            pd.Timestamp(cube.sessions[index - offset]).date()
            for index in selected_indexes
            for offset in (0, 1)
        }
    )
    all_bars = connection.execute(
        """
        SELECT symbol, timestamp, open, high, low, close, volume
        FROM read_parquet(?)
        WHERE CAST(timezone('America/New_York', timestamp) AS DATE) = ANY(?)
        ORDER BY timestamp, symbol
        """,
        [paths, selected_dates],
    ).fetch_df()
    localized_dates = pd.to_datetime(all_bars["timestamp"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.date
    records = []
    for index in selected_indexes:
        target = pd.Timestamp(cube.sessions[index]).date()
        prior = pd.Timestamp(cube.sessions[index - 1]).date()
        bars = all_bars.loc[localized_dates.isin((prior, target))].copy()
        observed = v1254_state_score(bars, session_date=target)
        pieces = [
            direction * (float(matrix[name][index]) - mean) / scale
            for name, (mean, scale, direction) in V1254_STATE_STATS.items()
        ]
        expected = float(np.mean(pieces))
        records.append(
            {
                "session_date": target.isoformat(),
                "observed": observed,
                "expected": expected,
                "absolute_error": abs(observed - expected),
            }
        )
    passed = all(record["absolute_error"] < 1e-12 for record in records)
    print(json.dumps({"passed": passed, "records": records}, indent=2))
    if not passed:
        raise RuntimeError("V1254_PAPER_FACTOR_PARITY_FAILED")


if __name__ == "__main__":
    main()
