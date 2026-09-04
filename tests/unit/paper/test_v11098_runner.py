from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from scripts.run_v11098_alpaca_paper import ENTRY_BARS, MANAGED_SLEEVES, _sleeve_name
from tests.fakes.broker import FakePaperBroker
from us_intraday_lab.paper.v449 import V449PaperController, V449PaperLedger


def test_v11098_entry_clocks_are_frozen_and_unique() -> None:
    assert ENTRY_BARS == (3, 11, 12, 18, 24, 42)
    assert len(MANAGED_SLEEVES) == len(set(MANAGED_SLEEVES)) == 12
    assert _sleeve_name(SimpleNamespace(sleeve="opening"), 0) == "opening"
    assert _sleeve_name(SimpleNamespace(sleeve="anchor"), 0) == "anchor"
    assert _sleeve_name(SimpleNamespace(sleeve="fill"), 7) == "f7"


def test_generic_controller_preserves_distinct_v11098_order_ids(tmp_path) -> None:
    controller = V449PaperController(
        broker=FakePaperBroker(now=datetime(2026, 9, 8, 13, 30, tzinfo=UTC)),
        ledger=V449PaperLedger(tmp_path / "ledger.sqlite3"),
        strategy_code="v11098",
        managed_sleeves=MANAGED_SLEEVES,
    )
    session = date(2026, 9, 8)
    identifiers = {
        controller.client_order_id(session, sleeve, "entry")
        for sleeve in MANAGED_SLEEVES
    }
    assert len(identifiers) == len(MANAGED_SLEEVES)
    assert controller.client_order_id(session, "anchor", "entry").endswith("-a-entry")
    assert controller.client_order_id(session, "f0", "entry").endswith("-f0-entry")
