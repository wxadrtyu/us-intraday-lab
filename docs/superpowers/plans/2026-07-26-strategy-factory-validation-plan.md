# Strategy Factory and Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert structured AI hypotheses into bounded deterministic strategy families, evaluate them without test-set leakage, apply hard promotion gates and null tests, and register only traceable survivors.

**Architecture:** The factory accepts a data-only `HypothesisProposal`, validates it against a feature catalog, expands a finite grid with deterministic sampling, and schedules immutable backtest jobs. A validation service computes chronological splits and walk-forward evidence, applies hard gates before ranking, runs null tests, and writes append-only registry transitions plus Chinese research reports.

**Tech Stack:** Python 3.12, Pydantic 2, pandas, NumPy, SciPy, PyArrow, DuckDB, SQLite, Jinja2, Typer, pytest, Ruff, mypy.

## Global Constraints

- Complete Plans 1 and 2 first.
- AI proposes hypotheses and bounded parameter ranges only; deterministic code owns variants, backtests, gates, ranking, and registry writes.
- No hypothesis can introduce a new indicator, operator, symbol, order type, sizing algorithm, file path, URL, or executable fragment.
- Every proposal records prompt/model/provider metadata when AI is used, but the system must also support a local fixture provider for deterministic tests.
- Variant generation has a configured family budget and seed. It never performs an unbounded Cartesian product.
- Chronological split is `70% train / 20% validation / 10% final test`.
- Parameter selection and family pruning can use only train and validation. Final test is evaluated once for survivors and cannot feed another search round.
- Hard gates precede ranking: positive base and `1.5x` cost returns, at least 100 closed trades, maximum drawdown at most 8%, profit factor at least 1.15, at least 60% profitable walk-forward windows, parameter stability, no ETF above 70% of total profit, start-date stability, and passed null test.
- Promotion requires evidence across `SPY`, `QQQ`, and `IWM`; robustness-only symbols may reject a family but may not replace the production trio.
- Registry transitions are append-only and retain rejected strategies with reasons.
- Strategy lifecycle in this plan ends at `candidate` or `paper_shadow`; later paper states belong to Plan 4.
- Generated reports are Chinese and must distinguish train, validation, untouched final test, and diagnostic results.

---

## File Structure

```text
src/us_intraday_lab/
  contracts/
    hypotheses.py
    validation.py
    registry.py
  factory/
    feature_catalog.py
    proposal.py
    variants.py
    experiments.py
    orchestrator.py
  validation/
    splits.py
    walk_forward.py
    stability.py
    null_tests.py
    gates.py
    ranking.py
  registry/
    migrations/001_initial.sql
    store.py
    lifecycle.py
  reporting/
    research.py
    templates/research_run_zh.md.j2
tests/
  fixtures/hypotheses/
    momentum_pullback.json
  unit/factory/
    test_proposal.py
    test_variants.py
    test_experiments.py
  unit/validation/
    test_splits.py
    test_walk_forward.py
    test_stability.py
    test_null_tests.py
    test_gates.py
    test_ranking.py
  unit/registry/
    test_lifecycle.py
  integration/factory/
    test_research_run.py
    test_final_test_isolation.py
```

`factory` creates immutable experiments. `validation` reads results and emits decisions but cannot mutate strategy definitions. `registry` is the only lifecycle writer. `reporting` renders already-computed evidence and contains no gate logic.

## Task 1: Define Hypothesis and Validation Contracts

**Files:**
- Modify: `pyproject.toml`
- Create: `src/us_intraday_lab/contracts/hypotheses.py`
- Create: `src/us_intraday_lab/contracts/validation.py`
- Create: `src/us_intraday_lab/contracts/registry.py`
- Create: `src/us_intraday_lab/factory/feature_catalog.py`
- Test: `tests/unit/factory/test_proposal.py`

- [ ] **Step 1: Write failing proposal tests**

```python
import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.hypotheses import HypothesisProposal


def test_proposal_contains_bounded_data_only_search_space() -> None:
    proposal = HypothesisProposal.model_validate(
        {
            "hypothesis_id": "intraday-momentum-pullback",
            "thesis": "Trend continuation after a shallow pullback",
            "entry_template": "momentum_pullback",
            "exit_template": "risk_managed",
            "indicators": ["ema_spread", "rsi", "volume_ratio"],
            "parameter_ranges": {
                "rsi_entry": {"values": [35.0, 40.0, 45.0]},
                "stop_loss_bps": {"values": [25, 35, 45]},
            },
            "symbols": ["SPY", "QQQ", "IWM"],
            "max_variants": 60,
            "seed": 20260726,
            "rationale": "Price and volume confirmation may reduce false entries.",
        }
    )
    assert proposal.max_variants == 60


def test_proposal_rejects_executable_fields() -> None:
    with pytest.raises(ValidationError):
        HypothesisProposal.model_validate({"python": "print('run me')"})
```

- [ ] **Step 2: Implement closed proposal models**

Add `jinja2>=3.1,<4` and `scipy>=1.15,<2` as direct runtime dependencies in `pyproject.toml`, then reinstall with `python -m pip install -e ".[dev]"`. Allow only catalog template IDs, indicator IDs, numeric/enum parameter values, the three production symbols, `max_variants` from 1 through 200, and an explicit integer seed. Text fields are annotations and never interpreted.

- [ ] **Step 3: Define validation evidence and decisions**

Create frozen contracts for:

- `ChronologicalSplit`;
- `WalkForwardWindowResult`;
- `GateEvidence`;
- `GateResult` with stable reason code, threshold, observed value, and pass/fail;
- `ValidationDecision` with `REJECT` or `PROMOTE_TO_PAPER_SHADOW`;
- `RegistryEvent` with from/to state, actor, reason, immutable references, and timestamp.

- [ ] **Step 4: Implement an immutable feature/template catalog**

The catalog maps approved template parameters to the Plan 2 DSL. Every parameter declares type, allowed values or numeric bounds, and whether it affects entry, exit, risk, or sizing. Unknown proposal fields fail closed.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/factory/test_proposal.py -q
git add src/us_intraday_lab/contracts src/us_intraday_lab/factory/feature_catalog.py tests/unit/factory
git commit -m "feat(factory): define bounded hypothesis contracts"
```

## Task 2: Generate Deterministic, Budgeted Strategy Variants

**Files:**
- Create: `src/us_intraday_lab/factory/__init__.py`
- Create: `src/us_intraday_lab/factory/proposal.py`
- Create: `src/us_intraday_lab/factory/variants.py`
- Create: `src/us_intraday_lab/factory/experiments.py`
- Create: `tests/fixtures/hypotheses/momentum_pullback.json`
- Test: `tests/unit/factory/test_variants.py`
- Test: `tests/unit/factory/test_experiments.py`

- [ ] **Step 1: Write deterministic variant tests**

Given the same proposal and catalog:

- variant IDs and canonical JSON are identical across runs;
- no more than `max_variants` are produced;
- duplicates collapse by content hash;
- every variant passes the Plan 2 static validator;
- changing only descriptive rationale does not change variant IDs;
- changing seed changes the selected subset only when the full grid exceeds the budget.

- [ ] **Step 2: Implement bounded expansion**

Construct the sorted Cartesian candidate space, then use a seeded space-filling selection when it exceeds the budget. Always include a declared baseline and boundary values. Strategy ID is `sha256(canonical_definition_json)[:16]`.

- [ ] **Step 3: Write experiment-lineage tests**

Assert every `ExperimentManifest` includes:

```text
experiment_id
hypothesis_id
proposal_hash
catalog_version
variant_generator_version
dataset_id
backtest_engine_version
calendar_version
cost_model_versions
split_definition
code_revision
created_at
```

- [ ] **Step 4: Implement proposal providers**

Define a provider protocol that returns `HypothesisProposal`. Implement `FixtureProposalProvider` now. Keep any future LLM client behind this interface and require its output to pass Pydantic and catalog validation before storage. Do not add a vendor SDK until a later explicit integration task supplies credentials and a chosen provider.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/factory/test_variants.py tests/unit/factory/test_experiments.py -q
git add src/us_intraday_lab/factory tests/fixtures/hypotheses tests/unit/factory
git commit -m "feat(factory): generate deterministic strategy families"
```

## Task 3: Lock Chronological Splits and Walk-Forward Evaluation

**Files:**
- Create: `src/us_intraday_lab/validation/__init__.py`
- Create: `src/us_intraday_lab/validation/splits.py`
- Create: `src/us_intraday_lab/validation/walk_forward.py`
- Test: `tests/unit/validation/test_splits.py`
- Test: `tests/unit/validation/test_walk_forward.py`
- Test: `tests/integration/factory/test_final_test_isolation.py`

- [ ] **Step 1: Write failing chronological split tests**

Use unique ordered sessions and assert:

```python
assert train_sessions < validation_sessions < final_test_sessions
assert len(train) / total == pytest.approx(0.70, abs=0.02)
assert len(validation) / total == pytest.approx(0.20, abs=0.02)
assert len(final_test) / total == pytest.approx(0.10, abs=0.02)
assert not set(train) & set(validation)
assert not set(train) & set(final_test)
assert not set(validation) & set(final_test)
```

Boundary rounding must be deterministic and recorded in the experiment manifest.

- [ ] **Step 2: Implement immutable split access**

Create separate read APIs:

- `training_view()` for fitting/variant pruning;
- `validation_view()` for family selection;
- `final_test_view()` available only to the final evaluator after selection is sealed.

Do not pass one unlabelled DataFrame through all phases.

- [ ] **Step 3: Write the leakage test**

Instrument the data views. Run selection and assert no final-test read occurs. Then run final evaluation and assert it is read exactly once. Attempting a second search round after final access must raise `FINAL_TEST_ALREADY_CONSUMED`.

- [ ] **Step 4: Implement rolling walk-forward windows**

Windows are chronological and session-aligned. Record train/evaluation boundaries and net base return per window. No window may share evaluation sessions with its training span.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/validation/test_splits.py tests/unit/validation/test_walk_forward.py tests/integration/factory/test_final_test_isolation.py -q
git add src/us_intraday_lab/validation tests/unit/validation tests/integration/factory/test_final_test_isolation.py
git commit -m "feat(validation): enforce chronological test isolation"
```

## Task 4: Implement Stability, Concentration, Start-Date, and Null Tests

**Files:**
- Create: `src/us_intraday_lab/validation/stability.py`
- Create: `src/us_intraday_lab/validation/null_tests.py`
- Test: `tests/unit/validation/test_stability.py`
- Test: `tests/unit/validation/test_null_tests.py`

- [ ] **Step 1: Write parameter-neighborhood stability tests**

For each candidate, evaluate its declared adjacent parameter values. A plateau passes when the configured majority of neighbors remains profitable under base costs and none breaches the drawdown gate. A single isolated optimum fails with `UNSTABLE_PARAMETER_NEIGHBORHOOD`.

- [ ] **Step 2: Write symbol-concentration tests**

Compute profit contribution by `SPY`, `QQQ`, and `IWM`. Fail when total profit is nonpositive or one symbol contributes more than 70% of positive profit. Preserve negative contributions in the report.

- [ ] **Step 3: Write start-date sensitivity tests**

Re-evaluate from multiple session offsets fixed in configuration. Pass only when the majority remains profitable and no offset causes drawdown above 8%. Record every offset, not just the aggregate.

- [ ] **Step 4: Write deterministic null tests**

Use at least two nulls:

1. permute entry signals within the same symbol/session while preserving trade count and holding rules;
2. shift signal timestamps by seeded nonzero session-safe offsets.

Compare the observed candidate to the null distribution with a fixed seed and configured repetitions. The fixture test uses a small repetition count; production config uses the approved larger count. Fail when the candidate is not better than the configured null percentile.

- [ ] **Step 5: Implement and commit**

```powershell
python -m pytest tests/unit/validation/test_stability.py tests/unit/validation/test_null_tests.py -q
git add src/us_intraday_lab/validation tests/unit/validation
git commit -m "feat(validation): add robustness and null tests"
```

## Task 5: Apply Hard Gates Before Ranking

**Files:**
- Create: `src/us_intraday_lab/validation/gates.py`
- Create: `src/us_intraday_lab/validation/ranking.py`
- Test: `tests/unit/validation/test_gates.py`
- Test: `tests/unit/validation/test_ranking.py`

- [ ] **Step 1: Encode every approved hard gate in tests**

Create one passing evidence fixture and mutate one field at a time. Stable failure codes:

```text
NONPOSITIVE_BASE_RETURN
NONPOSITIVE_COST_1_5X_RETURN
INSUFFICIENT_TRADES
MAX_DRAWDOWN_EXCEEDED
PROFIT_FACTOR_TOO_LOW
INSUFFICIENT_PROFITABLE_WF_WINDOWS
UNSTABLE_PARAMETER_NEIGHBORHOOD
SYMBOL_PROFIT_CONCENTRATION
START_DATE_INSTABILITY
NULL_TEST_FAILED
```

Thresholds:

```text
base net return > 0
1.5x cost net return > 0
closed trades >= 100
maximum drawdown <= 0.08
profit factor >= 1.15
profitable walk-forward windows / all windows >= 0.60
largest symbol positive-profit share <= 0.70
```

- [ ] **Step 2: Implement fail-complete gate evaluation**

Evaluate all gates and return all reasons in fixed order. Never rank failed candidates. Treat undefined profit factor, missing scenario output, missing symbol evidence, or missing null evidence as a failure.

- [ ] **Step 3: Define ranking only among gate survivors**

Use a transparent composite of final-test and validation quality that rewards net return consistency, lower drawdown, profit factor, walk-forward consistency, and lower cost sensitivity. Store every normalized component. Do not use one opaque AI score.

- [ ] **Step 4: Add monotonic ranking tests**

Holding other fields equal, improved return/consistency/profit factor cannot lower score; increased drawdown/cost sensitivity cannot raise score. Ties resolve by strategy content hash.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/validation/test_gates.py tests/unit/validation/test_ranking.py -q
git add src/us_intraday_lab/validation tests/unit/validation
git commit -m "feat(validation): gate candidates before transparent ranking"
```

## Task 6: Add Append-Only Registry and Lifecycle Enforcement

**Files:**
- Create: `src/us_intraday_lab/registry/__init__.py`
- Create: `src/us_intraday_lab/registry/migrations/001_initial.sql`
- Create: `src/us_intraday_lab/registry/store.py`
- Create: `src/us_intraday_lab/registry/lifecycle.py`
- Test: `tests/unit/registry/test_lifecycle.py`

- [ ] **Step 1: Write lifecycle tests**

Allowed transitions in this plan:

```text
generated -> candidate
candidate -> rejected
candidate -> paper_shadow
paper_shadow -> rejected
```

Reject skipping validation, rewriting old events, reusing an idempotency key with different content, or promoting without a passing `ValidationDecision`.

- [ ] **Step 2: Create SQLite WAL schema**

Tables:

- `strategy_definitions` keyed by immutable content hash;
- `validation_decisions`;
- `registry_events` append-only with unique idempotency key;
- `strategy_current_state` maintained transactionally from events.

Enable foreign keys, WAL, busy timeout, and explicit transactions. Databases remain ignored.

- [ ] **Step 3: Implement append-only operations**

No update/delete API for definitions, decisions, or events. State changes append an event and update only the derived current-state row in the same transaction.

- [ ] **Step 4: Run and commit**

```powershell
python -m pytest tests/unit/registry/test_lifecycle.py -q
git add src/us_intraday_lab/registry tests/unit/registry
git commit -m "feat(registry): persist auditable strategy lifecycle"
```

## Task 7: Orchestrate a Research Run and Render the Chinese Report

**Files:**
- Create: `src/us_intraday_lab/factory/orchestrator.py`
- Create: `src/us_intraday_lab/reporting/research.py`
- Create: `src/us_intraday_lab/reporting/templates/research_run_zh.md.j2`
- Extend: `src/us_intraday_lab/cli.py`
- Test: `tests/integration/factory/test_research_run.py`

- [ ] **Step 1: Write a failing end-to-end fixture run**

Using a fixture proposal and synthetic accepted dataset, assert:

- bounded variants are created;
- every variant gets train and validation jobs;
- only selected survivors read final test;
- all three cost scenarios and `1.5x` evidence exist;
- every candidate receives all gate results;
- failed candidates remain queryable;
- survivors transition to `paper_shadow`;
- repeated execution with the same experiment ID is idempotent.

- [ ] **Step 2: Implement resumable orchestration**

Persist stages:

```text
PROPOSAL_ACCEPTED
VARIANTS_GENERATED
TRAIN_COMPLETE
VALIDATION_COMPLETE
SELECTION_SEALED
FINAL_TEST_COMPLETE
GATES_COMPLETE
REGISTRY_COMPLETE
REPORT_COMPLETE
```

On restart, verify immutable hashes and continue from the first incomplete stage. A hash mismatch fails closed.

- [ ] **Step 3: Render a Chinese research report**

Include hypothesis, generated/valid/tested/rejected counts, split dates, cost assumptions, hard-gate table, survivor ranking components, rejection reasons, null results, symbol contribution, start-date sensitivity, immutable IDs, and a clear statement that historical performance does not imply future profit.

- [ ] **Step 4: Add CLI**

```text
intraday-lab research run \
  --proposal tests/fixtures/hypotheses/momentum_pullback.json \
  --dataset-id <accepted-id> \
  --root G:\us-intraday-lab

intraday-lab research resume --experiment-id <id> --root G:\us-intraday-lab
intraday-lab research report --experiment-id <id> --root G:\us-intraday-lab
```

- [ ] **Step 5: Run Plan 3 acceptance**

```powershell
python -m pytest tests/unit/factory tests/unit/validation tests/unit/registry tests/integration/factory -q
ruff check .
ruff format --check .
python -m mypy src
intraday-lab research run --proposal tests/fixtures/hypotheses/momentum_pullback.json --dataset-id <accepted-id> --root G:\us-intraday-lab
```

Expected: all checks pass and the report links every decision to immutable experiment, strategy, dataset, engine, calendar, and cost-model identifiers.

- [ ] **Step 6: Commit**

```powershell
git add src/us_intraday_lab/factory src/us_intraday_lab/reporting src/us_intraday_lab/cli.py tests/integration/factory
git commit -m "feat(factory): orchestrate gated strategy research"
```

## Plan 3 Completion Criteria

- [ ] Fixture proposal generation is deterministic, bounded, and fully data-only.
- [ ] The final test cannot influence variant generation or selection.
- [ ] All approved hard gates run before ranking and emit stable reasons.
- [ ] Null, neighborhood, symbol-concentration, walk-forward, and start-date evidence is retained.
- [ ] Failed candidates are preserved; promoted candidates enter only `paper_shadow`.
- [ ] A killed research run resumes idempotently without recomputing completed immutable stages.
- [ ] The Chinese report matches stored evidence and contains no independently recomputed metrics.
- [ ] All tests, Ruff, formatting, and mypy pass.
