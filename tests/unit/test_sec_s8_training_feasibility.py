from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import scripts.diagnose_sec_s8_training_feasibility as script
from us_intraday_lab.sec_s8_training_feasibility import (
    DECISION_BARS,
    FAMILIES,
    HOLDING_BARS,
    TOP_COUNTS,
    build_event_states,
    load_coverage,
    run_diagnostic,
    score_family,
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


def _score_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "session_date": [date(2021, 1, 5)] * 3,
            "bar_idx": [2] * 3,
            "session_return": [-0.02, 0.01, 0.03],
            "first_or_renewal_252": [True, True, True],
            "repeat_252": [False, False, False],
            "clustered_repeat_63": [False, False, False],
        }
    )


def _training_fixture(
    tmp_path: Path,
    *,
    missing_selected_exit: bool = False,
    include_container_row_after_training: bool = False,
) -> tuple[Path, Path, str, str]:
    periods = 260
    start = date(2021, 1, 1)
    sessions = [start + timedelta(days=index) for index in range(periods)]
    rows: list[dict[str, object]] = []
    for symbol, signal_return in (("AAA", 0.03), ("BBB", 0.01)):
        for session_index, session in enumerate(sessions):
            for bar_idx in DECISION_BARS:
                row: dict[str, object] = {
                    "symbol": symbol,
                    "session_date": session,
                    "bar_idx": bar_idx,
                    "session_return": signal_return,
                    "p1_open": 100.0,
                    "p2_open": 101.0,
                    "p3_open": 102.0,
                    "p5_open": 104.0,
                    "p7_open": 106.0,
                    "p8_open": 107.0,
                }
                if (
                    missing_selected_exit
                    and symbol == "AAA"
                    and session_index == 255
                    and bar_idx == 2
                ):
                    row["p2_open"] = float("nan")
                rows.append(row)
    if include_container_row_after_training:
        rows.append(
            {
                "symbol": "AAA",
                "session_date": date(2024, 1, 2),
                "bar_idx": 2,
                "session_return": 99.0,
                "p1_open": 1.0,
                "p2_open": 100.0,
                "p3_open": 100.0,
                "p5_open": 100.0,
                "p7_open": 100.0,
                "p8_open": 100.0,
            }
        )
    event_cube = tmp_path / "events.parquet"
    pd.DataFrame(rows).to_parquet(event_cube, index=False)
    event_hash = hashlib.sha256(event_cube.read_bytes()).hexdigest()

    payload = {
        "status": "ACCEPTANCE_COVERAGE_COMPLETE",
        "source": {"original_s8": 7909, "excluded_s8_pos": 5375},
        "acquisition": {"requested": 2, "admissible": 2, "missing_or_invalid": 0},
        "coverage": {
            "passed": True,
            "issuer_document_pairs": 2,
            "distinct_issuers": 2,
        },
        "admissible_rows": [
            {
                "symbol": symbol,
                "cik": cik,
                "accession": f"000000000{cik}-21-000001",
                "accepted": f"{sessions[254].isoformat()}T16:00:00",
                "form": "S-8",
                "next_sample_session": sessions[255].isoformat(),
                "admissible": True,
            }
            for symbol, cik in (("AAA", 1), ("BBB", 2))
        ],
    }
    coverage = tmp_path / "coverage.json"
    coverage_hash = _write_json(coverage, payload)
    return event_cube, coverage, event_hash, coverage_hash


def test_continuation_and_reversal_order_active_names_oppositely() -> None:
    frame = _score_fixture()

    continuation = score_family(frame, "all_event_continuation")
    reversal = score_family(frame, "all_event_reversal")

    assert continuation.idxmax() == frame.index[frame["symbol"].eq("CCC")][0]
    assert reversal.idxmax() == frame.index[frame["symbol"].eq("AAA")][0]


def test_family_predicates_exclude_ineligible_active_names() -> None:
    frame = _score_fixture()

    score = score_family(frame, "repeat_252_continuation")

    assert score.isna().all()


def test_selected_missing_price_fails_cell_closed(tmp_path: Path) -> None:
    event_cube, coverage, event_hash, coverage_hash = _training_fixture(
        tmp_path, missing_selected_exit=True
    )

    cells, summary = run_diagnostic(
        event_cube_path=event_cube,
        coverage_path=coverage,
        expected_event_sha256=event_hash,
        expected_coverage_sha256=coverage_hash,
    )

    assert cells["valid"].eq(False).any()
    assert int(summary["invalid_cells"]) > 0
    assert not cells.loc[cells["valid"].eq(False), "retention_floor_passed"].any()


def test_diagnostic_uses_frozen_cost_delay_and_no_execution_contract(
    tmp_path: Path,
) -> None:
    event_cube, coverage, event_hash, coverage_hash = _training_fixture(tmp_path)

    cells, summary = run_diagnostic(
        event_cube_path=event_cube,
        coverage_path=coverage,
        expected_event_sha256=event_hash,
        expected_coverage_sha256=coverage_hash,
    )
    cell = cells.loc[
        cells["family"].eq("all_event_continuation")
        & cells["decision_bar"].eq(2)
        & cells["holding_bars"].eq(1)
        & cells["top_count"].eq(1)
    ].iloc[0]

    assert len(cells) == 400
    assert cell["standard_cost_bp"] == 9
    assert cell["stress_cost_bp"] == 18
    assert cell["delay_bars"] == 1
    assert summary["cells_completed"] == 400
    assert summary["strategy_versions_created"] == 0
    assert summary["development_or_consumed_loaded"] is False
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"


def test_diagnostic_projects_wider_immutable_container_to_training_only(
    tmp_path: Path,
) -> None:
    event_cube, coverage, event_hash, coverage_hash = _training_fixture(
        tmp_path, include_container_row_after_training=True
    )

    cells, summary = run_diagnostic(
        event_cube_path=event_cube,
        coverage_path=coverage,
        expected_event_sha256=event_hash,
        expected_coverage_sha256=coverage_hash,
    )

    assert len(cells) == 400
    assert summary["period"] == "2021-01-01/2023-12-31"
    assert summary["container_rows_excluded_outside_training"] == 1


def _frozen_result() -> tuple[pd.DataFrame, dict[str, object]]:
    cells = pd.DataFrame(
        [
            {
                "family": item.family,
                "decision_bar": item.decision_bar,
                "holding_bars": item.holding_bars,
                "top_count": item.top_count,
                "valid": True,
                "signal_sessions": 0,
                "standard_cost_bp": 9,
                "stress_cost_bp": 18,
                "delay_bars": 1,
                "standard_9bp": {
                    "annualized_return": 0.0,
                    "information_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "positive_calendar_years": 0,
                    "calendar_year_returns": {},
                },
                "cost_18bp": {"annualized_return": 0.0},
                "delay_1bar_9bp": {"annualized_return": 0.0},
                "retention_floor_passed": False,
            }
            for item in specifications()
        ]
    )
    return cells, {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "sec-original-s8-training-feasibility-v1",
        "period": "2021-01-01/2023-12-31",
        "event_cube_sha256": "1" * 64,
        "coverage_sha256": "2" * 64,
        "coverage": {"issuer_document_pairs": 482, "distinct_issuers": 258},
        "event_rows": 1,
        "active_state_rows": 1,
        "calendar_sessions": 1,
        "cells_completed": 400,
        "invalid_cells": 0,
        "retained_cells": 0,
        "retained_families": [],
        "decision": "ABANDON_SEC_S8_NO_VERSION_CREATED",
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "primary_document_bodies_opened": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": 0.1,
    }


def test_cli_writes_complete_versionless_outputs_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "run_diagnostic", lambda **_: _frozen_result())
    args = [
        "--event-cube",
        str(tmp_path / "events.parquet"),
        "--coverage",
        str(tmp_path / "coverage.json"),
        "--output-json",
        str(tmp_path / "summary.json"),
        "--output-parquet",
        str(tmp_path / "cells.parquet"),
        "--output-md",
        str(tmp_path / "summary.md"),
    ]

    assert script.run(args) == 0
    summary = json.loads((tmp_path / "summary.json").read_text("utf-8"))

    assert summary["status"] == "COMPLETE"
    assert summary["cells_completed"] == 400
    assert summary["strategy_versions_created"] == 0
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"
    assert (tmp_path / "cells.parquet").exists()
    assert (tmp_path / "summary.md").exists()
    assert not list(tmp_path.glob("*.tmp"))
