"""One-session, explicitly authorized v11098 Alpaca Paper catch-up runner."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from scripts.run_v11098_alpaca_paper import MANAGED_SLEEVES, _sleeve_name, _target_complete
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

CONTRACT = Path("research/results/2026-09-03-v11098-forward-contract.json")
LEDGER = Path("state/paper/v11098.sqlite3")


def _last_complete_bar(local: datetime) -> int:
    session_open = datetime.combine(local.date(), time(9, 30), NEW_YORK)
    return min(77, int((local - session_open).total_seconds() // 300) - 1)


def main() -> int:
    broker = AlpacaPaperBroker.from_environment()
    clock = broker.clock()
    now = datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    if not clock.is_open:
        raise RuntimeError("V11098_CATCH_UP_REQUIRES_OPEN_MARKET")
    session_date = local.date()
    through_bar = _last_complete_bar(local)
    if through_bar < 23:
        raise RuntimeError("V11098_CATCH_UP_ROUTE_NOT_YET_RESOLVED")
    ledger = V449PaperLedger(LEDGER.resolve())
    controller = V449PaperController(
        broker=broker,
        ledger=ledger,
        candidate_id=V11098_ID,
        strategy_code="v11098",
        account_fraction=1.0,
        managed_strategy_codes=("v11098", "pool"),
        managed_sleeves=MANAGED_SLEEVES,
    )
    controller.startup_check(session_date)
    history = AlpacaIexHistory.from_environment()
    session_open = datetime.combine(session_date, time(9, 30), NEW_YORK)
    bars = history.fetch(
        symbols=SYMBOLS,
        start=session_open - timedelta(days=100),
        end=now + timedelta(seconds=1),
    )
    if not _target_complete(bars, session_date, through_bar):
        raise RuntimeError(f"IEX_CATCH_UP_BARS_INCOMPLETE_THROUGH_{through_bar}")
    cube = feature_cube_from_bars(bars)
    contract = load_contract(CONTRACT)
    legs = signals_for_session(cube, contract, session_date)
    entered: dict[str, int] = {}
    fill_index = 0
    localized = pd.to_datetime(bars["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
    for leg in legs:
        sleeve = _sleeve_name(leg, fill_index)
        if leg.sleeve == "fill":
            fill_index += 1
        if leg.entry_bar > through_bar + 1 or ny_bar_time(session_date, leg.exit_bar) <= now:
            continue
        signal = SleeveSignal(
            sleeve=sleeve,
            symbol=leg.symbol,
            decision_bar=leg.decision_bar,
            exit_bar=leg.exit_bar,
            weight=leg.weight,
            exposure=leg.exposure,
        )
        target = bars.loc[(bars["symbol"] == leg.symbol) & (localized.dt.date == session_date)]
        ledger.append(
            event_key=f"{session_date}:v11098:{sleeve}:catch-up-signal",
            session_date=session_date,
            event_type="SIGNAL",
            payload={
                "candidate_id": V11098_ID,
                "explicit_user_catch_up": True,
                "original_entry_bar": leg.entry_bar,
                "catch_up_after_bar": through_bar,
                "exit_bar": leg.exit_bar,
                "symbol": leg.symbol,
                "weight": leg.weight,
                "exposure": leg.exposure,
                "route": leg.parent_id,
            },
        )
        controller.enter(
            session_date=session_date,
            signal=signal,
            reference_price=float(target.iloc[-1]["close"]),
            now=datetime.now(UTC),
        )
        entered[sleeve] = leg.exit_bar
    print(
        {
            "status": "CATCH_UP_SUBMITTED",
            "session_date": session_date.isoformat(),
            "through_bar": through_bar,
            "entered": entered,
        },
        flush=True,
    )
    for exit_bar in sorted(set(entered.values())):
        wait_until(ny_bar_time(session_date, exit_bar))
        for sleeve, target_exit in entered.items():
            if target_exit == exit_bar:
                controller.exit_sleeve(
                    session_date=session_date, sleeve=sleeve, now=datetime.now(UTC)
                )
    wait_until(datetime.combine(session_date, time(15, 59), NEW_YORK))
    controller.emergency_flatten(session_date=session_date, now=datetime.now(UTC))
    if broker.positions():
        raise RuntimeError("V11098_CATCH_UP_CLOSEOUT_POSITION_REMAINS")
    print({"status": "CATCH_UP_CLOSED", "session_date": session_date.isoformat()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
