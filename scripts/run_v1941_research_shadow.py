"""One-session live signal capture. Market data only; no broker or order calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from us_intraday_lab.paper.pool import v1254_signals_at
from us_intraday_lab.research_shadow_alpaca import AlpacaIexHistory
from us_intraday_lab.v45_research_shadow import SYMBOLS
from us_intraday_lab.v1941_research_shadow import (
    LABELS,
    ShadowLedger,
    bar_time,
    frozen_state,
    theoretical_results,
    through_bar,
)


def wait_until(target):
    while (remaining := (target - datetime.now(UTC)).total_seconds()) > 0:
        time.sleep(min(30, remaining))


def snapshot(frame, directory, name):
    target = directory / f"{name}.parquet"
    if target.exists():
        raise RuntimeError("IMMUTABLE_SNAPSHOT_ALREADY_EXISTS")
    temporary = target.with_suffix(".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.rename(target)
    return {
        "file": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "rows": len(frame),
    }


def target_ready(frame, session, decision):
    current = frame.loc[frame.timestamp >= bar_time(session, 0)]
    for symbol in ("TQQQ", "SOXL"):
        selected = current.loc[current.symbol == symbol]
        minutes = (selected.timestamp - bar_time(session, 0)).dt.total_seconds() / 60
        if not set(range(decision + 1)).issubset(set((minutes // 5).astype(int))):
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    session, directory = args.session, args.output.resolve() / args.session.isoformat()
    calendar = xcals.get_calendar("XNYS")
    if not calendar.is_session(str(session)):
        raise RuntimeError("NOT_XNYS_SESSION")
    if calendar.session_close(str(session)).to_pydatetime() < bar_time(session, 74):
        raise RuntimeError("SHORT_SESSION_UNSUPPORTED")
    directory.mkdir(parents=True, exist_ok=True)
    # OS-held nonblocking lock is released even if this process crashes.
    lock = (directory / "runner.lock").open("a+b")
    if os.name == "nt":
        import msvcrt

        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = ShadowLedger(directory / "events.sqlite3")
    if ledger.get("result"):
        return
    client = AlpacaIexHistory.from_environment()
    ledger.append(
        f"startup-{os.getpid()}",
        "STARTUP",
        {
            "session": str(session),
            "pid": os.getpid(),
            "protocol": "v1941-live-shadow-1",
            "state_time": bar_time(session, 18).isoformat(),
            "signal_times": [bar_time(session, i + 1).isoformat() for i in (23, 26, 29)],
            "end_time": bar_time(session, 74).isoformat(),
            "source_sha256": {
                name: hashlib.sha256(
                    (Path(__file__).resolve().parents[1] / name).read_bytes()
                ).hexdigest()
                for name in (
                    "scripts/run_v1941_research_shadow.py",
                    "src/us_intraday_lab/v1941_research_shadow.py",
                    "src/us_intraday_lab/paper/pool.py",
                    "research/results/2026-08-26-v1865-v1965-risk-overlay.json",
                )
            },
        },
    )
    print(
        json.dumps(
            {
                "event": "STARTUP",
                "session": str(session),
                "pid": os.getpid(),
                "order_route": "FORBIDDEN",
            }
        ),
        flush=True,
    )
    prior_path = directory / "prior.parquet"
    if prior_path.exists():
        recorded = ledger.get("prefetch")
        if (
            not recorded
            or hashlib.sha256(prior_path.read_bytes()).hexdigest() != recorded["sha256"]
        ):
            raise RuntimeError("PRIOR_SNAPSHOT_INTEGRITY_FAILURE")
        prior = pd.read_parquet(prior_path)
    else:
        prior = client.fetch(
            symbols=SYMBOLS,
            start=bar_time(session, 0) - timedelta(days=75),
            end=min(datetime.now(UTC), bar_time(session, 0) - timedelta(microseconds=1)),
        )
        ledger.append("prefetch", "PREFETCH", snapshot(prior, directory, "prior"))
    print(
        json.dumps(
            {
                "event": "READY",
                "prior_rows": len(prior),
                "next_state_time": bar_time(session, 18).isoformat(),
            }
        ),
        flush=True,
    )

    def fetch():
        current = client.fetch(symbols=SYMBOLS, start=bar_time(session, 0), end=datetime.now(UTC))
        return pd.concat([prior, current], ignore_index=True)

    def capture(key, decision, state=False):
        if ledger.get(key):
            return ledger.get(key)
        eligible = bar_time(session, decision + 1)
        deadline = eligible + timedelta(minutes=2)
        wait_until(eligible + timedelta(seconds=5))
        errors = []
        while datetime.now(UTC) <= deadline:
            try:
                frame = through_bar(fetch(), session, decision)
                if datetime.now(UTC) > deadline:
                    break
                payload = frozen_state(frame, session) if state else {}
                ready = payload["state_valid"] if state else target_ready(frame, session, decision)
                if not ready:
                    time.sleep(5)
                    continue
                signals = (
                    []
                    if state
                    else [
                        asdict(s)
                        for s in v1254_signals_at(
                            frame, session_date=session, decision_bar=decision
                        )
                    ]
                )
                observed = datetime.now(UTC)
                if observed > deadline:
                    break
                receipt_minute = (
                    math.floor((observed - bar_time(session, 0)).total_seconds() / 60) + 1
                )
                for signal in signals:
                    signal["receipt_entry_minute"] = receipt_minute
                payload.update(
                    {
                        "observed_at": observed.isoformat(),
                        "signals": signals,
                        "lag_seconds": (observed - eligible).total_seconds(),
                        "snapshot": snapshot(frame, directory, key),
                        "status": "CAPTURED",
                    }
                )
                ledger.append(
                    key, "STATE" if state else ("SIGNAL" if signals else "NO_SIGNAL"), payload
                )
                print(
                    json.dumps({"event": "CAPTURED", "key": key, "signal_count": len(signals)}),
                    flush=True,
                )
                return ledger.get(key)
            except Exception as exc:  # noqa: BLE001 - fail closed; sanitize adapter errors
                # Exception messages from adapters can contain request details; store type only.
                errors.append(type(exc).__name__)
                time.sleep(5)
        payload = {
            "status": "MISSED_OR_INCOMPLETE",
            "signals": [],
            "state_valid": False,
            "budget_multiplier": 0.0,
            "error_types": errors,
            "no_retrospective_signal_reconstruction": True,
        }
        ledger.append(key, "SKIP", payload)
        return ledger.get(key)

    state = capture("state", 17, state=True)
    signals, failures, sleeves = [], [], set()
    for decision in (23, 26, 29):
        observation = capture(f"decision-{decision}", decision)
        if observation["status"] != "CAPTURED":
            failures.append(decision)
        for signal in observation["signals"]:
            if signal["sleeve"] in sleeves:
                raise RuntimeError("DUPLICATE_SLEEVE_SIGNAL")
            sleeves.add(signal["sleeve"])
            signals.append(signal)
        gross = sum(s["weight"] * s["exposure"] for s in signals)
        if not 0 <= gross <= 1.00000001:
            raise RuntimeError("GROSS_BOUNDARY_VIOLATION")
        ledger.append(
            f"position-{decision}",
            "THEORETICAL_POSITION",
            {
                "baseline_gross": gross,
                "candidate_gross": gross * state["budget_multiplier"],
                "signals": signals,
                "actual_orders": 0,
            },
        )
    wait_until(bar_time(session, 74))
    frame = fetch()
    result = {
        "session": str(session),
        "state": state,
        "missed_decisions": failures,
        "validation_status": "INCOMPLETE"
        if failures or not state["state_valid"]
        else "SIGNAL_CAPTURE_COMPLETE_NOT_STRATEGY_ADMISSION",
        "snapshot": snapshot(frame, directory, f"final-{os.getpid()}"),
        "scenarios": theoretical_results(
            frame, session, signals, state["budget_multiplier"], state_valid=state["state_valid"]
        ),
    }
    if any(s["status"] != "COMPLETE" for s in result["scenarios"].values()):
        result["validation_status"] = "INCOMPLETE"
    ledger.append("result", "SESSION_RESULT", result)
    report = directory / "result.json"
    with report.open("x", encoding="utf-8") as handle:
        json.dump({**result, **LABELS}, handle, indent=2, allow_nan=False)
    print(json.dumps({"event": "COMPLETE", "status": result["validation_status"]}), flush=True)
    lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - never print credential-bearing adapter errors
        print(json.dumps({"event": "FATAL", "error_type": type(error).__name__}), flush=True)
        raise SystemExit(1) from None
