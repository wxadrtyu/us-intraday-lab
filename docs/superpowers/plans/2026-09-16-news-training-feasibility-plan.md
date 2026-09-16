# Point-in-Time News Training Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate the frozen 400-cell, training-only news grid and decide whether development news acquisition is economically justified without creating a strategy version.

**Architecture:** One pure diagnostic module validates immutable inputs, constructs frozen cross-sectional scores, computes three return scenarios, and applies the retention/breadth rule. A thin CLI publishes atomic JSON, Parquet, and Markdown evidence; tests prove grid identity, causal date isolation, formulas, costs, and fail-closed hashes.

**Tech Stack:** Python 3.12, pandas, NumPy, PyArrow, pytest, Ruff, SHA-256.

## Global Constraints

- Load only 2021-01-01 through 2023-12-31.
- Require news feature SHA-256 `d5b83060c7bb5e8cc4d97192e1df2518e3313b269b3591d5715f5fc88180b209` and event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9` in production.
- Complete exactly 400 frozen cells; allocate no strategy versions.
- Preserve explicit no-news zero rows and reject missing/duplicate event keys.
- Never load raw news text, development, consumed, or 2026-04+ data.
- Do not add Paper, broker, order, submit, cancel, or observation-pool behavior.

---

### Task 1: Pure frozen diagnostic

**Files:**
- Create: `src/us_intraday_lab/news_training_feasibility.py`
- Create: `tests/unit/test_news_training_feasibility.py`

**Interfaces:**
- `specifications() -> tuple[Specification, ...]` returns exactly 400 cells.
- `score_family(frame: pd.DataFrame, family: str) -> pd.Series` implements the five frozen formulas.
- `run_diagnostic(*, events_path: Path, features_path: Path, expected_event_sha256: str, expected_feature_sha256: str) -> tuple[pd.DataFrame, dict[str, object]]` returns all cells and a summary.

- [ ] **Step 1: Write failing tests for grid, formulas, isolation, and retention**

```python
def test_grid_is_exactly_four_hundred_unversioned_cells() -> None:
    specs = specifications()
    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)


def test_negative_news_reversal_formula() -> None:
    frame = frozen_score_fixture()
    score = score_family(frame, "negative_news_reversal")
    expected = percentile(frame, "negative_minus_positive") - percentile(frame, "session_return")
    pd.testing.assert_series_equal(score, expected)


def test_rejects_nontraining_rows_and_hash_mismatch(tmp_path: Path) -> None:
    events, features = write_diagnostic_fixture(tmp_path, session=date(2024, 1, 2))
    with pytest.raises(RuntimeError, match="NEWS_DIAGNOSTIC_INPUT_HASH_MISMATCH"):
        run_diagnostic(
            events_path=events,
            features_path=features,
            expected_event_sha256="0" * 64,
            expected_feature_sha256="0" * 64,
        )
```

- [ ] **Step 2: Run tests and confirm missing-module failure**

Run: `python -m pytest tests/unit/test_news_training_feasibility.py -q`

Expected: import failure for the new module.

- [ ] **Step 3: Implement the frozen grid, metrics, and scoring**

Use immutable dataclasses, stable groupwise percentile ranks, symbol tie breaks,
the exact entry/exit map in the design, and annualized log-return metrics over
the complete training session calendar. A selected day pays its declared cost;
an unselected training session is zero only inside this feasibility diagnostic.

- [ ] **Step 4: Implement validation and decision output**

Validate hashes before reading, merge one-to-one by `event_key`, verify exact
identity columns, reject any date outside training, compute all three scenarios,
and set `PROCEED_TO_SEPARATE_DEVELOPMENT_ACQUISITION_PLAN` only when retained
cells span at least two families. Otherwise set
`ABANDON_NEWS_CONTRACT_NO_VERSION_CREATED`.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/unit/test_news_training_feasibility.py -q`

Expected: all tests PASS.

```powershell
git add -- src/us_intraday_lab/news_training_feasibility.py tests/unit/test_news_training_feasibility.py
git commit -m "Add frozen news training feasibility diagnostic"
```

### Task 2: CLI, production run, and evidence

**Files:**
- Create: `scripts/diagnose_news_training_feasibility.py`
- Modify: `tests/unit/test_news_training_feasibility.py`
- Create after run: `research/results/2026-09-16-news-training-feasibility-summary.json`
- Create after run: `research/results/2026-09-16-news-training-feasibility-summary.md`

**Interfaces:**
- CLI accepts `--events`, `--features`, `--output-json`, `--output-parquet`, and `--output-md`.
- Production full cell table remains external under `E:\us-intraday-lab-data\us-market\research`; the tracked summary contains only aggregate evidence and hashes.

- [ ] **Step 1: Write a failing atomic-output test**

```python
def test_cli_writes_complete_training_only_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "run_diagnostic", lambda **kwargs: frozen_result())
    exit_code = script.run(arguments_for(tmp_path))
    payload = json.loads((tmp_path / "summary.json").read_text("utf-8"))
    assert exit_code == 0
    assert payload["cells_completed"] == 400
    assert payload["development_or_consumed_loaded"] is False
    assert payload["strategy_versions_created"] == 0
```

- [ ] **Step 2: Implement atomic CLI outputs**

Write temporary siblings, replace only after complete serialization, and reject
an existing path whose bytes differ. Markdown states the decision, retained
families, hashes, `Paper activation: false`, and `Order route: FORBIDDEN`.

- [ ] **Step 3: Run targeted tests and Ruff**

Run: `python -m pytest tests/unit/test_news_training_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/news_training_feasibility.py scripts/diagnose_news_training_feasibility.py tests/unit/test_news_training_feasibility.py`

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 4: Run the production diagnostic**

```powershell
python scripts/diagnose_news_training_feasibility.py `
  --events E:\us-intraday-lab-data\us-market\research\cache\v14309_v14408_events.parquet `
  --features E:\us-intraday-lab-data\us-market\research\cache\us_market_news_training_features_v1.parquet `
  --output-json research\results\2026-09-16-news-training-feasibility-summary.json `
  --output-parquet E:\us-intraday-lab-data\us-market\research\news-training-feasibility-v1.parquet `
  --output-md research\results\2026-09-16-news-training-feasibility-summary.md
```

Expected: `status=COMPLETE`, 400 cells, no nontraining data, and one of the two
frozen decisions.

- [ ] **Step 5: Verify, record local memory, commit, and push**

Run the targeted test, all data tests, and full suite. Preserve the known 16
unrelated research failures. Write the AGENTS.md-required local memory fallback
with mandatory legacy tags and the actual diagnostic decision, then commit only
source/tests/spec/plan/tracked summaries and push the current branch.
