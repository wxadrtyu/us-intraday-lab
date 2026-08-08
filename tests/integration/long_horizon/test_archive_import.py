from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.data import read_declared_five_minute_member

REAL_ARCHIVE = Path(r"G:\quant-agent-team-us\data\us_stock_data.tar.gz")
MEMBER_SHA256 = "2aa6d1483d4aed73edad83c255f837ca95004cb9230108966ae825074289e669"


def declaration() -> FiveMinuteSourceDeclaration:
    return FiveMinuteSourceDeclaration(
        provider="tiingo",
        feed="iex",
        bar_size="5min",
        member_name="price_intraday_vol_5min.csv",
        member_sha256=MEMBER_SHA256,
        symbols=("AAPL", "QQQ"),
        source_timezone="America/New_York",
        expected_start_date=date(2025, 1, 2),
        expected_end_date=date(2026, 7, 2),
        ingested_at=datetime(2026, 8, 8, tzinfo=UTC),
    )


@pytest.mark.skipif(not REAL_ARCHIVE.is_file(), reason="local legacy archive unavailable")
def test_declared_real_member_identity_and_scope() -> None:
    frame = read_declared_five_minute_member(REAL_ARCHIVE, declaration())

    assert tuple(sorted(frame["symbol"].unique())) == ("AAPL", "QQQ")
    assert frame["timestamp"].min().isoformat() == "2025-01-02T14:30:00+00:00"
    assert frame["timestamp"].max().isoformat() == "2026-07-02T19:55:00+00:00"
    assert len(frame) == 52_099
    assert declaration().member_sha256 == MEMBER_SHA256
