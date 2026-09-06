from __future__ import annotations

from datetime import date
from pathlib import Path

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd

from us_intraday_lab.data.monthly_universe import (
    build_monthly_universe,
    monthly_cutoffs,
)


def test_monthly_cutoff_is_the_prior_completed_session() -> None:
    cutoffs = monthly_cutoffs(date(2022, 1, 1), date(2022, 2, 1))

    assert cutoffs.to_dict("records") == [
        {"month": date(2022, 1, 1), "information_cutoff": date(2021, 12, 31)},
        {"month": date(2022, 2, 1), "information_cutoff": date(2022, 1, 31)},
    ]


def test_universe_uses_only_prior_sessions_and_fails_low_liquidity(tmp_path: Path) -> None:
    calendar = exchange_calendars.get_calendar("XNYS")
    cutoff = pd.Timestamp("2022-01-31")
    sessions = calendar.sessions_window(cutoff, -60)
    rows: list[dict[str, object]] = []
    for symbol, volume in (("LIQUID", 2_000_000.0), ("THIN", 100.0)):
        for session in sessions:
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": session,
                    "close": 10.0,
                    "volume": volume,
                }
            )
    daily_root = tmp_path / "data" / "staging" / "alpaca_iex_1day_v2"
    daily_root.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(daily_root / "part.parquet", index=False)

    manifest = build_monthly_universe(
        root=tmp_path,
        start_month=date(2022, 2, 1),
        end_month=date(2022, 2, 1),
    )
    decisions = pd.read_parquet(
        tmp_path
        / "data"
        / "catalog"
        / "monthly_universe"
        / str(manifest["dataset_id"])
        / "decisions.parquet"
    ).set_index("symbol")

    assert bool(decisions.loc["LIQUID", "eligible"])
    assert decisions.loc["LIQUID", "observed_sessions"] == 60
    assert not bool(decisions.loc["THIN", "eligible"])
    assert decisions.loc["THIN", "decision_reason"] == "liquidity_below_floor"
    assert manifest["uses_future_data"] is False
