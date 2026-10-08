from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import scripts.diagnose_sec_s3asr_training_feasibility as script
from us_intraday_lab.sec_s3asr_training_feasibility import (
    DECISION_BARS,
    FAMILIES,
    build_event_states,
    load_coverage,
    run_diagnostic,
    score_family,
    specifications,
)


def _write_json(path: Path, payload: object) -> str:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode()
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _coverage_fixture() -> dict[str, object]:
    return {
        "status": "ACCEPTANCE_COVERAGE_COMPLETE",
        "source": {"original_s3asr": 5766, "excluded_s3asr_amendments": 0},
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
                "accepted": "2021-01-04T16:00:00-05:00",
                "form": "S-3ASR",
                "next_sample_session": "2021-01-05",
                "admissible": True,
            }
            for symbol, cik in (("AAA", 1), ("BBB", 2))
        ],
    }


def _symbol_sessions(symbol: str, periods: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": symbol,
            "session_date": [date(2021, 1, 1) + timedelta(days=i) for i in range(periods)],
        }
    )


def _event_rows(*rows: tuple[str, str, date]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "accession": accession,
                "accepted": f"{availability.isoformat()}T16:00:00-05:00",
                "next_sample_session": availability,
            }
            for symbol, accession, availability in rows
        ]
    )


def test_grid_is_exactly_400_unique_cells() -> None:
    specs = specifications()

    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)


def test_load_coverage_requires_exact_form_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    digest = _write_json(path, _coverage_fixture())

    rows, audit = load_coverage(path, digest)

    assert rows["form"].eq("S-3ASR").all()
    assert audit["issuer_document_pairs"] == 2
    with pytest.raises(RuntimeError, match="SEC_S3ASR_COVERAGE_HASH_MISMATCH"):
        load_coverage(path, "0" * 64)


def test_event_is_active_for_exactly_five_symbol_sessions() -> None:
    sessions = _symbol_sessions("AAA", 8)
    availability = sessions.iloc[1]["session_date"]

    states = build_event_states(
        _event_rows(("AAA", "a1", availability)), sessions
    )

    assert states["session_date"].tolist() == sessions["session_date"].iloc[1:6].tolist()
    assert states["active_accessions"].tolist() == [("a1",)] * 5


def test_repeat_windows_are_strictly_causal() -> None:
    sessions = _symbol_sessions("AAA", 400)
    events = _event_rows(
        ("AAA", "old", sessions.iloc[100]["session_date"]),
        ("AAA", "repeat", sessions.iloc[300]["session_date"]),
        ("AAA", "cluster", sessions.iloc[350]["session_date"]),
    )

    states = build_event_states(events, sessions)
    repeat = states.loc[states["session_date"].eq(sessions.iloc[300]["session_date"])].iloc[0]
    cluster = states.loc[states["session_date"].eq(sessions.iloc[350]["session_date"])].iloc[0]

    assert bool(repeat["repeat_252"])
    assert not bool(repeat["clustered_repeat_63"])
    assert bool(cluster["repeat_252"])
    assert bool(cluster["clustered_repeat_63"])


def test_continuation_and_reversal_order_names_oppositely() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "session_date": [date(2021, 1, 5)] * 3,
            "bar_idx": [2] * 3,
            "session_return": [-0.02, 0.01, 0.03],
            "first_or_renewal_252": [True] * 3,
            "repeat_252": [False] * 3,
            "clustered_repeat_63": [False] * 3,
        }
    )

    continuation = score_family(frame, "all_event_continuation")
    reversal = score_family(frame, "all_event_reversal")

    assert continuation.idxmax() == 2
    assert reversal.idxmax() == 0


def _training_fixture(
    tmp_path: Path,
    *,
    missing_selected_exit: bool = False,
    include_later_container_row: bool = False,
) -> tuple[Path, Path, str, str]:
    periods = 260
    sessions = [date(2021, 1, 1) + timedelta(days=i) for i in range(periods)]
    rows: list[dict[str, object]] = []
    for symbol, signal_return in (("AAA", 0.03), ("BBB", 0.01)):
        for index, session in enumerate(sessions):
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
                if missing_selected_exit and symbol == "AAA" and index == 255 and bar_idx == 2:
                    row["p2_open"] = float("nan")
                rows.append(row)
    if include_later_container_row:
        rows.append(
            {
                "symbol": "AAA",
                "session_date": date(2024, 1, 2),
                "bar_idx": 2,
                "session_return": 99.0,
                "p1_open": 1.0,
                "p2_open": 2.0,
                "p3_open": 2.0,
                "p5_open": 2.0,
                "p7_open": 2.0,
                "p8_open": 2.0,
            }
        )
    cube = tmp_path / "events.parquet"
    pd.DataFrame(rows).to_parquet(cube, index=False)
    cube_hash = hashlib.sha256(cube.read_bytes()).hexdigest()

    payload = _coverage_fixture()
    for row, session in zip(payload["admissible_rows"], (sessions[255], sessions[255]), strict=True):
        row["next_sample_session"] = session.isoformat()
        row["accepted"] = f"{sessions[254].isoformat()}T16:00:00-05:00"
    coverage = tmp_path / "coverage.json"
    coverage_hash = _write_json(coverage, payload)
    return cube, coverage, cube_hash, coverage_hash


def test_diagnostic_enforces_grid_cost_delay_and_training_boundary(tmp_path: Path) -> None:
    cube, coverage, cube_hash, coverage_hash = _training_fixture(
        tmp_path, include_later_container_row=True
    )

    cells, summary = run_diagnostic(
        event_cube_path=cube,
        coverage_path=coverage,
        expected_event_sha256=cube_hash,
        expected_coverage_sha256=coverage_hash,
    )

    assert len(cells) == 400
    assert cells["standard_cost_bp"].eq(9).all()
    assert cells["stress_cost_bp"].eq(18).all()
    assert cells["delay_bars"].eq(1).all()
    assert summary["container_rows_excluded_outside_training"] == 1
    assert summary["cells_completed"] == 400
    assert summary["strategy_versions_created"] == 0
    assert summary["development_or_consumed_loaded"] is False
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"


def test_selected_missing_price_invalidates_cells(tmp_path: Path) -> None:
    cube, coverage, cube_hash, coverage_hash = _training_fixture(
        tmp_path, missing_selected_exit=True
    )

    cells, summary = run_diagnostic(
        event_cube_path=cube,
        coverage_path=coverage,
        expected_event_sha256=cube_hash,
        expected_coverage_sha256=coverage_hash,
    )

    assert cells["valid"].eq(False).any()
    assert summary["invalid_cells"] > 0


def test_cli_writes_complete_outputs_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cells = pd.DataFrame(
        [
            {
                "family": spec.family,
                "decision_bar": spec.decision_bar,
                "holding_bars": spec.holding_bars,
                "top_count": spec.top_count,
                "valid": True,
                "signal_sessions": 0,
                "standard_cost_bp": 9,
                "stress_cost_bp": 18,
                "delay_bars": 1,
                "standard_9bp": {"annualized_return": 0.0, "information_ratio": 0.0},
                "cost_18bp": {"annualized_return": 0.0},
                "delay_1bar_9bp": {"annualized_return": 0.0},
                "retention_floor_passed": False,
            }
            for spec in specifications()
        ]
    )
    summary = {
        "status": "COMPLETE",
        "decision": "ABANDON_SEC_S3ASR_NO_VERSION_CREATED",
        "cells_completed": 400,
        "invalid_cells": 0,
        "retained_cells": 0,
        "retained_families": [],
        "coverage": {"issuer_document_pairs": 286, "distinct_issuers": 249},
        "event_cube_sha256": "1" * 64,
        "coverage_sha256": "2" * 64,
        "active_state_rows": 0,
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "primary_document_bodies_opened": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": 0.1,
    }
    monkeypatch.setattr(script, "run_diagnostic", lambda **_: (cells, summary))

    result = script.run(
        [
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
    )

    assert result == 0
    saved = json.loads((tmp_path / "summary.json").read_text("utf-8"))
    assert saved["cells_completed"] == 400
    assert saved["strategy_versions_created"] == 0
    assert saved["paper_activation"] is False
    assert saved["order_route"] == "FORBIDDEN"
    assert (tmp_path / "cells.parquet").exists()
    assert not list(tmp_path.glob("*.tmp"))
