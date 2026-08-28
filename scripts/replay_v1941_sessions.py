"""User-requested retrospective diagnostics, never prospective shadow observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd
from run_v1941_research_shadow import target_ready

from us_intraday_lab.paper.pool import v1254_signals_at
from us_intraday_lab.research_shadow_alpaca import AlpacaIexHistory
from us_intraday_lab.v45_research_shadow import SYMBOLS, _bucket
from us_intraday_lab.v1941_research_shadow import (
    LABELS,
    bar_time,
    exact_open,
    frozen_state,
    through_bar,
)

REPLAY_LABELS = {
    **LABELS,
    "mode": "RETROSPECTIVE_DIAGNOSTIC_NOT_LIVE_SHADOW",
    "prospective": False,
    "actual_orders": 0,
    "parameter_refit": False,
    "receipt_scenario": "UNAVAILABLE_NO_LIVE_RECEIPT_TIMESTAMP",
}


def replay(bars: pd.DataFrame, session: date, asof: datetime) -> dict:
    """Use historical decision cutoffs; do not invent wall-clock signal receipts."""
    bars = bars.loc[
        pd.to_datetime(bars.timestamp, utc=True) < asof.replace(second=0, microsecond=0)
    ]
    state = frozen_state(bars, session)
    signals, decisions, seen = [], [], set()
    for decision in (23, 26, 29):
        if asof < bar_time(session, decision + 1):
            decisions.append({"decision": decision, "status": "PENDING_WINDOW"})
            continue
        try:
            cutoff = through_bar(bars, session, decision)
            if not target_ready(cutoff, session, decision):
                raise ValueError("TARGET_BARS_INCOMPLETE")
            selected = v1254_signals_at(cutoff, session_date=session, decision_bar=decision)
        except ValueError as exc:
            decisions.append(
                {
                    "decision": decision,
                    "status": "INCOMPLETE_INPUT",
                    "error_type": type(exc).__name__,
                }
            )
            continue
        for signal in selected:
            if signal.sleeve in seen:
                raise ValueError("DUPLICATE_SLEEVE")
            seen.add(signal.sleeve)
            signals.append(asdict(signal))
        decisions.append({"decision": decision, "status": "REPLAYED", "signals": len(selected)})
    gross = sum(s["weight"] * s["exposure"] for s in signals)
    if not 0 <= gross <= 1.00000001:
        raise ValueError("GROSS_BOUNDARY_VIOLATION")
    results = {}
    for name, cost, delay in (
        ("9bp", 0.0009, 0),
        ("18bp", 0.0018, 0),
        ("delay_5min_9bp", 0.0009, 1),
    ):
        trades, incomplete = [], []
        for signal in signals:
            if asof < bar_time(session, signal["exit_bar"]) + timedelta(minutes=1):
                incomplete.append({"symbol": signal["symbol"], "reason": "PENDING_EXIT"})
                continue
            try:
                entry = exact_open(
                    bars, session, signal["symbol"], (signal["decision_bar"] + 1 + delay) * 5
                )
                exit_price = exact_open(bars, session, signal["symbol"], signal["exit_bar"] * 5)
            except ValueError:
                incomplete.append({"symbol": signal["symbol"], "reason": "MISSING_EXACT_PRICE"})
                continue
            baseline = signal["weight"] * signal["exposure"] * (exit_price / entry - 1 - cost)
            trades.append(
                {
                    **signal,
                    "entry": entry,
                    "exit": exit_price,
                    "baseline_return": baseline,
                    "candidate_return": baseline * state["budget_multiplier"],
                }
            )
        complete = not incomplete and all(d["status"] == "REPLAYED" for d in decisions)
        baseline = sum(t["baseline_return"] for t in trades) if complete else None
        results[name] = {
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "v1254_raw_return": baseline,
            "v1254_common_state_return": baseline if state["state_valid"] else 0.0,
            "v1941_return": (
                baseline * state["budget_multiplier"] if baseline is not None else None
            ),
            "trades": trades,
            "incomplete": incomplete,
            "fill_type": "THEORETICAL_IEX_OPEN_NOT_BROKER_FILL",
        }
    complete = all(s["status"] == "COMPLETE" for s in results.values())
    return {
        **REPLAY_LABELS,
        "session": str(session),
        "asof_utc": asof.isoformat(),
        "status": "COMPLETE_DIAGNOSTIC" if complete else "INCOMPLETE_DIAGNOSTIC",
        "state": state,
        "decisions": decisions,
        "signals": signals,
        "baseline_gross": gross,
        "candidate_gross": gross * state["budget_multiplier"],
        "scenarios": results,
    }


def immutable_json(path, payload):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=date.fromisoformat, nargs="+", required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--follow-final", action="store_true")
    args = parser.parse_args()
    calendar = xcals.get_calendar("XNYS")
    sessions = sorted(set(args.sessions))
    for session in sessions:
        if not calendar.is_session(str(session)):
            raise ValueError("NOT_XNYS_SESSION")
        if calendar.session_close(str(session)).to_pydatetime() < bar_time(session, 74):
            raise ValueError("SHORT_SESSION_UNSUPPORTED")
    root = Path(__file__).resolve().parents[1]
    # A retrospective run cannot be directed into the live-shadow or Paper ledger tree.
    output = args.output.resolve()
    for forbidden in (root / "state/paper", root / "state/research_shadow_v1941"):
        if output == forbidden or forbidden in output.parents:
            raise ValueError("RETROSPECTIVE_OUTPUT_ISOLATION_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    run = output / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + f"-{os.getpid()}")
    run.mkdir()
    seed = args.seed.resolve()
    import sqlite3

    connection = sqlite3.connect((seed.parent / "events.sqlite3").as_uri() + "?mode=ro", uri=True)
    recorded = json.loads(
        connection.execute(
            "SELECT payload FROM events WHERE event_key=?", ("prefetch",)
        ).fetchone()[0]
    )
    digest = hashlib.sha256(seed.read_bytes()).hexdigest()
    if digest != recorded["sha256"]:
        raise ValueError("SEED_HASH_MISMATCH")
    prior = pd.read_parquet(seed)
    # Retain only complete prior-session context; fetch non-overlapping later sessions fresh.
    _, seed_sessions, _ = _bucket(prior)
    seed_end = seed_sessions[-1]
    if seed_end >= min(sessions):
        raise ValueError("SEED_MUST_PRECEDE_TARGETS")
    # Use the next session's regular open; _bucket excludes off-session observations.
    fetch_start = bar_time(seed_end + timedelta(days=1), 0)
    prior = prior.loc[prior.timestamp < fetch_start]
    immutable_json(
        run / "manifest.json",
        {
            **REPLAY_LABELS,
            "sessions": [str(s) for s in sessions],
            "seed": str(seed),
            "seed_sha256": digest,
            "source_sha256": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (
                    "scripts/replay_v1941_sessions.py",
                    "src/us_intraday_lab/v1941_research_shadow.py",
                    "src/us_intraday_lab/paper/pool.py",
                )
            },
        },
    )
    client = AlpacaIexHistory.from_environment()

    def run_stage(stage):
        now = datetime.now(UTC)
        end = min(now, bar_time(max(sessions), 78))
        fresh = client.fetch(symbols=SYMBOLS, start=fetch_start, end=end)
        frame = pd.concat([prior, fresh], ignore_index=True)
        path = run / f"{stage}.parquet"
        frame.to_parquet(path, index=False)
        source = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for session in sessions:
            result = replay(frame, session, now)
            result["snapshot"] = source
            immutable_json(run / f"{session}-{stage}.json", result)
            print(
                json.dumps(
                    {
                        "session": str(session),
                        "status": result["status"],
                        "budget": result["state"]["budget_multiplier"],
                        "signal_count": len(result["signals"]),
                        "run_dir": str(run),
                        "returns": {n: r["v1941_return"] for n, r in result["scenarios"].items()},
                    }
                ),
                flush=True,
            )

    run_stage("initial")
    target = bar_time(max(sessions), 74)
    if args.follow_final and datetime.now(UTC) < target:
        print(json.dumps({"status": "WAITING_FINAL", "until": target.isoformat()}), flush=True)
        while (remaining := (target - datetime.now(UTC)).total_seconds()) > 0:
            time.sleep(min(30, remaining))
        run_stage("final")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never echo credential-bearing adapter errors
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
