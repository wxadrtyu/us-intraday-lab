"""Acquire immutable FINRA short-volume files for frozen training sessions."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.finra_short_volume_acquisition import (
    FinraShortVolumeHttpTransport,
    acquire_sessions,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    return parser.parse_args()


def load_training_sessions(events_path: Path) -> list[date]:
    dates = pd.read_parquet(
        events_path,
        columns=["session_date"],
        filters=[
            ("session_date", ">=", date(2021, 1, 1)),
            ("session_date", "<=", date(2023, 12, 31)),
        ],
    )["session_date"]
    return sorted(set(pd.to_datetime(dates).dt.date))


def main() -> int:
    arguments = _arguments()
    sessions = load_training_sessions(arguments.events)
    manifests = acquire_sessions(
        arguments.root.resolve(), sessions, FinraShortVolumeHttpTransport()
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "training_only": True,
                "sessions": len(manifests),
                "rows": sum(int(item["row_count"]) for item in manifests),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
