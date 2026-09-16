from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.diagnose_news_training_feasibility import render_markdown
from us_intraday_lab.news_training_feasibility import (
    FAMILIES,
    run_diagnostic,
    score_family,
    specifications,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_grid_is_exactly_four_hundred_unversioned_cells() -> None:
    specs = specifications()
    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)
    assert {item.decision_bar for item in specs} == {2, 5, 11, 17, 23}
    assert {item.holding_bars for item in specs} == {1, 2, 4, 6}
    assert {item.top_count for item in specs} == {1, 3, 5, 10}


def test_negative_news_reversal_rewards_bad_news_and_low_return() -> None:
    frame = pd.DataFrame(
        {
            "session_date": [date(2022, 1, 3)] * 3,
            "bar_idx": [2] * 3,
            "symbol": ["A", "B", "C"],
            "negative_count_1d": [3, 1, 0],
            "positive_count_1d": [0, 0, 2],
            "session_return": [-0.03, 0.0, 0.03],
        }
    )

    score = score_family(frame, "negative_news_reversal")

    assert score.iloc[0] > score.iloc[1] > score.iloc[2]


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    sessions = [date(2022, 1, 3), date(2022, 1, 4)]
    events: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    for session_index, session in enumerate(sessions):
        for symbol_index, symbol in enumerate(("A", "B", "C")):
            event_key = f"{symbol}|{session.isoformat()}|02"
            price = 100.0 + symbol_index
            events.append(
                {
                    "event_key": event_key,
                    "symbol": symbol,
                    "session_date": session,
                    "bar_idx": 2,
                    "session_return": (symbol_index - 1) * 0.01,
                    "p1_open": price,
                    "p2_open": price * 1.002,
                    "p3_open": price * 1.003,
                    "p5_open": price * 1.005,
                    "p7_open": price * 1.007,
                    "p8_open": price * 1.008,
                }
            )
            features.append(
                {
                    "event_key": event_key,
                    "symbol": symbol,
                    "session_date": session,
                    "bar_idx": 2,
                    "decayed_article_count_2h": float(symbol_index),
                    "negative_count_1d": 2 - symbol_index,
                    "positive_count_1d": symbol_index,
                    "earnings_count_1d": session_index,
                    "guidance_count_1d": symbol_index,
                    "financing_count_5d": 0,
                    "litigation_count_5d": symbol_index == 0,
                    "regulatory_count_5d": 0,
                }
            )
    events_path = tmp_path / "events.parquet"
    features_path = tmp_path / "features.parquet"
    pd.DataFrame(events).to_parquet(events_path, index=False)
    pd.DataFrame(features).to_parquet(features_path, index=False)
    return events_path, features_path


def test_run_completes_grid_without_creating_versions(tmp_path: Path) -> None:
    events, features = _write_fixture(tmp_path)

    cells, summary = run_diagnostic(
        events_path=events,
        features_path=features,
        expected_event_sha256=_sha256(events),
        expected_feature_sha256=_sha256(features),
    )

    assert len(cells) == 400
    assert summary["cells_completed"] == 400
    assert summary["development_or_consumed_loaded"] is False
    assert summary["strategy_versions_created"] == 0
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"


def test_rejects_hash_mismatch_before_reading(tmp_path: Path) -> None:
    events, features = _write_fixture(tmp_path)

    with pytest.raises(RuntimeError, match="NEWS_DIAGNOSTIC_INPUT_HASH_MISMATCH"):
        run_diagnostic(
            events_path=events,
            features_path=features,
            expected_event_sha256="0" * 64,
            expected_feature_sha256=_sha256(features),
        )


def test_rejects_nontraining_rows(tmp_path: Path) -> None:
    events, features = _write_fixture(tmp_path)
    feature_frame = pd.read_parquet(features)
    feature_frame["session_date"] = date(2024, 1, 2)
    feature_frame.to_parquet(features, index=False)

    with pytest.raises(RuntimeError, match="NEWS_DIAGNOSTIC_TRAINING_BOUNDARY"):
        run_diagnostic(
            events_path=events,
            features_path=features,
            expected_event_sha256=_sha256(events),
            expected_feature_sha256=_sha256(features),
        )


def test_markdown_preserves_research_only_boundary() -> None:
    markdown = render_markdown(
        {
            "status": "COMPLETE",
            "decision": "ABANDON_NEWS_CONTRACT_NO_VERSION_CREATED",
            "event_rows": 10,
            "cells_completed": 400,
            "retained_cells": 0,
            "retained_families": [],
            "event_sha256": "a" * 64,
            "feature_sha256": "b" * 64,
            "cells_sha256": "c" * 64,
            "strategy_versions_created": 0,
            "paper_activation": False,
            "order_route": "FORBIDDEN",
        }
    )

    assert "Strategy versions created: **0**" in markdown
    assert "Paper activation: **false**" in markdown
    assert "Order route: **FORBIDDEN**" in markdown
