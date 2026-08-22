"""Independent late-session v449 Alpaca paper closeout safeguard."""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker
from us_intraday_lab.paper.v449 import V449PaperController, V449PaperLedger
from us_intraday_lab.research_shadow_alpaca import NEW_YORK


def main() -> int:
    now = datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    broker = AlpacaPaperBroker.from_environment()
    if not broker.clock().is_open or local.time() < time(15, 40):
        return 0
    ledger = V449PaperLedger(Path("state/paper/v449_alpaca.sqlite3").resolve())
    controller = V449PaperController(broker=broker, ledger=ledger)
    controller.emergency_flatten(session_date=local.date(), now=now)
    if broker.positions():
        raise RuntimeError("V449_EMERGENCY_CLOSEOUT_POSITION_REMAINS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
