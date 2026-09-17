# CFTC Positioning Training Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an immutable, causally timed, training-only 400-cell feasibility diagnostic for CFTC TFF positioning.

**Architecture:** A data module validates the exact PRE response and derives conservative publication availability. A feature builder carries each released weekly state for at most 14 calendar days and joins it to the frozen event universe. A thin feasibility wrapper reuses the tested configurable regime diagnostic and emits immutable evidence.

**Tech Stack:** Python 3.12, pandas, urllib, Parquet/Zstandard, pytest, Ruff, existing `cboe_volatility_regime_feasibility` engine.

## Global Constraints

- Training dates are exactly 2021-01-01 through 2023-12-31.
- Dataset is exactly `gpe5-46if`; contracts are exactly `13874+`, `20974+`, `239742`, `1170E1`, and `043602`.
- Ordinary availability is report date plus eight calendar days; the seven frozen 2023 ION overrides use their official publication dates and become usable on the next equity session.
- A positioning state expires after 14 calendar days.
- Exactly 400 cells; 9 bp, 18 bp, and delayed-entry accounting; no development/consumed dates.
- No strategy version, broker import, Paper activation, pool mutation, order route, submit, or cancel path.

---

### Task 1: Official response parser and causal availability

**Files:**
- Create: `src/us_intraday_lab/data/cftc_positioning.py`
- Create: `tests/unit/data/test_cftc_positioning.py`

**Interfaces:**
- Produces: `parse_training_response(body: bytes) -> pd.DataFrame`
- Produces: `causal_available_date(report_date: date) -> date`
- Produces: `build_training_snapshot(fetch: Callable[[str], bytes]) -> tuple[pd.DataFrame, dict[str, object]]`

- [ ] **Step 1: Write failing parser and availability tests**

```python
def test_parser_requires_exact_contract_date_grid():
    result = parse_training_response(five_contract_two_week_json)
    assert result.groupby("contract_code").size().to_dict() == expected_counts

def test_ion_report_uses_actual_publication_next_session_boundary():
    assert causal_available_date(date(2023, 2, 14)) == date(2023, 3, 9)

def test_ordinary_report_uses_eight_calendar_day_lag():
    assert causal_available_date(date(2022, 6, 7)) == date(2022, 6, 15)
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/data/test_cftc_positioning.py -q`
Expected: collection failure because `us_intraday_lab.data.cftc_positioning` does not exist.

- [ ] **Step 3: Implement exact schema, contract, date, duplicate, count, numeric, and availability validation**

The parser must retain `report_date`, `available_date`, `contract_code`, `open_interest`, asset-manager long/short, and leveraged-money long/short. `build_training_snapshot` must request only the frozen dates and contract codes, require 156 rows per contract in the live run, and return response SHA-256 plus URL metadata.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/data/test_cftc_positioning.py -q && ruff check src/us_intraday_lab/data/cftc_positioning.py tests/unit/data/test_cftc_positioning.py`
Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/cftc_positioning.py tests/unit/data/test_cftc_positioning.py
git commit -m "Implement CFTC positioning acquisition contract"
```

### Task 2: Weekly-state event features

**Files:**
- Modify: `src/us_intraday_lab/data/cftc_positioning.py`
- Modify: `tests/unit/data/test_cftc_positioning.py`
- Create: `scripts/acquire_cftc_positioning_training.py`
- Create: `scripts/build_cftc_positioning_training_features.py`

**Interfaces:**
- Produces: `build_event_features(events: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame`
- Output feature columns: `spx_asset_mgr_z26`, `nasdaq_lev_money_z26`, `russell_divergence_z26`, `vix_lev_money_change_z26`, `treasury_asset_mgr_change_z26`, and `coverage_reason`.

- [ ] **Step 1: Write failing tests for release-date joining, 14-day expiry, and training-boundary filtering**

```python
def test_feature_join_uses_latest_released_state_and_expires_after_fourteen_days():
    result = build_event_features(events, positions)
    assert result.loc[result.session_date.eq(date(2022, 6, 16)), "coverage_reason"].iat[0] == "COVERED"
    assert result.loc[result.session_date.eq(date(2022, 7, 1)), "coverage_reason"].iat[0] == "CFTC_STATE_EXPIRED"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/data/test_cftc_positioning.py -q`
Expected: failure because `build_event_features` is missing.

- [ ] **Step 3: Implement normalized positioning, changes, rolling z-scores, backward as-of join, expiry, and atomic scripts**

Use net positions divided by open interest. Compute rolling 26-report z-scores per exact contract. Persist only training rows and event keys; output source and feature hashes.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/data/test_cftc_positioning.py -q && ruff check src/us_intraday_lab/data/cftc_positioning.py scripts/acquire_cftc_positioning_training.py scripts/build_cftc_positioning_training_features.py`
Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/cftc_positioning.py tests/unit/data/test_cftc_positioning.py scripts/acquire_cftc_positioning_training.py scripts/build_cftc_positioning_training_features.py
git commit -m "Build causal CFTC positioning features"
```

### Task 3: Frozen 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/cftc_positioning_feasibility.py`
- Create: `scripts/diagnose_cftc_positioning_training.py`
- Create: `tests/unit/test_cftc_positioning_feasibility.py`

**Interfaces:**
- Produces: `specifications() -> tuple[Specification, ...]`
- Produces: `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`

- [ ] **Step 1: Write failing grid and direction tests**

```python
def test_grid_has_exactly_400_unique_cells():
    grid = specifications()
    assert len(grid) == len(set(grid)) == 400

def test_vix_stress_family_ranks_loser_above_winner():
    scores = score_family(frame, "vix_leveraged_stress_reversal", FAMILY_FEATURES)
    assert scores.iloc[0] > scores.iloc[1]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/test_cftc_positioning_feasibility.py -q`
Expected: collection failure because the feasibility module does not exist.

- [ ] **Step 3: Implement the thin configured wrapper and immutable report CLI**

Use the existing configurable regime engine with the five frozen feature/direction pairs. Override diagnostic ID and decisions with `cftc-positioning-training-feasibility-v1`, `ACQUIRE_DEVELOPMENT_CFTC_POSITIONING`, and `ABANDON_CFTC_POSITIONING_NO_VERSION_CREATED`.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/unit/test_cftc_positioning_feasibility.py -q && ruff check src/us_intraday_lab/cftc_positioning_feasibility.py scripts/diagnose_cftc_positioning_training.py tests/unit/test_cftc_positioning_feasibility.py`
Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/cftc_positioning_feasibility.py scripts/diagnose_cftc_positioning_training.py tests/unit/test_cftc_positioning_feasibility.py
git commit -m "Implement CFTC positioning feasibility diagnostic"
```

### Task 4: Execute, freeze, verify, and publish

**Files:**
- Create: `research/results/2026-09-17-cftc-positioning-training-feasibility-summary.json`
- Create: `research/results/2026-09-17-cftc-positioning-training-feasibility-summary.md`
- External: `E:/us-intraday-lab-data/us-market/data/staging/cftc_positioning_training_v1.parquet`
- External: `E:/us-intraday-lab-data/us-market/research/cache/us_market_cftc_positioning_training_v1.parquet`
- External: `E:/us-intraday-lab-data/us-market/research/cftc-positioning-training-feasibility-v1.parquet`

**Interfaces:**
- Consumes frozen event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- Produces one `COMPLETE` 400-cell decision and immutable hashes.

- [ ] **Step 1: Acquire and build features**

Run the acquisition and feature CLIs against the paths above. Expected: 780 exact contract-report rows, 156 per contract, training-only event output, and no immutable collisions.

- [ ] **Step 2: Run the diagnostic with exact event and feature hashes**

Expected: `status=COMPLETE`, `cells_completed=400`, and either at least two retained families or the exact abandon decision.

- [ ] **Step 3: Run verification**

Run: `python -m pytest tests/unit/data tests/unit/test_cftc_positioning_feasibility.py -q`
Run: `ruff check` on all new/modified files.
Run: `python -m pytest -q` and compare failures with the frozen 16-test baseline.

- [ ] **Step 4: Write fallback memory, commit reports, and push**

The fallback memory must include `summary`, `stage`, `kpi_version`, mandatory `project:quant-agent-team`, `market:cn_a`, `freq:daily` tags, and `next_step`. Commit only publishable reports/code; leave external data and `state/` untracked. Push `codex/v550-v649-second-strategy`.
