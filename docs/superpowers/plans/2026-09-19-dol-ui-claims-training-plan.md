# DOL Weekly UI-Claims Labor-Shock Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze official 2021-2023 DOL weekly claims first releases, map each to strictly pre-publication SPY beta in the fixed 527-symbol training cube, and run the preregistered 400-cell feasibility screen only after a hard source/coverage pass.

**Architecture:** An archive module freezes three official year-index responses and their exact linked PDFs with hash-verified first-page extraction. A feature module computes two strictly prior-12-release innovations and prior-60-paired-session SPY beta, emitting explicit missingness. A feasibility module checks source/feature coverage before any outcome read and conditionally runs a custom no-missing-as-cash evaluator.

**Tech Stack:** Python 3.12, official DOL archive HTML/PDF, `pypdf` or `pdftotext` from available runtime, pandas/NumPy/pyarrow, pytest, Ruff, existing intraday cost/metric contracts.

## Global Constraints

- Frozen cube SHA-256: `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`; select only 2021-2023 and exactly 527 symbols. State **coverage-limited sample, not full market**.
- Source: three official archive form responses (`report=press`, year 2021/2022/2023), then only their exact 156 linked PDF URLs. Freeze request, URL, HTTP metadata, retrieval time, raw bytes and SHA-256; no current `data.pdf`, guessed URLs, revised series, mirror, login or key. One request per second maximum.
- Require 52/52/52 unique PDFs. Extract only first-page 8:30 ET embargo date, advance seasonally adjusted initial claims and advance seasonally adjusted insured unemployment; preserve parse errors and exact source hashes.
- Availability: first frozen sample session strictly after PDF publication date, active one session. Exposure: exactly 60 finite paired bar-5 symbol/SPY opening returns strictly **before publication date**; SPY excluded; no sign filter, alias or industry guess.
- Innovations: current first-published value minus strictly prior-12-complete-release median. Five families: initial deterioration/improvement, insured deterioration/improvement, concordant deterioration. Improvement ranks high SPY beta; deterioration ranks low SPY beta; symbol ascending ties.
- Coverage before outcome load: all 156 source hashes/first pages complete; at least 200 unique beta-eligible non-SPY symbols, 150 symbols on 100 distinct availability sessions, 20,000 pairs; each family at least 30 active releases and five per year.
- Grid: exactly five families × `(2,5,11,17,23)` decision bars × `(1,2,4,6)` holding bars × `(1,3,5,10)` top counts = 400. Standard/stress costs 9/18 bp and one-bar delay at 9 bp. Per-cell 40 signal sessions, 10/year, >=20% annualized net, IR>=0.8, drawdown<20%, two positive years, positive stress/delay; at least two families retained. Never turn missing selected outcomes into zero/cash.
- No development/consumed ranking, version creation, broker, submit/cancel, Paper activation, pool modification, order route or shutdown. Stage tests, tagged fallback memory and push after each checkpoint.

---

### Task 1: Official year-index inventory and immutable PDF capture

**Files:** Create `src/us_intraday_lab/data/dol_ui_claims_archive.py`, `scripts/acquire_dol_ui_claims_training.py`, `tests/unit/data/test_dol_ui_claims_archive.py`.

**Interfaces:** `discover_pdf_links(year_html: bytes, year: int) -> pd.DataFrame` returns ordered `(release_date,pdf_url)` exact official links. `freeze_year_indexes(fetch, root: Path) -> dict` stores three raw HTML responses and the immutable 156-link manifest. `acquire_pdfs(fetch, root: Path) -> dict` only consumes that frozen manifest and writes raw PDFs, hashes and missingness.

- [ ] Write RED local-fixture tests for 52/52/52 exact links, duplicate/host/date mismatch rejection, source-hash replay, and no PDF fetch before the year-index manifest exists. For example:

```python
def test_official_year_parser_rejects_duplicate_release():
    html = b'<a href="/press/2021/010721.pdf">7</a>' * 2
    with pytest.raises(ValueError, match="duplicate"):
        discover_pdf_links(html, 2021)
```

- [ ] Run `python -m pytest tests/unit/data/test_dol_ui_claims_archive.py -q` and confirm missing-behavior RED. Implement exact link/date parser, immutable writes, 1-request/second fetch wrapper and separate index/PDF stages. Run focused pytest, Ruff and `git diff --check`; commit/push with tagged fallback memory. **Do not fetch 2021-2023 PDFs before this source inventory code and the spec are committed.**

### Task 2: First-page extraction and causal labor/exposure features

**Files:** Create `src/us_intraday_lab/data/dol_ui_claims_features.py`, `scripts/build_dol_ui_claims_training_features.py`, `tests/unit/data/test_dol_ui_claims_features.py`.

**Interfaces:** `extract_first_page(pdf: bytes, expected_date: date) -> dict` returns the explicit publication date and exactly two first-published integer values. `build_release_features(events: pd.DataFrame, claims: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]` returns release states and symbol-release beta exposure with reasons.

- [ ] Write RED fixtures showing no use of later PDF pages/revisions, ambiguous or absent first-page measure rejection, release-day exclusion, 12 strictly prior medians, 60 strictly pre-publication bar-5 pairs, invalid duplicate key, SPY exclusion, missing history, and high/low beta tie order. The core future-leak assertion is:

```python
base = build_release_features(events, claims)[1]
altered = events.copy()
altered.loc[altered.session_date.ge(release_date), "session_return"] = 999.0
assert build_release_features(altered, claims)[1].beta.equals(base.beta)
```

- [ ] Verify RED, implement the minimal parser and feature builder, then run focused pytest/Ruff/diff checks. Build only from a hash-verified cube with a pushed-down 2021-2023 filter; preserve all 527 symbols and exclusion reasons. Commit/push with tagged fallback memory.

### Task 3: Hard coverage gate and conditional 400-cell evaluator

**Files:** Create `src/us_intraday_lab/dol_ui_claims_feasibility.py`, `scripts/diagnose_dol_ui_claims_training.py`, `tests/unit/test_dol_ui_claims_feasibility.py`.

**Interfaces:** `coverage_gate(source_manifest: dict, states: pd.DataFrame, exposures: pd.DataFrame) -> dict` produces every frozen floor without an outcome path. `specifications() -> tuple[Specification,...]` returns exactly 400 unique cells. `run_diagnostic(...) -> tuple[pd.DataFrame,dict]` loads event outcome columns only after `coverage_gate(...)["passed"]` is true.

- [ ] Write RED boundary tests for 51 vs 52 PDF/year, 199 vs 200 unique symbols, 99 vs 100 150-symbol sessions, 19,999 vs 20,000 pairs, 29 vs 30 family releases, four vs five/year, and all 400 unique specs. Add a failed-gate test with a nonexistent outcome path and assert `cells_completed == 0` plus `post_availability_outcomes_loaded is False`.
- [ ] Implement gate first and verify focused tests green. Then write RED tests that a selected symbol with a missing entry/exit price invalidates the signal day/cell rather than becoming a zero-return day or replacement stock. Implement a custom evaluator sharing the existing metric definitions only where they preserve this contract; do not reuse an evaluator that ranks on current-session return or zero-fills missing outcomes.
- [ ] Enforce the frozen cost/delay/annual return/IR/drawdown/calendar-year floors, status COMPLETE, and at least two retained families for a development-data **suggestion only**. Run focused tests, Ruff and diff check; commit/push with tagged fallback memory.

### Task 4: Sequential source acquisition and terminal evidence

**Files:** External raw/derived `E:\us-intraday-lab-data\us-market\research\cache\dol_ui_claims_training_v1`; tracked `research/results/2026-09-19-dol-ui-claims-training-feasibility-summary.json/.md` and tagged `memory/2026-09-19-dol-ui-claims-training-local.md`.

- [ ] Fetch and hash the three official year-index responses sequentially; assert exact unique 52/52/52 dated links and commit the source inventory checkpoint before downloading any training PDF.
- [ ] Fetch only exact linked PDFs sequentially at <=1 request/second; preserve raw bytes, status, errors and SHA-256. Verify all 156 first pages, fields, dates, source hashes and 527-symbol training cube hash before the coverage gate.
- [ ] Build strictly causal features and run the frozen source/exposure/family coverage gate **before** loading post-availability outcomes. On failure, freeze `ABANDON_DOL_UI_CLAIMS_COVERAGE_GATE` with zero cells and no tuning. On pass, run exactly 400 frozen cells; a training pass only recommends development-data acquisition.
- [ ] Check raw/derived hashes and complete cell counts, run focused tests/Ruff/`git diff --check` and full pytest, document unrelated baseline failures, commit/push only publishable source code, source/terminal summaries and tagged fallback memory. Keep raw PDFs, extracted text, caches, cells and `state/` outside Git.
