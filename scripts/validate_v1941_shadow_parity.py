"""Compare frozen live state with the original research cube; no parameter selection."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb
import evaluate_full_universe_intraday_v1865_v1964_risk_overlay as risk
import numpy as np
import pandas as pd

from us_intraday_lab.v1941_research_shadow import MEANS, SCALES, THRESHOLD, frozen_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    cube = risk.prior.v53.Cube(args.root, "alpaca", 0)
    matrix = risk.prior._state_matrix(cube, "bar17")
    scores = risk.prior._state_score(matrix, dict.fromkeys(MEANS, 1), MEANS, SCALES)
    selected = [
        i
        for i, d in enumerate(cube.dates)
        if str(d.date()) == "2024-08-07" or d >= pd.Timestamp("2026-08-01")
    ]
    paths = risk.prior.v12._verified_paths(args.root, "alpaca")
    dates = [str(cube.dates[i].date()) for i in selected]
    connection = duckdb.connect()
    frame = connection.execute(
        "SELECT symbol,timestamp,open,high,low,close,volume,session_date "
        "FROM read_parquet(?) WHERE cast(session_date as varchar) IN (SELECT unnest(?))",
        [paths, dates],
    ).fetch_df()
    observations = []
    for i in selected:
        session = cube.dates[i].date()
        observed = frozen_state(
            frame.loc[pd.to_datetime(frame.session_date).dt.date == session], session
        )
        for name in MEANS:
            np.testing.assert_allclose(
                observed["factors"][name] if observed["factors"][name] is not None else np.nan,
                matrix[name][i],
                atol=1e-12,
                rtol=1e-12,
            )
        np.testing.assert_allclose(
            observed["score"] if observed["score"] is not None else np.nan,
            scores[i],
            atol=1e-12,
            rtol=1e-12,
        )
        expected = (0.9 if scores[i] >= THRESHOLD else 0.45) if np.isfinite(scores[i]) else 0
        assert observed["budget_multiplier"] == expected
        observations.append({"session": str(session), "budget": expected})
    print(
        json.dumps(
            {
                "status": "PASS",
                "sessions": len(selected),
                "observations": observations,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )
    )


if __name__ == "__main__":
    main()
