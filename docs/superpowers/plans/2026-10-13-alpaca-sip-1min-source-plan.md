# Alpaca SIP One-Minute Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire immutable, point-in-time full-market SIP one-minute bars with a bounded pilot and fail-closed coverage audit before any 5-10 minute strategy evaluation.

**Architecture:** A dedicated market-data-only module owns the frozen request grid, downloader, quality checks, atomic shard publication, and deep resume verification. A thin CLI loads the existing candidate asset snapshot, runs finite shard ranges, and reports exact source identities. A separate audit compares source bars to the frozen monthly point-in-time universe and required one-minute execution paths.

**Tech Stack:** Python 3.12, alpaca-py historical market-data client, pandas, PyArrow Parquet, exchange_calendars, pytest, Ruff, SHA-256.

## Global Constraints

- Namespace `alpaca_sip_1min_v1` on `E:\us-intraday-lab-data\us-market`; no raw files in Git.
- Candidate asset snapshot `alpaca-us-equity-assets-4cf36da00fead42b3b669620`, exactly 15,399 sorted symbols, SHA-256 `03af744e8cd30ef307251e9484ac08ec6d79fa4c8a4607a768cf45ba672d61c9`.
- Monthly eligible universe content SHA-256 `3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.
- First acquisition window 2021-01-01 through 2023-12-31; all dates consumed.
- Request `feed=sip`, `timeframe=1Min`, `adjustment=split`, point-in-time month-end or window-end `asof`, deterministic 100-symbol batches.
- Every missing or rejected symbol-minute remains explicit; no fill, cash substitution, zero return, or post-outcome deletion.
- No trading API, broker, Paper, order route, monitor-pool mutation, daily or overnight research, or issuer-event data.

---

### Task 1: Freeze one-minute contract and read-only downloader

**Files:**
- Create: `src/us_intraday_lab/data/alpaca_sip_one_minute.py`
- Create: `tests/unit/data/test_alpaca_sip_one_minute.py`

**Interfaces:**
- Produces: `SIP_ONE_MINUTE_NAMESPACE`, `ReadOnlyAlpacaSipOneMinuteDownloader.fetch(symbols, start, end, asof)`, `partition_specs(symbols, start, end, batch_size)`, `load_frozen_candidate_symbols`.

- [ ] Write tests that a fake historical data client receives `TimeFrame.Minute`, `DataFeed.SIP`, `Adjustment.SPLIT`, exact UTC date bounds and `asof`, while source imports contain no trading client.
- [ ] Run `python -m pytest tests/unit/data/test_alpaca_sip_one_minute.py -q`; confirm missing-module failure.
- [ ] Implement the downloader and deterministic month/batch grid with request identity hashed from provider, feed, bar size, adjustment, bounds, asof, batch size, and symbols.
- [ ] Re-run focused tests and Ruff; commit the passing contract.

### Task 2: Add causal regular-session normalization and quality checks

**Files:**
- Modify: `src/us_intraday_lab/data/alpaca_sip_one_minute.py`
- Modify: `tests/unit/data/test_alpaca_sip_one_minute.py`

**Interfaces:**
- Produces: `normalize_one_minute_bars(frame, asof)`, `quality_report(frame, requested, start, end, asof)`.

- [ ] Write failing fixtures for exact XNYS open/close filtering, duplicate `(symbol,timestamp)`, off-grid seconds, invalid OHLC, missing required values, negative volume/trade count, nonpositive VWAP, unexpected symbol, and source tag mismatch.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement normalization that preserves provider source-row and excluded-row counts plus a fail-closed quality report. Empty observations remain explicit and are never fabricated.
- [ ] Re-run focused tests and Ruff; commit the passing validation stage.

### Task 3: Add atomic shards and verified resume

**Files:**
- Modify: `src/us_intraday_lab/data/alpaca_sip_one_minute.py`
- Modify: `tests/unit/data/test_alpaca_sip_one_minute.py`

**Interfaces:**
- Produces: `acquire_sip_one_minute_shards(root, downloader, symbols, start, end, batch_size, shard_start, shard_stop)` and `validate_sip_one_minute_source(root, symbols, start, end, batch_size)`.

- [ ] Write failing temporary-directory tests for one shard, exact content hash, complete request manifest, provider invalid-symbol rejection ledger, atomic resume, corrupt Parquet refusal, missing contract refusal, partial file refusal, and mismatched identity refusal.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement exclusive acquisition contract, temporary Parquet/manifest publication, exact source-row accounting, SHA-256, deep resume checks, bounded retries, and finite shard slices.
- [ ] Re-run focused tests and Ruff; commit the passing storage stage.

### Task 4: Add CLI and bounded immutable pilot

**Files:**
- Create: `scripts/acquire_us_market_sip_one_minute.py`
- Modify: `tests/unit/data/test_alpaca_sip_one_minute.py`
- Create after run: `research/results/2026-10-13-alpaca-sip-1min-immutable-pilot.json`

**Interfaces:**
- Consumes: Task 1-3 source module.
- Produces: immutable pilot shards under a separate E: pilot root, plus a tracked pilot summary with hashes and missingness.

- [ ] Write failing CLI tests for exact candidate snapshot/hash, required shard bounds, no unbounded default, and safe one-session pilot invocation.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement the CLI with explicit root, asset snapshot, protocol, start/end, batch size, and required finite shard start/stop.
- [ ] Run the same 100-symbol, 2025-12-30 representative pilot in a separate immutable namespace, verify all shard hashes, measure latency and bytes, and retain provider rejections and missing symbols.
- [ ] Run tests and Ruff, record `project:quant-agent-team`, `market:cn_a`, `freq:intraday` memory, commit summary, and push.

### Task 5: Gate bulk acquisition and coverage

**Files:**
- Create: `scripts/audit_us_market_sip_one_minute.py`
- Create: `tests/unit/data/test_sip_one_minute_audit.py`
- Create after audit: `research/results/2026-10-13-alpaca-sip-1min-capacity-gate.json`

**Interfaces:**
- Consumes: immutable pilot and frozen monthly SIP-v2 eligible universe.
- Produces: capacity decision and exact month/session/clock coverage tables before any strategy outcome read.

- [ ] Write failing tests for conservative disk/time extrapolation, point-in-time monthly eligibility, symbol-minute and execution-path missingness, rejected symbol accounting, and fail-closed incomplete shard grids.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement capacity and coverage audits with exact identity checks and at least the frozen 95% eligible-path coverage floor.
- [ ] Re-run focused tests and Ruff; if capacity passes, acquire finite shard ranges with atomic resume. If coverage fails, freeze the source diagnosis without reading strategy returns.
- [ ] Record tagged memory, commit tracked evidence, and push. Raw shards and credentials remain untracked.
