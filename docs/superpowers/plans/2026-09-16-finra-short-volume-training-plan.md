# FINRA Short-Volume Training Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and causally align training-only FINRA Consolidated NMS daily short-sale volume, then run a frozen 400-cell feasibility diagnostic without allocating a strategy version.

**Architecture:** A transport-independent parser/acquirer writes immutable daily partitions and manifests outside Git. A separate feature builder left-joins lagged FINRA flow onto every frozen event key. A pure diagnostic module evaluates the preregistered families and emits only hash-addressed summaries and a cell table.

**Tech Stack:** Python 3.12, urllib, pandas, PyArrow, pytest, Ruff, existing US intraday research helpers.

## Global Constraints

- Acquisition and feature selection are limited to 2021-01-01 through 2023-12-31.
- Use exact provider symbols; do not uppercase, normalize punctuation, or resolve collisions heuristically.
- `Last-Modified` is the earliest causal availability time; later corrections are never backdated.
- Missing or rejected files and symbol rows remain null and counted, never zero-filled.
- Require at least 95% covered event rows and 500 covered sessions across all three years before return computation.
- Evaluate exactly 400 cells: 5 families x 5 decision bars x 4 holding bars x 4 top counts.
- No strategy version, development/consumed data, Paper activation, broker import, or order route.

---

### Task 1: Immutable FINRA daily-file acquisition

**Files:**
- Create: `src/us_intraday_lab/data/finra_short_volume_acquisition.py`
- Create: `tests/unit/data/test_finra_short_volume_acquisition.py`

**Interfaces:**
- Produces: `parse_daily_file(body: bytes, expected_date: date) -> pd.DataFrame`
- Produces: `fetch_daily_file(transport, trade_date, ...) -> tuple[pd.DataFrame, dict[str, object]]`
- Produces: `acquire_sessions(root: Path, sessions: Sequence[date], transport) -> list[dict[str, object]]`
- Produces: `FinraShortVolumeHttpTransport.__call__(trade_date) -> HttpPayload`

- [ ] **Step 1: Write failing parser, correction, retry, resume, and boundary tests**

Use synthetic bodies with the exact six-column header and numeric footer. Assert exact-case symbols survive, a footer mismatch/duplicate/negative/short-over-total row fails closed, `Last-Modified` parses as UTC, transient 429 retries preserve the date, accepted partitions resume by hash, partial pairs fail, and 2024 raises `FINRA_SHORT_VOLUME_ACQUISITION_TRAINING_ONLY`.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/data/test_finra_short_volume_acquisition.py -q`

Expected: collection failure because the module does not exist.

- [ ] **Step 3: Implement the minimal immutable acquirer**

Define a frozen `HttpPayload(body, status, headers, url)`, validate the header/footer and every row, compute SHA-256 before parsing, and write Parquet plus JSON through temporary files followed by atomic replace. Manifest fields must include `trade_date`, `last_modified`, `response_sha256`, `content_sha256`, `etag`, `row_count`, `footer_count`, `complete`, and `training_only`. Retry only 429/500/502/503/504 and transport timeouts with bounded exponential backoff.

- [ ] **Step 4: Run tests and lint**

Run: `pytest tests/unit/data/test_finra_short_volume_acquisition.py -q`

Expected: all tests pass.

Run: `ruff check src/us_intraday_lab/data/finra_short_volume_acquisition.py tests/unit/data/test_finra_short_volume_acquisition.py`

Expected: `All checks passed!`

- [ ] **Step 5: Commit**

Run: `git add -- src/us_intraday_lab/data/finra_short_volume_acquisition.py tests/unit/data/test_finra_short_volume_acquisition.py && git commit -m "Add immutable FINRA short-volume acquisition"`

### Task 2: Acquisition CLI and causal coverage audit

**Files:**
- Create: `scripts/acquire_finra_short_volume_training.py`
- Create: `scripts/audit_finra_short_volume_training.py`
- Create: `tests/unit/test_audit_finra_short_volume_training.py`

**Interfaces:**
- Consumes: Task 1 manifests and partitions plus `v14309_v14408_events.parquet`.
- Produces: `build_coverage(events, partitions, manifests) -> tuple[pd.DataFrame, dict[str, object]]`
- Produces: `research/results/2026-09-16-finra-short-volume-training-coverage.{json,md}`.

For any file whose CDN `Last-Modified` is after its trade date, snapshot the
official FINRA monthly index and record its response hash. An exact file listed
once without `Updated` receives the documented 18:00 ET original availability;
all other cases retain the later CDN timestamp and fail closed.

- [ ] **Step 1: Write failing audit tests**

Create events on two sessions and source files with one same-day publication and one later correction. Assert strict `last_modified < decision_cutoff`, exact-symbol matching, preserved event row order, null reasons (`MISSING_SESSION`, `SOURCE_NOT_YET_AVAILABLE`, `SYMBOL_NOT_FOUND`), year/session counts, and a blocked result below 95%.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/test_audit_finra_short_volume_training.py -q`

Expected: collection failure because the audit script does not exist.

- [ ] **Step 3: Implement CLI and audit**

The acquisition CLI derives distinct 2021-2023 sessions from the frozen event cache and requests each corresponding FINRA session once. The audit derives the previous event-calendar session, maps its immutable partition, applies Last-Modified at the event's New York decision timestamp, and left-joins exact symbols. Reports include expected/acquired/accepted/rejected sessions, response hashes, event coverage, per-year coverage, missing-reason counts, symbol-match counts, and `PASS` only when all frozen gates hold.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/unit/test_audit_finra_short_volume_training.py tests/unit/data/test_finra_short_volume_acquisition.py -q`

Run: `ruff check scripts/acquire_finra_short_volume_training.py scripts/audit_finra_short_volume_training.py tests/unit/test_audit_finra_short_volume_training.py`

Expected: all tests and lint pass.

Run: `git add -- scripts/acquire_finra_short_volume_training.py scripts/audit_finra_short_volume_training.py tests/unit/test_audit_finra_short_volume_training.py && git commit -m "Add FINRA training coverage audit"`

### Task 3: Causal event feature cache

**Files:**
- Create: `src/us_intraday_lab/data/finra_short_volume_features.py`
- Create: `scripts/build_finra_short_volume_training_features.py`
- Create: `tests/unit/data/test_finra_short_volume_features.py`

**Interfaces:**
- Consumes: validated partitions/manifests, frozen event cache, existing source-session prices.
- Produces: `build_features(events, daily_flow, daily_prices) -> pd.DataFrame`
- Produces externally: `research/cache/us_market_finra_short_volume_training_v1.parquet`.

- [ ] **Step 1: Write failing feature tests**

Assert the output preserves every event key and order; computes raw ratios, 5/20-session trailing statistics, 20-session z-score with a ten-observation minimum, source-date cross-sectional percentiles, one-session change, and prior return interaction; and preserves nulls/counts when history is insufficient.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/data/test_finra_short_volume_features.py -q`

Expected: collection failure because the module does not exist.

- [ ] **Step 3: Implement the feature builder**

Build symbol-level rolling values on distinct source sessions before expanding to event keys. Use `min_periods` explicitly, stable merges with `validate=` contracts, and fail on duplicate event keys. Write the external cache atomically and print row count, null counts, date bounds, and SHA-256.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/unit/data/test_finra_short_volume_features.py tests/unit/test_audit_finra_short_volume_training.py -q`

Run: `ruff check src/us_intraday_lab/data/finra_short_volume_features.py scripts/build_finra_short_volume_training_features.py tests/unit/data/test_finra_short_volume_features.py`

Expected: all tests and lint pass.

Run: `git add -- src/us_intraday_lab/data/finra_short_volume_features.py scripts/build_finra_short_volume_training_features.py tests/unit/data/test_finra_short_volume_features.py && git commit -m "Build causal FINRA short-volume features"`

### Task 4: Frozen 400-cell training diagnostic

**Files:**
- Create: `src/us_intraday_lab/finra_short_volume_feasibility.py`
- Create: `scripts/diagnose_finra_short_volume_training.py`
- Create: `tests/unit/test_finra_short_volume_feasibility.py`

**Interfaces:**
- Consumes: frozen events and Task 3 feature cache.
- Produces: `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`
- Produces externally: `research/finra-short-volume-training-feasibility-v1.parquet`.
- Produces tracked: `research/results/2026-09-16-finra-short-volume-training-feasibility-summary.{json,md}`.

- [ ] **Step 1: Write failing grid and boundary tests**

Assert five named families, 400 unique cells, full-session joint ranking, long-only gross exposure no greater than one, close-flat holdings, 9/18 bp and delayed variants, exact retention floors, rejected nontraining dates, and summary fields `strategy_versions_created=0`, `paper_activation=false`, and `order_route=FORBIDDEN`.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/test_finra_short_volume_feasibility.py -q`

Expected: collection failure because the module does not exist.

- [ ] **Step 3: Implement the pure diagnostic and renderer**

Reuse the established event-return accounting semantics from the news diagnostic without importing broker modules. Rank all valid symbols per `(session_date, bar_idx)`, compute session portfolio returns, calendar-year metrics, IR, maximum drawdown, and stress variants, then retain only exact frozen-gate passes. The development-acquisition decision is `ACQUIRE_DEVELOPMENT_FINRA_SHORT_VOLUME` only when at least two families are represented; otherwise use `ABANDON_FINRA_SHORT_VOLUME_NO_VERSION_CREATED`.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/unit/test_finra_short_volume_feasibility.py -q`

Run: `ruff check src/us_intraday_lab/finra_short_volume_feasibility.py scripts/diagnose_finra_short_volume_training.py tests/unit/test_finra_short_volume_feasibility.py`

Expected: all tests and lint pass.

Run: `git add -- src/us_intraday_lab/finra_short_volume_feasibility.py scripts/diagnose_finra_short_volume_training.py tests/unit/test_finra_short_volume_feasibility.py && git commit -m "Add frozen FINRA training diagnostic"`

### Task 5: Production training run, evidence, and phase memory

**Files:**
- Create: `research/results/2026-09-16-finra-short-volume-training-coverage.json`
- Create: `research/results/2026-09-16-finra-short-volume-training-coverage.md`
- Create if the gate passes: `research/results/2026-09-16-finra-short-volume-training-feasibility-summary.json`
- Create if the gate passes: `research/results/2026-09-16-finra-short-volume-training-feasibility-summary.md`
- Create outside this worktree: `G:/quant-agent-team-us/memory/2026-09-16-finra-short-volume-training-local.md`

- [ ] **Step 1: Acquire 2021-2023 files and audit coverage**

Run the acquisition against `E:/us-intraday-lab-data/us-market`, then run the audit. Do not continue to feature/return computation unless the frozen gate says `PASS`.

- [ ] **Step 2: If coverage passes, build features and run all 400 cells**

Require complete status, exact cache/input hashes, 400 completed cells, and a native cell-table hash. Do not acquire development data in the same step.

- [ ] **Step 3: Run verification**

Run all new focused tests, all data tests, Ruff on changed Python files, then the full suite. Compare any full-suite failures with the frozen 16-failure baseline before attributing regressions.

- [ ] **Step 4: Record fallback memory and commit evidence**

The local memory must include `summary`, `stage`, `kpi_version`, `tags`, and `next_step`, including mandatory tags `project:quant-agent-team`, `market:cn_a`, and `freq:daily`, plus US intraday tags. Commit only code and publishable summaries; keep raw files, manifests, caches, checkpoints, and state untracked.

- [ ] **Step 5: Push and continue**

Push the branch, verify only `state/` remains untracked in this worktree, and immediately select the next genuinely distinct contract if this one is falsified. Never shut down the machine without a fresh explicit request.
