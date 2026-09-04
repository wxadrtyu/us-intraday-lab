"""Run the parity-proven v11098 strategy on Alpaca Paper only."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path

import pandas as pd

from scripts.run_v449_alpaca_paper import _entry_window_open, _target_complete
from scripts.v11098_live_frame_adapter import (
    feature_cube_from_bars,
    load_contract,
    signals_for_session,
)
from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker
from us_intraday_lab.paper.pool import V11098_ID
from us_intraday_lab.paper.v449 import (
    SleeveSignal,
    V449PaperController,
    V449PaperLedger,
    ny_bar_time,
    wait_until,
)
from us_intraday_lab.research_shadow_alpaca import NEW_YORK, AlpacaIexHistory
from us_intraday_lab.v45_research_shadow import SYMBOLS

ENTRY_BARS = (3, 11, 12, 18, 24, 42)
MANAGED_SLEEVES = ("opening", "anchor") + tuple(f"f{index}" for index in range(10))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("state/paper/v11098.sqlite3"))
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("research/results/2026-09-03-v11098-forward-contract.json"),
    )
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def _fetch_until_complete(history, *, base, session_date, through_bar, deadline):
    session_open = datetime.combine(session_date, wall_time(9, 30), NEW_YORK)
    while datetime.now(UTC) <= deadline.astimezone(UTC):
        if base is None:
            start = session_open - timedelta(days=100)
            retained = pd.DataFrame()
        else:
            start = session_open
            localized = pd.to_datetime(base["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
            retained = base.loc[localized.dt.date < session_date]
        current = history.fetch(
            symbols=SYMBOLS, start=start, end=datetime.now(UTC) + timedelta(seconds=1)
        )
        combined = (
            current
            if retained.empty
            else pd.concat((retained, current), ignore_index=True).drop_duplicates(
                ["symbol", "timestamp"], keep="last"
            )
        )
        if _target_complete(combined, session_date, through_bar):
            return combined.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        wait_until(min(deadline, datetime.now(NEW_YORK) + timedelta(seconds=5)))
    raise RuntimeError(f"IEX_TARGET_BARS_INCOMPLETE_THROUGH_{through_bar}")


def _sleeve_name(leg, fill_index):
    return "opening" if leg.sleeve == "opening" else "anchor" if leg.sleeve == "anchor" else f"f{fill_index}"


def main() -> int:
    arguments = _args()
    broker = AlpacaPaperBroker.from_environment()
    ledger = V449PaperLedger(arguments.ledger.resolve())
    controller = V449PaperController(
        broker=broker,
        ledger=ledger,
        candidate_id=V11098_ID,
        strategy_code="v11098",
        account_fraction=1.0,
        managed_strategy_codes=("v11098", "pool"),
        managed_sleeves=MANAGED_SLEEVES,
    )
    clock = broker.clock()
    if arguments.preflight:
        print({"endpoint": broker.endpoint, "market_open": clock.is_open, "positions": len(broker.positions()), "open_orders": len(broker.open_orders()), "active_strategy": "v11098"})
        return 0
    now = datetime.now(UTC)
    opening = now if clock.is_open else clock.next_open
    if not clock.is_open and opening - now > timedelta(hours=10):
        print({"status": "SKIPPED", "reason": "NEXT_OPEN_MORE_THAN_10_HOURS_AWAY"})
        return 0
    session_date = opening.astimezone(NEW_YORK).date()
    controller.startup_check(session_date)
    contract = load_contract(arguments.contract)
    history = AlpacaIexHistory.from_environment()
    bars = None
    entered: dict[str, int] = {}
    for entry_bar in ENTRY_BARS:
        eligible = ny_bar_time(session_date, entry_bar)
        wait_until(eligible)
        if not _entry_window_open(datetime.now(UTC), eligible):
            ledger.append(event_key=f"{session_date}:entry-{entry_bar}:late", session_date=session_date, event_type="SKIP", payload={"reason": "ENTRY_WINDOW_MISSED", "entry_bar": entry_bar})
            continue
        try:
            bars = _fetch_until_complete(history, base=bars, session_date=session_date, through_bar=entry_bar - 1, deadline=eligible + timedelta(minutes=2))
            cube = feature_cube_from_bars(bars)
            legs = signals_for_session(cube, contract, session_date)
        except Exception as error:  # noqa: BLE001 - preserve later exits after data failure
            ledger.append(event_key=f"{session_date}:entry-{entry_bar}:data-incident", session_date=session_date, event_type="INCIDENT", payload={"reason": "V11098_DATA_OR_SIGNAL_FAILURE", "entry_bar": entry_bar, "error_type": type(error).__name__, "error": str(error)[:300]})
            continue
        fill_index = 0
        for leg in legs:
            if leg.entry_bar != entry_bar:
                if leg.sleeve == "fill":
                    fill_index += 1
                continue
            sleeve = _sleeve_name(leg, fill_index)
            if leg.sleeve == "fill":
                fill_index += 1
            signal = SleeveSignal(sleeve=sleeve, symbol=leg.symbol, decision_bar=leg.decision_bar, exit_bar=leg.exit_bar, weight=leg.weight, exposure=leg.exposure)
            ledger.append(event_key=f"{session_date}:v11098:{sleeve}:signal", session_date=session_date, event_type="SIGNAL", payload={"candidate_id": V11098_ID, "symbol": leg.symbol, "entry_bar": leg.entry_bar, "exit_bar": leg.exit_bar, "weight": leg.weight, "exposure": leg.exposure, "route": leg.parent_id})
            localized = pd.to_datetime(bars["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
            target = bars.loc[(bars["symbol"] == leg.symbol) & (localized.dt.date == session_date)]
            controller.enter(session_date=session_date, signal=signal, reference_price=float(target.iloc[-1]["close"]), now=datetime.now(UTC))
            entered[sleeve] = leg.exit_bar
    for exit_bar in sorted(set(entered.values())):
        wait_until(ny_bar_time(session_date, exit_bar))
        for sleeve, target_exit in entered.items():
            if target_exit == exit_bar:
                controller.exit_sleeve(session_date=session_date, sleeve=sleeve, now=datetime.now(UTC))
    wait_until(datetime.combine(session_date, wall_time(15, 59), NEW_YORK))
    controller.emergency_flatten(session_date=session_date, now=datetime.now(UTC))
    if broker.positions():
        raise RuntimeError("V11098_PAPER_CLOSEOUT_POSITION_REMAINS")
    print({"status": "CLOSED", "session_date": session_date.isoformat(), "strategy": "v11098"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
