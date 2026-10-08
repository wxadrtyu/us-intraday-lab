from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.sec_s8_training_feasibility import (
    DECISION_BARS,
    FAMILIES,
    HOLDING_BARS,
    TOP_COUNTS,
    build_event_states,
    load_coverage,
    specifications,
)


def _coverage_fixture() -> dict[str, object]:
    return {
        "status": "ACCEPTANCE_COVERAGE_COMPLETE",
        "source": {"original_s8": 7909, "excluded_s8_pos": 5375},
        "acquisition": {"requested": 620, "admissible": 2, "missing_or_invalid": 618},
        "coverage": {
            "passed": True,
            "issuer_document_pairs": 2,
            "distinct_issuers": 1,
        },
        "admissible_rows": [
            {
                "symbol": "AAA",
                "cik": 1,
                "accession": "0000000001-21-000001",
                "accepted": "2021-01-04T16:00:00",
                "form": "S-8",
                "next_sample_session": "2021-01-05",
                "admissible": True,
            },
            {
                "symbol": "AAA",
                "cik": 1,
                "accession": "0000000001-22-000001",
                "accepted": "2022-01-04T16:00:00",
                "form": "S-8",
                "next_sample_session": "2022-01-05",
                "admissible": True,
            },
        ],
    }


def _write_json(path: Path, payload: dict[str, object]) -> str:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _symbol_sessions(symbol: str, periods: int, *, start: date = date(2021, 1, 1)) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * periods,
            "session_date": [start + timedelta(days=index) for index in range(periods)],
        }
    )


def _event_rows(*rows: tuple[str, str, date]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "accession": accession,
                "accepted": f"{session.isoformat()}T16:00:00",
                "next_sample_session": session,
            }
            for symbol, accession, session in rows
        ]
    )


def test_specifications_are_exactly_the_frozen_four_hundred_cells() -> None:
    specs = specifications()

    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)
    assert {item.decision_bar for item in specs} == set(DECISION_BARS)
    assert {item.holding_bars for item in specs} == set(HOLDING_BARS)
    assert {item.top_count for item in specs} == set(TOP_COUNTS)


def test_load_coverage_rejects_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    _write_json(path, _coverage_fixture())

    with pytest.raises(RuntimeError, match="SEC_S8_COVERAGE_HASH_MISMATCH"):
        load_coverage(path, "0" * 64)


def test_load_coverage_returns_only_frozen_admissible_rows(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    digest = _write_json(path, _coverage_fixture())

    rows, audit = load_coverage(path, digest)

    assert len(rows) == 2
    assert rows["form"].eq("S-8").all()
    assert rows["admissible"].eq(True).all()
    assert audit["coverage_passed"] is True


def test_event_is_active_for_exactly_three_symbol_sessions() -> None:
    sessions = _symbol_sessions("AAA", periods=6)
    availability = sessions.iloc[1]["session_date"]
    events = _event_rows(("AAA", "a1", availability))

    states = build_event_states(events, sessions)

    assert states["session_date"].tolist() == sessions["session_date"].iloc[1:4].tolist()
    assert states["active_accessions"].tolist() == [("a1",)] * 3


def test_first_label_requires_complete_252_session_lookback() -> None:
    aaa = _symbol_sessions("AAA", periods=260)
    bbb = _symbol_sessions("BBB", periods=260)
    sessions = pd.concat([aaa, bbb], ignore_index=True)
    events = _event_rows(
        ("AAA", "left-censored", aaa.iloc[100]["session_date"]),
        ("BBB", "complete", bbb.iloc[255]["session_date"]),
    )

    states = build_event_states(events, sessions)
    first_state = states.groupby("symbol", sort=True).first()

    assert not bool(first_state.loc["AAA", "first_or_renewal_252"])
    assert bool(first_state.loc["BBB", "first_or_renewal_252"])


def test_same_availability_accessions_do_not_make_each_other_repeats() -> None:
    sessions = _symbol_sessions("AAA", periods=300)
    availability = sessions.iloc[260]["session_date"]
    events = _event_rows(("AAA", "a1", availability), ("AAA", "a2", availability))

    states = build_event_states(events, sessions)

    assert not states["repeat_252"].any()
    assert not states["clustered_repeat_63"].any()
    assert states.iloc[0]["active_accessions"] == ("a1", "a2")


def test_repeat_windows_use_strictly_prior_availability_sessions() -> None:
    sessions = _symbol_sessions("AAA", periods=400)
    events = _event_rows(
        ("AAA", "old", sessions.iloc[100]["session_date"]),
        ("AAA", "repeat", sessions.iloc[300]["session_date"]),
        ("AAA", "cluster", sessions.iloc[350]["session_date"]),
    )

    states = build_event_states(events, sessions)
    repeat_start = states.loc[states["session_date"].eq(sessions.iloc[300]["session_date"])].iloc[0]
    cluster_start = states.loc[states["session_date"].eq(sessions.iloc[350]["session_date"])].iloc[0]

    assert bool(repeat_start["repeat_252"])
    assert not bool(repeat_start["clustered_repeat_63"])
    assert bool(cluster_start["repeat_252"])
    assert bool(cluster_start["clustered_repeat_63"])
