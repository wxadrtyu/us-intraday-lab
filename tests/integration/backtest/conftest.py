from __future__ import annotations

import io
import tarfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.catalog import accept_dataset, build_catalog
from us_intraday_lab.data.snapshot import ArchiveSourceDeclaration, import_snapshot

SESSION_DATE = date(2026, 7, 2)
PRODUCTION_SYMBOLS = ("IWM", "QQQ", "SPY")
MEMBER_NAME = "synthetic/minute_bars.csv"


def _signal_prices(base: float) -> list[float]:
    closes = [base, base + 10, base + 20, base + 30, base + 40]
    peak = closes[-1]
    closes.extend(peak + 0.1 * (index + 1) for index in range(14))
    closes.append(closes[-1] - 2.0)
    closes.extend([closes[-1]] * 6)
    return closes


def _synthetic_archive(tmp_path: Path) -> Path:
    timestamps = expected_minute_index(SESSION_DATE)
    rows: list[pd.DataFrame] = []
    for symbol_number, symbol in enumerate(PRODUCTION_SYMBOLS):
        prices = _signal_prices(100.0 + symbol_number * 100.0)
        minute_prices = [prices[index // 15] for index in range(len(timestamps))]
        volumes = [5_000.0 if index // 15 == 19 else 1_000.0 for index in range(len(timestamps))]
        rows.append(
            pd.DataFrame(
                {
                    "ticker": symbol,
                    "date": timestamps,
                    "open": minute_prices,
                    "high": [price + 0.2 for price in minute_prices],
                    "low": [price - 0.2 for price in minute_prices],
                    "close": minute_prices,
                    "volume": volumes,
                }
            )
        )
    payload = pd.concat(rows, ignore_index=True).to_csv(index=False).encode()
    archive_path = tmp_path / "accepted-minute-bars.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(MEMBER_NAME)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return archive_path


@pytest.fixture
def accepted_backtest_dataset(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "synthetic-repo"
    manifest, _ = import_snapshot(
        _synthetic_archive(tmp_path),
        root=root,
        source=ArchiveSourceDeclaration(
            provider="tiingo",
            feed="iex",
            bar_size="1min",
            member_names=(MEMBER_NAME,),
            production_symbols=PRODUCTION_SYMBOLS,
            expected_start_date=SESSION_DATE,
            expected_end_date=SESSION_DATE,
            ingested_at=datetime(2026, 7, 27, tzinfo=UTC),
        ),
    )
    build_catalog(manifest.dataset_id, root=root)
    accepted = accept_dataset(manifest.dataset_id, root=root)
    assert accepted.quality_passed
    return root, manifest.dataset_id
