# SEC Fundamental Filing Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a causal, immutable 2021-2023 SEC `10-Q` accounting-change feasibility screen for the fixed 527-symbol research sample.

**Architecture:** A data-contract module freezes exact SEC ticker-to-CIK identity, parses accession-linked submissions and Company Facts, and derives five filing-level accounting changes. A feature builder activates each filing on the next event-cube session for five sessions. A configured diagnostic ranks the available sample cross-section and evaluates exactly 400 frozen cells.

**Tech Stack:** Python 3.12, pandas, NumPy, urllib, Parquet/Zstandard, pytest, Ruff, existing configurable regime diagnostic.

## Global Constraints

- Training dates are exactly 2021-01-01 through 2023-12-31.
- The event cube SHA-256 is exactly `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9` and contains exactly 527 distinct sample symbols.
- Exact case-sensitive SEC ticker matches only; preserve all 65 initial unmatched symbols as `SEC_IDENTITY_UNAVAILABLE`.
- Original `10-Q` accessions only; accession-to-fact linkage is mandatory.
- Availability starts on the first event session strictly after filing date and expires after five event sessions.
- Acquisition is sequential at no more than four requests per second and preserves raw response hashes.
- Exactly 400 cells with 9 bp standard, 18 bp stress, and one-bar delay at 9 bp.
- No development or consumed dates, strategy version, broker import, pool mutation, Paper activation, submit/cancel path, or order route.

---

### Task 1: SEC identity and filing parser contract

**Files:**
- Create: `src/us_intraday_lab/data/sec_fundamental_filings.py`
- Create: `tests/unit/data/test_sec_fundamental_filings.py`

**Interfaces:**
- Produces: `parse_ticker_map(body: bytes, symbols: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]`
- Produces: `parse_submissions(body: bytes, cik: int) -> pd.DataFrame`
- Produces: `parse_companyfacts(body: bytes, cik: int) -> pd.DataFrame`

- [ ] **Step 1: Write failing exact-identity and accession tests**

Create fixtures with two exact ticker matches, one unmatched ticker, one `10-Q`, one `10-Q/A`, and Company Facts rows sharing the original accession. Assert exact matches only, explicit unmatched reasons, exclusion of the amendment from signals, and rejection of CIK/accession mismatches.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Expected: collection fails because `us_intraday_lab.data.sec_fundamental_filings` does not exist.

- [ ] **Step 3: Implement strict parsers**

Implement schema validation, exact ticker matching, ten-digit CIK normalization, columnar submissions expansion, original-`10-Q` filtering, USD-unit extraction, and immutable key checks. Return normalized tables without deriving returns or reading later periods.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Run: `ruff check src/us_intraday_lab/data/sec_fundamental_filings.py tests/unit/data/test_sec_fundamental_filings.py`

Expected: all tests and lint pass.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/sec_fundamental_filings.py tests/unit/data/test_sec_fundamental_filings.py
git commit -m "Implement SEC filing data contract"
```

### Task 2: Resumable immutable SEC acquisition

**Files:**
- Create: `scripts/acquire_sec_fundamental_filings_training.py`
- Modify: `tests/unit/data/test_sec_fundamental_filings.py`

**Interfaces:**
- Produces: `acquire_training_snapshot(symbols: set[str], fetch: Callable[[str], bytes], raw_root: Path) -> tuple[pd.DataFrame, dict[str, object]]`
- Produces external normalized filing Parquet and immutable manifest.

- [ ] **Step 1: Add failing acquisition tests**

Use a fake fetcher to assert the exact ticker-map URL, exact CIK URLs, one fetch per exact-matched issuer, raw-byte SHA-256 provenance, immutable collision rejection, resume from byte-identical raw files, and absence of any request for unmatched symbols.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Expected: acquisition tests fail because `acquire_training_snapshot` is missing.

- [ ] **Step 3: Implement acquisition and CLI**

Use official SEC URLs, a declared user agent, 0.25-second minimum spacing, bounded retry for `429` and `5xx`, and atomic immutable writes. Store raw JSON under the external `raw_root`; publish only secret-free hashes, URLs, counts, reasons, and the normalized training snapshot.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Run: `ruff check src/us_intraday_lab/data/sec_fundamental_filings.py scripts/acquire_sec_fundamental_filings_training.py tests/unit/data/test_sec_fundamental_filings.py`

Expected: all tests and lint pass.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/sec_fundamental_filings.py scripts/acquire_sec_fundamental_filings_training.py tests/unit/data/test_sec_fundamental_filings.py
git commit -m "Acquire immutable SEC filing training data"
```

### Task 3: Accounting changes and causal event features

**Files:**
- Modify: `src/us_intraday_lab/data/sec_fundamental_filings.py`
- Modify: `tests/unit/data/test_sec_fundamental_filings.py`
- Create: `scripts/build_sec_fundamental_filing_training_features.py`

**Interfaces:**
- Produces: `derive_filing_features(filings: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_event_features(events: pd.DataFrame, filing_features: pd.DataFrame, identity: pd.DataFrame) -> pd.DataFrame`
- Output columns: `revenue_growth_acceleration`, `gross_margin_expansion`, `operating_margin_expansion`, `cash_asset_improvement`, `deleveraging`, and `coverage_reason`.

- [ ] **Step 1: Add failing feature tests**

Construct quarterly facts with exact accessions and known prior-year/prior-quarter comparisons. Assert tag priority, 70-110-day duration validation, 330-400-day prior-year matching, 70-110-day prior-quarter matching, first-session-after-filing availability, five-session expiry, explicit structural missingness, and no feature on the filing session.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Expected: feature tests fail because the derivation and join functions are missing.

- [ ] **Step 3: Implement filing and event features**

Select canonical facts by frozen priority and exact accession, derive the five accounting changes, winsorize finite active-session cross-sections at 1%/99%, convert them to percentiles, and join them to every event key without imputing missing values. Emit deterministic coverage reasons.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/data/test_sec_fundamental_filings.py -q`

Run: `ruff check src/us_intraday_lab/data/sec_fundamental_filings.py scripts/build_sec_fundamental_filing_training_features.py tests/unit/data/test_sec_fundamental_filings.py`

Expected: all tests and lint pass.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/sec_fundamental_filings.py scripts/build_sec_fundamental_filing_training_features.py tests/unit/data/test_sec_fundamental_filings.py
git commit -m "Build causal SEC filing features"
```

### Task 4: Acquisition gate and 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/sec_fundamental_filing_feasibility.py`
- Create: `tests/unit/test_sec_fundamental_filing_feasibility.py`
- Create: `scripts/diagnose_sec_fundamental_filing_training.py`

**Interfaces:**
- Produces: `coverage_gate(filing_features: pd.DataFrame) -> dict[str, object]`
- Produces: `specifications() -> tuple[Specification, ...]`
- Produces: `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`

- [ ] **Step 1: Write failing gate, grid, and direction tests**

Assert that fewer than 300 issuers, fewer than four valid events per counted issuer, or fewer than 1,200 feature-bearing events blocks return evaluation. Assert exactly 400 unique cells and that a larger positive accounting percentile plus a larger causal intraday-return percentile receives the higher score.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/test_sec_fundamental_filing_feasibility.py -q`

Expected: collection fails because the feasibility module does not exist.

- [ ] **Step 3: Implement gate, configured diagnostic, and report CLI**

Reuse the tested configurable regime diagnostic only after the coverage gate passes. Override family names, diagnostic ID, proceed decision, and exact abandon decision. The CLI must verify event and feature hashes, publish immutable Parquet/JSON/Markdown evidence, and report zero strategy versions and forbidden order routing.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/test_sec_fundamental_filing_feasibility.py -q`

Run: `ruff check src/us_intraday_lab/sec_fundamental_filing_feasibility.py scripts/diagnose_sec_fundamental_filing_training.py tests/unit/test_sec_fundamental_filing_feasibility.py`

Expected: all tests and lint pass.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/sec_fundamental_filing_feasibility.py scripts/diagnose_sec_fundamental_filing_training.py tests/unit/test_sec_fundamental_filing_feasibility.py
git commit -m "Implement SEC filing feasibility diagnostic"
```

### Task 5: Execute, freeze, verify, remember, and publish

**Files:**
- Create: `research/results/2026-09-17-sec-fundamental-filing-training-feasibility-summary.json`
- Create: `research/results/2026-09-17-sec-fundamental-filing-training-feasibility-summary.md`
- External: `E:/us-intraday-lab-data/us-market/data/staging/sec_fundamental_filings_training_v1/`
- External: `E:/us-intraday-lab-data/us-market/research/cache/us_market_sec_fundamental_filing_training_v1.parquet`
- External: `E:/us-intraday-lab-data/us-market/research/sec-fundamental-filing-training-feasibility-v1.parquet`

**Interfaces:**
- Consumes the frozen event cube and exact source manifests.
- Produces one terminal coverage or 400-cell training decision.

- [ ] **Step 1: Acquire and freeze source data**

Run the acquisition CLI against the external staging root. Confirm exactly 527 requested sample symbols, exact-match identity counts, raw-source hashes, original-`10-Q` counts, and training-only boundaries.

- [ ] **Step 2: Apply the coverage gate**

If fewer than 300 issuers have at least four valid feature-bearing filings or fewer than 1,200 feature-bearing events exist, freeze `ABANDON_SEC_FUNDAMENTAL_FILINGS_COVERAGE_GATE` and do not evaluate returns. Otherwise build the immutable event-feature cache.

- [ ] **Step 3: Run the diagnostic to its terminal decision**

Require `status=COMPLETE`, `cells_completed=400`, and either at least two retained families or `ABANDON_SEC_FUNDAMENTAL_FILINGS_NO_VERSION_CREATED`.

- [ ] **Step 4: Verify all changed code and baseline regression**

Run focused tests, Ruff, `git diff --check`, and `python -m pytest -q`. Compare the full result with the known 16-test baseline; any new failure blocks publication.

- [ ] **Step 5: Freeze memory and publish evidence**

Write the required local fallback memory with `summary`, `stage`, `kpi_version`, tags `project:quant-agent-team`, `market:cn_a`, `freq:daily`, `market:us`, `freq:5min`, and `next_step`. Commit only publishable code/reports, leave raw data and `state/` untracked, and push `codex/v550-v649-second-strategy`.
