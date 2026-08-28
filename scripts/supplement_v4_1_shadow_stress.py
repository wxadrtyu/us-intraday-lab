"""Read-only execution diagnostics for an immutable existing v4.1 observation.

Print a supplemental report; never update or insert a shadow observation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from us_intraday_lab.research_shadow_alpaca import NEW_YORK, _at, _minute_index
from us_intraday_lab.research_shadow_twelvedata import TwelveDataHistory


def evaluate(bars: pd.DataFrame, observation: dict) -> dict:
    signals = observation["signals"]
    parameters = observation["parameters"]
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["minute_index"] = _minute_index(frame["timestamp"])
    frame = frame.loc[
        frame["minute_index"].between(0, 389)
        & (
            frame["timestamp"].dt.tz_convert(NEW_YORK).dt.date.astype(str)
            == observation["session_date"]
        )
    ]
    if frame.duplicated(["symbol", "minute_index"]).any():
        raise ValueError("duplicate supplemental minutes")
    results = {}
    for name, cost, delay in (
        ("standard_9bp_return", 0.0009, 0),
        ("cost_18bp_return", 0.0018, 0),
        ("delay_5min_9bp_return", 0.0009, 5),
    ):
        value = 0.0
        if signals["stock"]:
            stock = frame.loc[frame.symbol == signals["stock_symbol"]]
            if len(stock) < 385:
                raise ValueError("supplemental stock completeness failure")
            entry = _at(stock, 46 + delay, "open")
            path = stock.loc[stock.minute_index.between(46 + delay, 329)]
            raw = 0.02 if (path.high >= entry * 1.02).any() else _at(stock, 330, "open") / entry - 1
            value += 0.5 * (raw - cost)
        if signals["spy"]:
            spy = frame.loc[frame.symbol == "SPY"]
            if len(spy) != 390:
                raise ValueError("supplemental SPY completeness failure")
            raw = _at(spy, parameters["spy_exit_minute"], "open") / _at(spy, 31 + delay, "open") - 1
            value += 0.5 * (raw - cost)
        results[name] = value
    if abs(results["standard_9bp_return"] - observation["theoretical"]["strategy_return"]) > 1e-10:
        raise ValueError(
            "supplemental historical prices no longer reproduce stored standard return"
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    path = (args.root / "state" / "research_shadow.sqlite3").resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT observation_json,content_sha256 FROM research_shadow_observations "
            "WHERE campaign_id=? AND session_date=?",
            (args.campaign_id, args.session_date.isoformat()),
        ).fetchone()
    if row is None:
        raise ValueError("supplement requires an existing immutable observation")
    observation = json.loads(row[0])
    if observation["provider"] != "twelve_data":
        raise ValueError("supplement provider mismatch")
    symbols = []
    if observation["signals"]["stock"]:
        symbols.append(observation["signals"]["stock_symbol"])
    if observation["signals"]["spy"]:
        symbols.append("SPY")
    start = datetime.combine(args.session_date, time(), NEW_YORK)
    bars = (
        TwelveDataHistory.from_environment().fetch(
            symbols=tuple(symbols),
            start=start.astimezone(UTC),
            end=(start + timedelta(days=1)).astimezone(UTC),
        )
        if symbols
        else pd.DataFrame(columns=["timestamp", "symbol", "open", "high"])
    )
    result = evaluate(bars, observation)
    print(
        json.dumps(
            {
                "campaign_id": args.campaign_id,
                "session_date": args.session_date.isoformat(),
                "supplemental_report_only": True,
                "observation_content_sha256": row[1],
                "provider": "twelve_data",
                "signals": observation["signals"],
                "source_bars_sha256": hashlib.sha256(
                    bars.to_json(date_format="iso").encode()
                ).hexdigest(),
                "stress_diagnostics": result,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
