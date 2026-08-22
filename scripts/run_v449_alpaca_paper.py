"""Run the frozen v247/v449 allocation on one Alpaca Paper account."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path

import pandas as pd

from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker
from us_intraday_lab.paper.pool import (
    POOL_ALLOCATIONS,
    V247_ID,
    V449_ID,
    v247_signals_at,
    validate_pool_allocations,
)
from us_intraday_lab.paper.v449 import (
    COMPONENT_EXIT,
    EXIT_BAR,
    V449PaperController,
    V449PaperLedger,
    ny_bar_time,
    signals_at,
    wait_until,
)
from us_intraday_lab.research_shadow_alpaca import NEW_YORK, AlpacaIexHistory
from us_intraday_lab.v45_research_shadow import SYMBOLS

ENTRY_DECISIONS = (23, 26, 29)
MAX_ENTRY_LATENESS = timedelta(minutes=2)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("state/paper/v247_v449_pool.sqlite3"))
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def _target_complete(frame: pd.DataFrame, session_date: date, through_bar: int) -> bool:
    localized = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
    target = frame.loc[localized.dt.date == session_date].copy()
    target["minute"] = (localized.loc[target.index].dt.hour - 9) * 60 + localized.loc[
        target.index
    ].dt.minute - 30
    required = set(range((through_bar + 1) * 5))
    return all(
        required.issubset(set(target.loc[target["symbol"] == symbol, "minute"].astype(int)))
        for symbol in SYMBOLS
    )


def _fetch_until_complete(
    history: AlpacaIexHistory,
    *,
    base: pd.DataFrame | None,
    session_date: date,
    through_bar: int,
    deadline: datetime,
) -> pd.DataFrame:
    session_open = datetime.combine(session_date, wall_time(9, 30), NEW_YORK)
    while datetime.now(UTC) <= deadline.astimezone(UTC):
        if base is None:
            start = session_open - timedelta(days=75)
            retained = pd.DataFrame()
        else:
            start = session_open
            localized = pd.to_datetime(base["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
            retained = base.loc[localized.dt.date < session_date]
        current = history.fetch(
            symbols=SYMBOLS,
            start=start,
            end=datetime.now(UTC) + timedelta(seconds=1),
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
        time.sleep(5)
    raise RuntimeError(f"IEX_TARGET_BARS_INCOMPLETE_THROUGH_{through_bar}")


def main() -> int:
    arguments = _args()
    validate_pool_allocations()
    broker = AlpacaPaperBroker.from_environment()
    ledger = V449PaperLedger(arguments.ledger.resolve())
    controllers = {
        "v247": V449PaperController(
            broker=broker,
            ledger=ledger,
            candidate_id=V247_ID,
            strategy_code="v247",
            account_fraction=POOL_ALLOCATIONS[V247_ID],
            managed_strategy_codes=("v247", "v449"),
        ),
        "v449": V449PaperController(
            broker=broker,
            ledger=ledger,
            candidate_id=V449_ID,
            strategy_code="v449",
            account_fraction=POOL_ALLOCATIONS[V449_ID],
            managed_strategy_codes=("v247", "v449"),
        ),
    }
    clock = broker.clock()
    if arguments.preflight:
        print(
            {
                "endpoint": broker.endpoint,
                "market_open": clock.is_open,
                "next_open": clock.next_open.isoformat(),
                "positions": len(broker.positions()),
                "open_orders": len(broker.open_orders()),
            }
        )
        return 0
    now = datetime.now(UTC)
    opening = now if clock.is_open else clock.next_open
    if not clock.is_open and opening - now > timedelta(hours=10):
        print({"status": "SKIPPED", "reason": "NEXT_OPEN_MORE_THAN_10_HOURS_AWAY"})
        return 0
    session_date = opening.astimezone(NEW_YORK).date()
    controllers["v449"].startup_check(session_date)
    history = AlpacaIexHistory.from_environment()
    bars: pd.DataFrame | None = None
    for decision in ENTRY_DECISIONS:
        eligible = ny_bar_time(session_date, decision + 1)
        wait_until(eligible)
        if datetime.now(UTC) > (eligible + MAX_ENTRY_LATENESS).astimezone(UTC):
            ledger.append(
                event_key=f"{session_date}:decision-{decision}:late",
                session_date=session_date,
                event_type="SKIP",
                payload={"reason": "ENTRY_WINDOW_MISSED", "decision_bar": decision},
            )
            continue
        try:
            bars = _fetch_until_complete(
                history,
                base=bars,
                session_date=session_date,
                through_bar=decision,
                deadline=eligible + MAX_ENTRY_LATENESS,
            )
            strategy_signals = {
                "v247": v247_signals_at(
                    bars, session_date=session_date, decision_bar=decision
                ),
                "v449": signals_at(bars, session_date=session_date, decision_bar=decision),
            }
        except Exception as error:  # noqa: BLE001 - keep timed exits alive after data failure
            ledger.append(
                event_key=f"{session_date}:decision-{decision}:data-incident",
                session_date=session_date,
                event_type="INCIDENT",
                payload={
                    "reason": "DECISION_DATA_OR_FACTOR_FAILURE",
                    "decision_bar": decision,
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                },
            )
            continue
        for strategy_code, signals in strategy_signals.items():
            for signal in signals:
                signal_key = f"{session_date}:{strategy_code}:{signal.sleeve}:signal"
                ledger.append(
                    event_key=signal_key,
                    session_date=session_date,
                    event_type="SIGNAL",
                    payload={
                        "candidate_id": controllers[strategy_code].candidate_id,
                        "account_fraction": controllers[strategy_code].account_fraction,
                        "symbol": signal.symbol,
                        "decision_bar": signal.decision_bar,
                        "exit_bar": signal.exit_bar,
                        "weight": signal.weight,
                        "exposure": signal.exposure,
                    },
                )
                symbol_rows = bars.loc[bars["symbol"] == signal.symbol]
                localized = pd.to_datetime(symbol_rows["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
                target = symbol_rows.loc[
                    (localized.dt.date == session_date)
                    & (((localized.dt.hour - 9) * 60 + localized.dt.minute - 30) <= decision * 5 + 4)
                ]
                try:
                    controllers[strategy_code].enter(
                        session_date=session_date,
                        signal=signal,
                        reference_price=float(target.iloc[-1]["close"]),
                        now=datetime.now(UTC),
                    )
                except Exception as error:  # noqa: BLE001 - uncertain submit is reconciled by ID
                    ledger.append(
                        event_key=f"{session_date}:{strategy_code}:{signal.sleeve}:entry-incident",
                        session_date=session_date,
                        event_type="INCIDENT",
                        payload={
                            "reason": "ENTRY_SUBMISSION_UNCERTAIN",
                            "error_type": type(error).__name__,
                            "error": str(error)[:300],
                        },
                    )
    wait_until(ny_bar_time(session_date, COMPONENT_EXIT))
    try:
        for controller in controllers.values():
            controller.exit_sleeve(
                session_date=session_date, sleeve="component", now=datetime.now(UTC)
            )
    except Exception as error:  # noqa: BLE001 - anchor exit and closeout must still run
        ledger.append(
            event_key=f"{session_date}:component:exit-incident",
            session_date=session_date,
            event_type="INCIDENT",
            payload={"reason": "COMPONENT_EXIT_FAILURE", "error": str(error)[:300]},
        )
    wait_until(ny_bar_time(session_date, EXIT_BAR))
    try:
        for controller in controllers.values():
            controller.exit_sleeve(
                session_date=session_date, sleeve="anchor", now=datetime.now(UTC)
            )
    except Exception as error:  # noqa: BLE001 - emergency closeout must still run
        ledger.append(
            event_key=f"{session_date}:anchor:exit-incident",
            session_date=session_date,
            event_type="INCIDENT",
            payload={"reason": "ANCHOR_EXIT_FAILURE", "error": str(error)[:300]},
        )
    wait_until(datetime.combine(session_date, wall_time(15, 45), NEW_YORK))
    controllers["v449"].emergency_flatten(session_date=session_date, now=datetime.now(UTC))
    remaining = broker.positions()
    if remaining:
        raise RuntimeError("PAPER_POOL_CLOSEOUT_POSITION_REMAINS")
    print({"status": "CLOSED", "session_date": session_date.isoformat()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
