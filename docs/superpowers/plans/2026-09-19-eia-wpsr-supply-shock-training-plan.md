# EIA WPSR Supply-Shock Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire official dated EIA WPSR Table 4 releases, build strictly lagged XLE-exposure inventory-draw signals for the fixed 527-symbol 2021-2023 training sample, and run the frozen 400-cell feasibility screen only if preregistered coverage passes.

**Architecture:** One source module extracts release-page and Table 4 URLs from the official archive and validates raw CSV rows while preserving every byte and hash. One feature module derives availability sessions, prior-12-release innovations, and prior-60-paired-session XLE betas. One feasibility module gates source and feature coverage before delegating to the existing intraday cost/delay evaluator.

**Tech Stack:** Python 3.12, pandas, NumPy, requests/urllib, BeautifulSoup if already installed, pyarrow, pytest, Ruff, existing `us_intraday_lab` evaluator.

## Global Constraints

- Event cube SHA-256 is `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`; use only its 2021-2023 527-symbol training sample and label it coverage-limited, not full market.
- Read only EIA's dated 2021-2023 WPSR archive issue pages and their exact linked Table 4 CSV files. No guessed URLs, live revised API, mirror, or 2024+ return/ranking data.
- Preserve raw index HTML, each issue HTML, each CSV, retrieval metadata, SHA-256, missing release, schema error, and duplicate. One request per second at most.
- Availability is first sample session strictly after the dated issue page's release date, active for one session. XLE reference beta uses exactly 60 paired distinct observed `bar_idx=5` morning-return sessions strictly before availability, with no missing-as-zero.
- Fixed Table 4 rows: `Commercial (Excluding SPR)`, `Total Motor Gasoline`, `Distillate Fuel Oil`, and `Total Stocks (Excluding SPR)`; parse their exact `Difference` values.
- Five families are the four positive draw innovations relative to strictly prior 12 release medians plus concordant positive innovation for at least two of crude/gasoline/distillate.
- Coverage: >=48 valid releases per year and >=150 total; >=150 non-XLE symbols beta-eligible on >=100 release sessions and >=20,000 symbol-release pairs; >=40 active releases per family and >=10 per family in each year.
- Grid: exactly 5 families x 5 decision bars `(2,5,11,17,23)` x 4 holding bars `(1,2,4,6)` x 4 top counts `(1,3,5,10)` = 400 cells. Costs 9/18 bp plus 1-bar delay at 9 bp. Retention criteria are copied verbatim from the design.
- Keep development/consumed ranking, strategy versions, Paper, observation-pool mutations, broker/submit/cancel, order routing, and shutdown forbidden.

---

### Task 1: Freeze the official source manifest and raw inventory

**Files:** Create `src/us_intraday_lab/data/eia_wpsr_archive.py`, `scripts/acquire_eia_wpsr_training.py`, and `tests/unit/data/test_eia_wpsr_archive.py`.

**Interfaces:** `discover_releases(index_html: bytes) -> pd.DataFrame` returns official page URLs and release dates for 2021-2023 only. `discover_table4(page_html: bytes, page_url: str) -> str` returns exactly one same-issue Table 4 CSV URL. `parse_table4(body: bytes, release_date: date) -> pd.DataFrame` returns four exact named Difference rows. `acquire(...) -> dict` writes immutable raw bytes plus hashes and missingness.

- [ ] Write RED tests using local HTML/CSV fixtures: one 2021, 2022, and 2023 issue link; duplicate/missing Table 4 rejection; exact four Difference rows; comma-number parsing; rejected changed source hash.
- [ ] Run `python -m pytest tests/unit/data/test_eia_wpsr_archive.py -q` and confirm expected missing-function failures.
- [ ] Implement an HTML parser that follows hrefs from the archive index, validates each issue page's stated release date and exact same-issue Table 4 href, stores raw bytes by date under the external staging root, and writes a manifest atomically. Treat any duplicate/date mismatch/schema drift as a named failure, not an inferred repair.
- [ ] Run focused pytest, `python -m ruff check src/us_intraday_lab/data/eia_wpsr_archive.py scripts/acquire_eia_wpsr_training.py tests/unit/data/test_eia_wpsr_archive.py`, and `git diff --check`; then commit/push source code and tagged fallback memory. Do not download training CSV until the source manifest parser and frozen spec are committed.

### Task 2: Causal prior-exposure feature contract

**Files:** Create `src/us_intraday_lab/data/eia_wpsr_features.py`, `scripts/build_eia_wpsr_training_features.py`, and `tests/unit/data/test_eia_wpsr_features.py`.

**Interfaces:** `build_release_features(events: pd.DataFrame, releases: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]` returns one release-state table and one symbol-release exposure table, both training-only with explicit exclusion reasons.

- [ ] Write RED tests for release-day exclusion, next-session-only activation, 12-release strictly prior median, 60 distinct strictly prior `bar_idx=5` matched sessions, exclusion of other decision bars and XLE from positions, no missing-as-zero, nonpositive beta exclusion, and lexicographic tie break.
- [ ] Run `python -m pytest tests/unit/data/test_eia_wpsr_features.py -q` and confirm failures are the missing behavior.
- [ ] Implement uniquely keyed `(symbol,session_date,bar_idx=5)` observed opening returns, reject duplicate rows, compute prior-60 paired beta against XLE and prior-12 Difference medians with `shift(1)` before rolling operations. Keep all 527 symbols in input inventory and preserve every coverage reason; do not read later periods.
- [ ] Run focused pytest, Ruff, and diff checks; commit/push feature code and stage memory.

### Task 3: Frozen coverage and return diagnostic

**Files:** Create `src/us_intraday_lab/eia_wpsr_feasibility.py`, `scripts/diagnose_eia_wpsr_training.py`, and `tests/unit/test_eia_wpsr_feasibility.py`.

**Interfaces:** `coverage_gate(source_manifest: dict, release_features: pd.DataFrame, exposures: pd.DataFrame) -> dict` returns named hard-gate metrics before any outcome input. `specifications() -> tuple[Specification, ...]` returns exactly 400 unique cells. `run_diagnostic(...) -> dict` performs existing-evaluator calls only if the gate passes.

- [ ] Write RED tests for each threshold boundary (47 vs 48/year, 149 vs 150 total, 149 vs 150 symbols, 99 vs 100 sessions, 19,999 vs 20,000 pairs, 39 vs 40 family releases, 9 vs 10/year), missing hashes, and exactly 400 distinct specifications.
- [ ] Run `python -m pytest tests/unit/test_eia_wpsr_feasibility.py -q` to verify RED.
- [ ] Implement the fail-closed gate; only on pass load post-availability returns, run the 9 bp, 18 bp, and one-bar delay evaluations, enforce >=40 independent signal sessions plus >=10/year, >=20% full-calendar annualized net return, IR >=0.8, max drawdown <20%, >=2 positive years, and positive stress/delay annualized returns. Require retained cells in >=2 families; otherwise reject without version creation.
- [ ] Run focused pytest, Ruff, and diff checks; commit/push diagnostic code and stage memory.

### Task 4: Sequential training acquisition and terminal freeze

**Files:** Create `research/results/2026-09-19-eia-wpsr-supply-shock-training-feasibility-summary.json`, adjacent Markdown summary, and tagged `memory/2026-09-19-eia-wpsr-training-local.md`.

- [ ] Acquire archive index and issue-page HTML sequentially. Verify the complete 2021-2023 URL inventory and publish immutable hashes before retrieving any Table 4 training CSV. Then retrieve only exact page-linked CSVs sequentially at <=1 request/second and hash each immediately.
- [ ] Run source/schema/coverage diagnostics before any return evaluation. If any gate fails, freeze complete failure evidence with `cells_completed=0` and no returns loaded. Do not relax a gate or add a mirror.
- [ ] If and only if coverage passes, build causal features and run all 400 frozen cells. Require `status=COMPLETE`, `cells_completed=400`, raw/derived hashes consistent, and no later-period or execution path.
- [ ] Run focused tests, Ruff, `git diff --check`, and `python -m pytest -q`; document unrelated baseline failures separately. Commit/push only publishable code, preregistration, summary, and fallback memory. Keep raw files, caches, cells, and `state/` outside Git.
