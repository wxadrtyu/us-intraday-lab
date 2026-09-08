"""Build a training-only point-in-time news feature cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.news_event_acquisition import TRAINING_END, TRAINING_START
from us_intraday_lab.data.news_event_features import (
    FROZEN_NEWS_LEXICON,
    build_news_features,
)
from us_intraday_lab.data.quote_feature_acquisition import decision_timestamp


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_training_event_frame(source: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "session_date", "bar_idx"}
    if missing := required.difference(source.columns):
        raise ValueError(f"NEWS_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    result = source.loc[:, ["symbol", "session_date", "bar_idx"]].copy()
    result["symbol"] = result["symbol"].astype("string").str.upper()
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    result["bar_idx"] = pd.to_numeric(result["bar_idx"], errors="raise").astype(int)
    if not result["session_date"].map(
        lambda value: TRAINING_START <= value <= TRAINING_END
    ).all():
        raise ValueError("NEWS_EVENT_FRAME_TRAINING_ONLY")
    result["event_key"] = (
        result["symbol"].astype(str)
        + "|"
        + result["session_date"].map(date.isoformat)
        + "|"
        + result["bar_idx"].map(lambda value: f"{value:02d}")
    )
    if result["event_key"].duplicated().any():
        raise ValueError("NEWS_EVENT_KEY_DUPLICATE")
    cutoffs = {
        (session, bar_idx): decision_timestamp(session, bar_idx)
        for session, bar_idx in result.loc[
            :, ["session_date", "bar_idx"]
        ].drop_duplicates().itertuples(index=False, name=None)
    }
    result["decision_timestamp"] = pd.to_datetime(
        [
            cutoffs[(session, bar_idx)]
            for session, bar_idx in result.loc[
                :, ["session_date", "bar_idx"]
            ].itertuples(index=False, name=None)
        ],
        utc=True,
    )
    return result.loc[
        :, ["event_key", "symbol", "session_date", "bar_idx", "decision_timestamp"]
    ]


def load_training_articles(root: Path, start: date, end: date) -> pd.DataFrame:
    if start > end or start < TRAINING_START or end > TRAINING_END:
        raise ValueError("NEWS_ARTICLE_LOAD_TRAINING_ONLY")
    staging = root / "data/staging/alpaca_news_metadata_v1"
    paths = [
        path
        for path in sorted(staging.glob("????-??/*.parquet"))
        if start <= date.fromisoformat(path.stem) <= end
    ]
    expected_days = (end - start).days + 1
    if len(paths) != expected_days:
        raise ValueError(
            f"NEWS_TRAINING_PARTITIONS_INCOMPLETE:{len(paths)}/{expected_days}"
        )
    frames = [pd.read_parquet(path) for path in paths]
    result = pd.concat(frames, ignore_index=True)
    if result["news_id"].astype(str).duplicated().any():
        raise ValueError("NEWS_ARTICLE_ID_DUPLICATE")
    return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--start", default=TRAINING_START, type=date.fromisoformat)
    parser.add_argument("--end", default=TRAINING_END, type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    started = time.perf_counter()
    source = pd.read_parquet(
        arguments.events,
        columns=["symbol", "session_date", "bar_idx"],
        filters=[
            ("session_date", ">=", arguments.start),
            ("session_date", "<=", arguments.end),
        ],
    )
    events = build_training_event_frame(source)
    articles = load_training_articles(arguments.root.resolve(), arguments.start, arguments.end)
    features = build_news_features(events, articles, FROZEN_NEWS_LEXICON)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    features.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    report = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "training_only": True,
        "start": arguments.start.isoformat(),
        "end": arguments.end.isoformat(),
        "event_rows": len(events),
        "feature_rows": len(features),
        "unique_event_keys": int(features["event_key"].nunique()),
        "article_rows": len(articles),
        "duplicate_event_keys": int(features["event_key"].duplicated().sum()),
        "output_sha256": _sha256_file(arguments.output),
        "elapsed_seconds": time.perf_counter() - started,
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
