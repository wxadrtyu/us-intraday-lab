# Daily Technical Multi-Factor Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the frozen 2021-2023 daily technical multi-factor training diagnostic without accessing development or consumed-period outcomes.

**Architecture:** A focused library module verifies the immutable SIP daily tree and execution cube, derives strictly lagged daily features, maps them onto execution sessions, and evaluates the fixed 400-cell grid. A thin CLI validates the output contract and writes immutable evidence artifacts.

**Tech Stack:** Python 3.12, pandas, NumPy, PyArrow, pytest, Ruff.

## Global Constraints

- Use only 2021-2023 outcomes from the 527-symbol coverage-limited sample.
- Daily source tree SHA-256 for filenames from 2020-07 through 2023-12 is `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`.
- Execution cube SHA-256 is `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- Evaluate exactly 400 cells with 9/18 bp costs and one-bar delay.
- Never read development/consumed outcomes or change Paper, broker, order-route, or monitoring state.

---

### Task 1: Strictly lagged daily features

**Files:**
- Create: `src/us_intraday_lab/daily_technical_multifactor.py`
- Create: `tests/unit/test_daily_technical_multifactor.py`

**Interfaces:**
- Produces: `build_daily_features(daily_bars: pd.DataFrame) -> pd.DataFrame`.
- Produces: `map_features_to_sessions(features: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame`.
- Produces: `score_family(frame: pd.DataFrame, family: str) -> pd.Series`.

- [ ] **Step 1: Write failing tests** for the exact rolling formulas, a same-date bar that must not map to the execution date, explicit missing history, and deterministic percentile-rank ties.
- [ ] **Step 2: Run `python -m pytest tests/unit/test_daily_technical_multifactor.py -q`** and confirm failures are missing imports/functions.
- [ ] **Step 3: Implement the minimum feature, mapping, and scoring functions** with stable symbol/date sorting and no forward fill.
- [ ] **Step 4: Re-run the focused tests** and require all tests to pass.
- [ ] **Step 5: Commit** the feature contract and tests.

### Task 2: Fixed 400-cell evaluator

**Files:**
- Modify: `src/us_intraday_lab/daily_technical_multifactor.py`
- Modify: `tests/unit/test_daily_technical_multifactor.py`

**Interfaces:**
- Produces: `run_diagnostic(*, daily_root: Path, event_cube_path: Path, expected_daily_sha256: str, expected_event_sha256: str) -> tuple[pd.DataFrame, dict[str, object]]`; the loader enumerates only 2020-07 through 2023-12 monthly files before hashing or opening them.

- [ ] **Step 1: Add failing tests** for cell count 400, standard/stress/delay price mapping, invalid-price rejection, the 500-session floor, and the two-family recommendation rule.
- [ ] **Step 2: Run the focused test module** and confirm the new assertions fail before implementation.
- [ ] **Step 3: Implement loading, hashing, ranking, return aggregation, metrics, and the frozen retention gate** exactly as specified.
- [ ] **Step 4: Run the focused tests and Ruff** with `python -m pytest tests/unit/test_daily_technical_multifactor.py -q` and `python -m ruff check src/us_intraday_lab/daily_technical_multifactor.py tests/unit/test_daily_technical_multifactor.py`.
- [ ] **Step 5: Commit** the evaluator.

### Task 3: Immutable runner and training execution

**Files:**
- Create: `scripts/diagnose_daily_technical_multifactor.py`
- Modify: `tests/unit/test_daily_technical_multifactor.py`
- Create after execution: `research/results/2026-10-12-daily-technical-multifactor-summary.json`
- Create after execution: `research/results/2026-10-12-daily-technical-multifactor-summary.md`
- Create externally after execution: `E:/us-intraday-lab-data/us-market/research/daily-technical-multifactor-v1.parquet`

**Interfaces:**
- CLI arguments: `--daily-root`, `--event-cube`, `--output-json`, `--output-parquet`, and `--output-md`.

- [ ] **Step 1: Add a failing CLI contract test** requiring immutable writes, exact hashes, `cells_completed == 400`, `development_or_consumed_loaded == false`, `paper_activation == false`, and `order_route == FORBIDDEN`.
- [ ] **Step 2: Implement the CLI** as a thin wrapper around `run_diagnostic`.
- [ ] **Step 3: Run focused tests and Ruff** over the library, script, and tests.
- [ ] **Step 4: Commit the implementation before production outcome access.**
- [ ] **Step 5: Run the production diagnostic exactly once** against the frozen inputs and inspect the immutable summary.
- [ ] **Step 6: Write the structured local-memory result**, commit result evidence, run final verification, and push.
