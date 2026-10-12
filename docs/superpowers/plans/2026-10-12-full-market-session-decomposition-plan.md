# Full-market session decomposition implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the frozen 400-cell full-market daily session-decomposition campaign without relaxing any evidence, missingness, or execution gate.

**Architecture:** A focused pure module owns the immutable grid, causal overnight/intraday features, deterministic ranks, exposure-leg accounting, metrics, and hash-chained checkpoints. A thin CLI verifies exact external identities, constructs the full-market panel, evaluates cells sequentially, and publishes tracked aggregates only after complete execution.

**Tech Stack:** Python 3.12, pandas, NumPy, DuckDB, PyArrow/Parquet, pytest, Ruff, SHA-256 JSON identities.

## Global Constraints

- Read only frozen daily source SHA-256 `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701` and universe SHA-256 `3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.
- Use only price, volume, VWAP, trade-count, volatility, and derived breadth/technical fields; issuer-event data is forbidden.
- Treat 2021-2026 as consumed; never claim independent OOS evidence.
- Missing selected exposure bars and selected triple-zero liquidity rows invalidate the cell; never convert them to cash or zero return.
- Preserve annualized return >40%, MDD <20%, IR >=1, z >=3, 4/5 positive folds, 9/18bp, delay, start-date, 70% neighborhood, Bonferroni <=0.05, and both 500-repetition native maxT gates.
- Keep Paper activation false and order routing forbidden.

---

### Task 1: Freeze the contract and grid

**Files:**
- Create: `src/us_intraday_lab/full_market_session_decomposition.py`
- Create: `tests/unit/test_full_market_session_decomposition.py`

**Interfaces:**
- Produces: `Specification`, `specifications()`, `FAMILIES`, `LOOKBACKS`, `REFRESH_LIFE_PAIRS`, and `TOP_COUNTS`.

- [ ] Write a failing test asserting five named families, lookbacks `(20, 42, 63, 126)`, refresh/life pairs `((1,1),(5,5),(5,10),(10,10),(21,21))`, top counts `(10,20,40,80)`, exactly 400 unique specifications, and no event/fundamental fields.
- [ ] Run `python -m pytest tests/unit/test_full_market_session_decomposition.py -q`; expect failure because the module does not exist.
- [ ] Implement frozen constants and a frozen `Specification` dataclass whose Cartesian product is deterministic and exactly 400 cells.
- [ ] Re-run the focused test; expect pass.
- [ ] Commit with `git commit -m "Add session decomposition contract"`.

### Task 2: Implement causal session features

**Files:**
- Modify: `src/us_intraday_lab/full_market_session_decomposition.py`
- Modify: `tests/unit/test_full_market_session_decomposition.py`

**Interfaces:**
- Produces: `build_session_features(daily_bars: pd.DataFrame) -> pd.DataFrame` and `score_session_families(features: pd.DataFrame, lookback: int) -> pd.DataFrame`.

- [ ] Add hand-computed fixtures proving `overnight_log_return=log(open_t/close_t-1)`, `intraday_log_return=log(close_t/open_t)`, completed-bar rolling sums/hit rates/volatility, VWAP frequency, and dollar-volume ranks without future access.
- [ ] Add failure tests for duplicate symbol/session keys, nonpositive OHLC prices, invalid non-sentinel VWAP, and insufficient history remaining nonfinite.
- [ ] Run the focused tests and confirm the new tests fail.
- [ ] Implement schema validation, exact triple-zero VWAP-to-missing handling, causal grouped rolling features, winsorization, session cross-sectional percentile ranks, five fixed family equations, and symbol tie breaks.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Implement causal session decomposition features"`.

### Task 3: Implement exposure-leg portfolios

**Files:**
- Modify: `src/us_intraday_lab/full_market_session_decomposition.py`
- Modify: `tests/unit/test_full_market_session_decomposition.py`

**Interfaces:**
- Produces: `evaluate_session_scenarios(panel: pd.DataFrame, spec: Specification) -> dict[str, ScenarioResult]`.

- [ ] Add fixtures proving close-to-next-open returns for the three overnight families, next-open-to-next-close returns for the two intraday families, refresh/life cohort overlap, equal weights, exact 9/18bp charges per leg, and one-session delayed entry.
- [ ] Add fail-closed tests for selected missing entry/exit prices and selected zero-volume plus zero-trade-count exposure rows.
- [ ] Run focused tests and confirm failure.
- [ ] Implement deterministic selections, active cohort averaging, exposure-leg returns, shared selection hashes, and explicit invalid reasons without post-outcome deletion.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Add session exposure portfolio engine"`.

### Task 4: Bind atomic checkpoints and pre-null gates

**Files:**
- Modify: `src/us_intraday_lab/full_market_session_decomposition.py`
- Modify: `tests/unit/test_full_market_session_decomposition.py`

**Interfaces:**
- Produces: `RunIdentity`, `AtomicCheckpoint`, `evaluate_cell_record`, and `evaluate_cells_sequential`.

- [ ] Add tests for exact source/universe/design/code/gate identity binding, sequential cell indices, hash-chain verification, corrupt/mismatched resume refusal, annualized return, MDD, IR, z-score, five folds, and independent standard/cost/delay pre-null decisions.
- [ ] Run focused tests and confirm failure.
- [ ] Implement atomic replace-on-write checkpoints, one immutable cell JSON per completed cell, chain verification, metrics, and unchanged basic pre-null gates.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Add session campaign checkpoints and gates"`.

### Task 5: Add the immutable-source runner

**Files:**
- Create: `scripts/evaluate_full_market_session_decomposition.py`
- Modify: `tests/unit/test_full_market_session_decomposition.py`

**Interfaces:**
- Consumes: Task 1-4 module interfaces.
- Produces: external `state/full-market-session-decomposition-v1/` checkpoints and tracked aggregate JSON under `research/results/`.

- [ ] Add tests that the runner constants match exact source identities/counts, joins monthly eligibility causally, labels evidence consumed, writes aggregates only at 400/400, and keeps `paper_activation=false` plus `order_route=FORBIDDEN`.
- [ ] Run focused tests and confirm failure.
- [ ] Implement the DuckDB loader, point-in-time eligibility join, source audit, panel cache, design/code/gate hashes, resumable sequential evaluation, and complete-only aggregate writer.
- [ ] Run focused tests and Ruff; expect all pass, then commit with `git commit -m "Add session decomposition runner"`.

### Task 6: Run, freeze, and continue

**Files:**
- Create after completion: `research/results/2026-10-12-full-market-session-decomposition-cells.json`
- Create after completion: `research/results/2026-10-12-full-market-session-decomposition-summary.json`
- Create: `memory/2026-10-12-full-market-session-decomposition-result-local.md`

**Interfaces:**
- Consumes: exact frozen runner and identities.
- Produces: immutable rejection evidence or inputs to later robustness gates.

- [ ] Run the CLI sequentially, polling its atomic checkpoint rather than restarting a live process.
- [ ] Verify `status=COMPLETE`, `cells_completed=400`, exact identity hashes, empty stderr, and a valid terminal chain.
- [ ] If zero cells pass the basic pre-null gate, freeze rejection and skip neighborhood/Bonferroni/native-null work. If cells pass, execute the remaining frozen gates in order without changing the grid.
- [ ] Write structured local fallback memory with `project:quant-agent-team`, `market:cn_a`, and `freq:daily`; state that MCP memory was unavailable.
- [ ] Run focused tests, Ruff, `git diff --check`, commit tracked evidence, and push. Never add `state/`.

