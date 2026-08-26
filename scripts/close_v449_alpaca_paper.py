"""Independent late-session v247/v449/v798/v1254 Alpaca paper closeout safeguard."""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker
from us_intraday_lab.paper.pool import MANAGED_STRATEGY_CODES
from us_intraday_lab.paper.v449 import V449PaperController, V449PaperLedger
from us_intraday_lab.research_shadow_alpaca import NEW_YORK


def main() -> int:
    now = datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    broker = AlpacaPaperBroker.from_environment()
    if not broker.clock().is_open or local.time() < time(15, 40):
        return 0
    ledger = V449PaperLedger(Path("state/paper/v247_v449_pool.sqlite3").resolve())
    controller = V449PaperController(
        broker=broker,
        ledger=ledger,
        strategy_code="pool",
        managed_strategy_codes=MANAGED_STRATEGY_CODES,
    )
    controller.emergency_flatten(session_date=local.date(), now=now)
    if broker.positions():
        raise RuntimeError("PAPER_POOL_EMERGENCY_CLOSEOUT_POSITION_REMAINS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
