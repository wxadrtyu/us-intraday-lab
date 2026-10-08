# SEC original Form S-8 training implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the frozen 400-cell training-only diagnostic for exact original SEC Form S-8 events without opening development or consumed data or creating a strategy version.

**Architecture:** A focused library module validates immutable inputs, converts the frozen coverage rows into causal three-session issuer states, assigns repetition labels without left-censor leakage, evaluates the five frozen cross-sectional families, and applies the retention rule. A thin CLI writes atomic external cell results plus tracked aggregate JSON/Markdown evidence. Tests exercise state construction, ranking, missingness, costs, metrics, hashes, and terminal decisions before the implementation is allowed to read production outcomes.

**Tech Stack:** Python 3.12, pandas, NumPy, PyArrow, pytest, Ruff, SHA-256, JSON.

## Global constraints

- Event cube SHA-256: `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- Coverage artifact SHA-256: `62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`.
- SEC identity SHA-256: `44e7e15596937fe353d2148e6e775c41b83e27f9196d980bbeb44bd873d5f5b1` remains provenance evidence; the diagnostic consumes the already-frozen symbol/CIK mapping from the coverage artifact and performs no new entity resolution.
- Use only 2021-01-01 through 2023-12-31 and reject any event-cube row outside that boundary.
- Use only the 482 frozen admissible coverage rows; preserve 138 missing-next-session rows as audit counts and never impute them.
- Event life is exactly three observed symbol sessions beginning at `next_sample_session`.
- Evaluate exactly five families x decision bars `(2,5,11,17,23)` x holding bars `(1,2,4,6)` x top counts `(1,3,5,10)` = 400 cells.
- Use 9 bp standard cost, 18 bp stress cost, and one-bar delayed entry at 9 bp.
- Retain only with at least 120 signal sessions, annualized return at least 20%, IR at least 0.8, maximum drawdown below 20%, at least two positive calendar years, positive 18 bp annualized return, and positive delayed annualized return.
- Proceed only when retained cells span at least two families.
- Do not load primary-document bodies, development data, consumed data, broker state, Paper state, monitoring pools, order routes, or shutdown controls.
- Raw inputs, full cell tables, caches, and runtime state remain untracked. Only code, tests, aggregate summaries, design/plan documents, and tagged local fallback memory are committed.

---

### Task 1: Causal event-state builder

**Files:**
- Create: `src/us_intraday_lab/sec_s8_training_feasibility.py`
- Create: `tests/unit/test_sec_s8_training_feasibility.py`

**Interfaces:**
- `Specification(family: str, decision_bar: int, holding_bars: int, top_count: int)` is an immutable dataclass.
- `specifications() -> tuple[Specification, ...]` returns exactly 400 unique cells.
- `load_coverage(path: Path, expected_sha256: str) -> tuple[pd.DataFrame, dict[str, object]]` validates the artifact before returning the 482 admitted rows and audit metadata.
- `build_event_states(events: pd.DataFrame, symbol_sessions: pd.DataFrame) -> pd.DataFrame` returns one row per active `(symbol, session_date)` with active accessions and the three frozen repetition predicates.

- [ ] **Step 1: Write failing tests for the exact grid and immutable coverage contract**

```python
def test_specifications_are_exactly_the_frozen_four_hundred_cells() -> None:
    specs = specifications()
    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)
    assert {item.decision_bar for item in specs} == {2, 5, 11, 17, 23}
    assert {item.holding_bars for item in specs} == {1, 2, 4, 6}
    assert {item.top_count for item in specs} == {1, 3, 5, 10}


def test_load_coverage_rejects_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(coverage_fixture()), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SEC_S8_COVERAGE_HASH_MISMATCH"):
        load_coverage(path, "0" * 64)
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Expected: collection fails because `us_intraday_lab.sec_s8_training_feasibility` does not exist.

- [ ] **Step 3: Implement constants, the dataclass, hash validation, and coverage parsing**

Create the module with these frozen constants and validation rules:

```python
FAMILIES = (
    "all_event_continuation",
    "all_event_reversal",
    "first_or_renewal_252_continuation",
    "repeat_252_continuation",
    "clustered_repeat_63_reversal",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
TOP_COUNTS = (1, 3, 5, 10)
TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
STANDARD_EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
DELAY_EXITS = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}
```

`load_coverage` must verify bytes before JSON parsing, require
`status == "ACCEPTANCE_COVERAGE_COMPLETE"`, `coverage.passed is True`, exactly
482 rows with `admissible is True`, unique `(symbol, accession)` pairs, nonempty
accepted timestamps and next sessions, and exact form `S-8`. It returns only
columns needed for state construction plus the frozen aggregate audit counts.

- [ ] **Step 4: Write failing state tests before state implementation**

```python
def test_event_is_active_for_exactly_three_symbol_sessions() -> None:
    sessions = symbol_sessions("AAA", periods=6)
    events = event_rows(("AAA", "a1", sessions.iloc[1].session_date))
    states = build_event_states(events, sessions)
    assert states.session_date.tolist() == sessions.session_date.iloc[1:4].tolist()


def test_first_label_requires_complete_252_session_lookback() -> None:
    sessions = symbol_sessions("AAA", periods=260)
    events = event_rows(
        ("AAA", "left-censored", sessions.iloc[100].session_date),
        ("AAA", "complete", sessions.iloc[255].session_date),
    )
    states = build_event_states(events, sessions)
    labels = states.groupby("accession").first()
    assert not bool(labels.loc["left-censored", "first_or_renewal_252"])
    assert bool(labels.loc["complete", "first_or_renewal_252"])


def test_same_availability_accessions_do_not_make_each_other_repeats() -> None:
    sessions = symbol_sessions("AAA", periods=300)
    date_ = sessions.iloc[260].session_date
    states = build_event_states(event_rows(("AAA", "a1", date_), ("AAA", "a2", date_)), sessions)
    assert not states["repeat_252"].any()
    assert not states["clustered_repeat_63"].any()
```

- [ ] **Step 5: Verify the new tests fail for missing state behavior**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Expected: grid/hash tests pass and state tests fail because `build_event_states` is absent or incomplete.

- [ ] **Step 6: Implement minimal causal state construction**

Create a stable symbol-session ordinal table from unique `(symbol, session_date)`
rows. Map each event's frozen next session to its ordinal. Repetition uses only
strictly smaller distinct availability ordinals for the same symbol. Set
`first_or_renewal_252` only when ordinal is at least 252 and no prior availability
ordinal is in `[ordinal-252, ordinal-1]`; set `repeat_252` and
`clustered_repeat_63` from positive prior evidence in their exact windows.
Expand each event over ordinals `0,1,2`, stop at the symbol boundary, then
aggregate to one symbol-session row with sorted active accession tuples and
predicate-wise `any`. Retain an event-level helper table in the return value's
documented columns so tests can inspect labels without reading outcomes.

- [ ] **Step 7: Run targeted tests and commit Task 1**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Expected: all Task 1 tests pass.

```powershell
git add -- src/us_intraday_lab/sec_s8_training_feasibility.py tests/unit/test_sec_s8_training_feasibility.py
git commit -m "Add SEC S-8 causal event states"
```

### Task 2: Frozen training evaluator

**Files:**
- Modify: `src/us_intraday_lab/sec_s8_training_feasibility.py`
- Modify: `tests/unit/test_sec_s8_training_feasibility.py`

**Interfaces:**
- `score_family(frame: pd.DataFrame, family: str) -> pd.Series` returns a numeric score only for eligible active rows.
- `run_diagnostic(*, event_cube_path: Path, coverage_path: Path, expected_event_sha256: str, expected_coverage_sha256: str) -> tuple[pd.DataFrame, dict[str, object]]` returns all 400 cells and a versionless aggregate summary.

- [ ] **Step 1: Write failing tests for score direction, deterministic ranking, and fail-closed prices**

```python
def test_continuation_and_reversal_order_the_same_active_names_oppositely() -> None:
    frame = score_fixture(returns={"AAA": -0.02, "BBB": 0.01, "CCC": 0.03})
    continuation = score_family(frame, "all_event_continuation")
    reversal = score_family(frame, "all_event_reversal")
    assert continuation.idxmax() == frame.index[frame.symbol.eq("CCC")][0]
    assert reversal.idxmax() == frame.index[frame.symbol.eq("AAA")][0]


def test_selected_missing_price_fails_cell_closed(tmp_path: Path) -> None:
    cube, coverage, cube_hash, coverage_hash = write_training_fixture(tmp_path, missing_selected_exit=True)
    cells, summary = run_diagnostic(
        event_cube_path=cube,
        coverage_path=coverage,
        expected_event_sha256=cube_hash,
        expected_coverage_sha256=coverage_hash,
    )
    assert cells["valid"].eq(False).any()
    assert summary["invalid_cells"] > 0
    assert not cells.loc[cells.valid.eq(False), "retention_floor_passed"].any()
```

- [ ] **Step 2: Run tests and verify expected behavior failures**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Expected: the new tests fail because scoring and `run_diagnostic` are missing.

- [ ] **Step 3: Implement score eligibility and ranking**

Use within `(session_date, bar_idx)` percentile ranks of `session_return`.
Continuation returns the percentile; reversal returns `1.0 - percentile`.
Family predicates come only from the active-state columns. Drop nonfinite scores
before ranking and sort by `session_date`, descending score, then ascending
symbol. Rank a symbol once even if multiple accessions are active.

- [ ] **Step 4: Write failing tests for costs, delay, full-calendar metrics, and retention**

```python
def test_standard_stress_and_delay_use_frozen_entries_exits_and_costs(tmp_path: Path) -> None:
    cube, coverage, cube_hash, coverage_hash = write_training_fixture(tmp_path)
    cells, _ = run_diagnostic(
        event_cube_path=cube,
        coverage_path=coverage,
        expected_event_sha256=cube_hash,
        expected_coverage_sha256=coverage_hash,
    )
    cell = cells.query(
        "family == 'all_event_continuation' and decision_bar == 2 and holding_bars == 1 and top_count == 1"
    ).iloc[0]
    assert cell.standard_cost_bp == 9
    assert cell.stress_cost_bp == 18
    assert cell.delay_bars == 1


def test_summary_never_creates_version_or_authorizes_execution(tmp_path: Path) -> None:
    cells, summary = run_small_valid_fixture(tmp_path)
    assert len(cells) == 400
    assert summary["cells_completed"] == 400
    assert summary["strategy_versions_created"] == 0
    assert summary["development_or_consumed_loaded"] is False
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"
```

- [ ] **Step 5: Implement evaluation, metrics, and terminal decision**

Read exactly these cube columns after validating the file hash:
`symbol`, `session_date`, `bar_idx`, `session_return`, `p1_open`, `p2_open`,
`p3_open`, `p5_open`, `p7_open`, `p8_open`. Reject duplicate
`(symbol,session_date,bar_idx)` keys and any row outside training. Construct the
full unique sample-session calendar. For each specification, select up to K
names, equal-weight valid names, and fail the cell if any selected entry or exit
is missing/nonpositive. Standard enters `p1_open`, stress uses the same path,
and delay enters `p2_open`; exits use `STANDARD_EXITS` and `DELAY_EXITS`.
Subtract cost once per active portfolio session. Valid zero-signal sessions are
zero. Compute annualized geometric return, IR, drawdown, and calendar-year
returns on the full calendar. Apply every frozen retention predicate exactly.
Set decision to `ACQUIRE_DEVELOPMENT_SEC_S8_DATA` only when retained cells span
two families; otherwise use `ABANDON_SEC_S8_NO_VERSION_CREATED`.

- [ ] **Step 6: Run targeted tests and commit Task 2**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/sec_s8_training_feasibility.py tests/unit/test_sec_s8_training_feasibility.py`

Expected: tests pass and Ruff reports `All checks passed!`.

```powershell
git add -- src/us_intraday_lab/sec_s8_training_feasibility.py tests/unit/test_sec_s8_training_feasibility.py
git commit -m "Add frozen SEC S-8 training diagnostic"
```

### Task 3: Atomic CLI, production training run, and evidence

**Files:**
- Create: `scripts/diagnose_sec_s8_training_feasibility.py`
- Modify: `tests/unit/test_sec_s8_training_feasibility.py`
- Create after the production run: `research/results/2026-10-08-sec-s8-training-feasibility-summary.json`
- Create after the production run: `research/results/2026-10-08-sec-s8-training-feasibility-summary.md`
- Create after the production run: `memory/2026-10-08-sec-s8-training-feasibility-local.md`
- External untracked output: `E:\us-intraday-lab-data\us-market\research\sec-s8-training-feasibility-v1.parquet`

**Interfaces:**
- CLI arguments: `--event-cube`, `--coverage`, `--output-json`, `--output-parquet`, and `--output-md`.
- `render_markdown(summary: dict[str, object]) -> str` renders only aggregate evidence, immutable hashes, missingness, and the frozen decision.
- `run(argv: Sequence[str] | None = None) -> int` returns zero only after all three outputs are atomically complete.

- [ ] **Step 1: Write the failing CLI atomic-output test**

```python
def test_cli_writes_complete_versionless_outputs_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "run_diagnostic", lambda **_: frozen_result())
    assert script.run(cli_args(tmp_path)) == 0
    summary = json.loads((tmp_path / "summary.json").read_text("utf-8"))
    assert summary["status"] == "COMPLETE"
    assert summary["cells_completed"] == 400
    assert summary["strategy_versions_created"] == 0
    assert summary["paper_activation"] is False
    assert summary["order_route"] == "FORBIDDEN"
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run the CLI test and verify it fails because the script is absent**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Expected: import or assertion failure for the missing CLI.

- [ ] **Step 3: Implement the atomic CLI and aggregate Markdown renderer**

Use temporary sibling files and `Path.replace` only after successful JSON,
Parquet, and Markdown serialization. The tracked summary must contain status,
decision, hashes, input/audit counts, 400 completed cells, retained cell/family
counts, best training-only cell aggregates if and only if the diagnostic is
valid, `strategy_versions_created=0`, `development_or_consumed_loaded=false`,
`paper_activation=false`, and `order_route=FORBIDDEN`. It must not contain raw
prices, issuer-level rows, or the full ranked cell table.

- [ ] **Step 4: Run targeted tests and static checks**

Run: `python -m pytest tests/unit/test_sec_s8_training_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/sec_s8_training_feasibility.py scripts/diagnose_sec_s8_training_feasibility.py tests/unit/test_sec_s8_training_feasibility.py`

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Run the production training diagnostic sequentially**

```powershell
python scripts/diagnose_sec_s8_training_feasibility.py `
  --event-cube E:\us-intraday-lab-data\us-market\research\cache\v14309_v14408_events.parquet `
  --coverage state\sec_s8_source_audit\acceptance-coverage.json `
  --output-json research\results\2026-10-08-sec-s8-training-feasibility-summary.json `
  --output-parquet E:\us-intraday-lab-data\us-market\research\sec-s8-training-feasibility-v1.parquet `
  --output-md research\results\2026-10-08-sec-s8-training-feasibility-summary.md
```

Expected: `status=COMPLETE`, exactly 400 cells, no invalid cells, no nontraining
data, and one frozen terminal decision. If any immutable hash, schema, selected
price, or output invariant fails, stop this family, preserve the error evidence,
and do not repair it by changing the design.

- [ ] **Step 6: Verify the production artifact and repository boundary**

Run targeted tests, Ruff, `git diff --check`, and a JSON assertion that status is
`COMPLETE`, `cells_completed == 400`, every input hash matches, and all execution
flags remain false/forbidden. Confirm `state/` and the external Parquet remain
untracked.

- [ ] **Step 7: Write tagged fallback memory, commit, and push**

Write the actual decision using the required fields `summary`, `stage`,
`kpi_version`, `tags`, and `next_step`, with tags
`project:quant-agent-team`, `market:cn_a`, `freq:daily`,
`stage:training-result`, `strategy:sec-original-s8`, and the terminal status.
Commit only source, tests, CLI, aggregate result files, and fallback memory.
Push the current branch. If training passes, proceed autonomously only to a
separate development-data acquisition design; do not load development data in
this task. If it fails, freeze the family and preregister a genuinely distinct
source without tuning this design.
