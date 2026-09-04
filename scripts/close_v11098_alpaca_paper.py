"""Independent v11098 Alpaca Paper closeout safeguard."""

from datetime import UTC, datetime, time
from pathlib import Path

from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker
from us_intraday_lab.paper.pool import V11098_ID
from us_intraday_lab.paper.v449 import V449PaperController, V449PaperLedger
from us_intraday_lab.research_shadow_alpaca import NEW_YORK


def main() -> int:
    now = datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    broker = AlpacaPaperBroker.from_environment()
    if not broker.clock().is_open or local.time() < time(15, 58):
        return 0
    controller = V449PaperController(
        broker=broker,
        ledger=V449PaperLedger(Path("state/paper/v11098.sqlite3").resolve()),
        candidate_id=V11098_ID,
        strategy_code="pool",
        managed_strategy_codes=("v11098", "pool"),
    )
    controller.emergency_flatten(session_date=local.date(), now=now)
    if broker.positions():
        raise RuntimeError("V11098_EMERGENCY_CLOSEOUT_POSITION_REMAINS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
