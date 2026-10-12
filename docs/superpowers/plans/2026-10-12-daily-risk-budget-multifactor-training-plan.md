# Daily Risk-Budget Multi-Factor Training Implementation Plan

> **For agentic workers:** Execute inline in the current isolated worktree. Do not dispatch subagents. Follow test-driven development for every behavior change.

**Goal:** Evaluate one preregistered 400-cell, daily technical-only risk-budgeted multi-factor family on the frozen 2021-2023 training sample.

**Architecture:** Add an isolated feature/risk/portfolio engine that reuses only frozen daily-source loading and metric primitives. Add a separate immutable CLI so prior rejected diagnostics and artifacts cannot be overwritten.

**Tech Stack:** Python, pandas, NumPy, pytest, Ruff, Parquet.

## Global Constraints

- Use only the two frozen input hashes named in the design.
- Read only 2021-2023 training outcomes; earlier rows are lookback inputs only.
- Keep future missing opens fail-closed.
- Evaluate exactly 400 preregistered cells at 9/18 bp and one-session delay.
- Create no strategy version and touch no Paper, monitoring, broker, or order state.

---

### Task 1: Freeze feature, eligibility, and risk-budget behavior

**Files:**
- Create: `tests/unit/test_daily_risk_budget_multifactor.py`
- Create: `src/us_intraday_lab/daily_risk_budget_multifactor.py`

**Interfaces:**
- `specifications() -> tuple[Specification, ...]`
- `build_risk_budget_features(daily_bars: pd.DataFrame) -> pd.DataFrame`
- `score_family(frame: pd.DataFrame, family: str) -> pd.Series`
- `market_exposure(daily_bars: pd.DataFrame) -> pd.Series`

- [ ] Write tests asserting five fixed families and exactly 400 unique cells.
- [ ] Run the focused test and confirm failure because the module is absent.
- [ ] Add the minimal specification and feature code.
- [ ] Add tests proving USD 5 / USD 5 million causal eligibility, shifted market
      volatility exposure, family scoring, inverse-volatility weights, and 10%
      cap with residual cash.
- [ ] Run each new test red, implement minimally, then run it green.

### Task 2: Freeze portfolio accounting and gates

**Files:**
- Modify: `tests/unit/test_daily_risk_budget_multifactor.py`
- Modify: `src/us_intraday_lab/daily_risk_budget_multifactor.py`

**Interfaces:**
- `portfolio_returns(...) -> tuple[pd.Series, int, bool]`
- `evaluate_grid(...) -> pd.DataFrame`
- `training_decision(cells: pd.DataFrame) -> str`

- [ ] Add a failing test for lagged selection, overlapping cohorts, risk
      exposure, turnover cost, and open-to-next-open return.
- [ ] Add a failing test that a selected missing next open invalidates a cell.
- [ ] Implement minimal causal portfolio accounting and cached cohort sequences.
- [ ] Add and pass tests for exact gates, zero-invalid requirement, and two-family
      decision rule.

### Task 3: Add immutable CLI and safety contract

**Files:**
- Create: `scripts/diagnose_daily_risk_budget_multifactor.py`
- Modify: `tests/unit/test_daily_risk_budget_multifactor.py`

**Interfaces:**
- CLI writes immutable JSON, Markdown, and external Parquet artifacts.

- [ ] Add a failing direct-start/help and rendered-safety-contract test.
- [ ] Implement the CLI with frozen hashes, atomic immutable output, and no
      execution-state interfaces.
- [ ] Run focused tests, all related daily tests, and Ruff.
- [ ] Inspect `git diff --check` and commit/push code before running outcomes.

### Task 4: Run once and freeze the training conclusion

**Files:**
- Create: `research/results/2026-10-12-daily-risk-budget-multifactor-summary.json`
- Create: `research/results/2026-10-12-daily-risk-budget-multifactor-summary.md`
- Create: `memory/2026-10-12-daily-risk-budget-multifactor-result-local.md`
- External: `E:/us-intraday-lab-data/us-market/research/daily-risk-budget-multifactor-v1.parquet`

- [ ] Run the CLI once on frozen inputs and wait for `status=COMPLETE` and 400
      completed cells.
- [ ] Independently inspect invalid count, retained families, best valid cells,
      and artifact SHA-256.
- [ ] Write tagged local fallback memory with `project:quant-agent-team`,
      `market:cn_a`, `freq:daily`, stage, KPI version, decision, and next step.
- [ ] Run fresh tests, Ruff, and diff checks; commit and push the immutable
      conclusion. Recommend new development data only if every frozen gate passes.
