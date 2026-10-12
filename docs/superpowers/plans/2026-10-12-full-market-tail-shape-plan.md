# Full-market daily tail-shape multifactor implementation plan

> **Frozen 2026-10-12:** Do not execute. The user replaced daily research with intraday strategies whose single-trade holding period is at most 5-10 minutes. No implementation or outcome read occurred.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the frozen 400-cell full-market daily tail-shape campaign without relaxing any evidence, missingness, or execution gate.

**Architecture:** A focused pure module owns the immutable grid, causal return-distribution features, deterministic cross-sectional scores, overlapping open-to-open portfolios, metrics, and hash-chained checkpoints. A thin CLI verifies the exact external identities, constructs the point-in-time full-market panel, evaluates cells sequentially, and publishes tracked aggregates only after complete execution.

**Tech Stack:** Python 3.12, pandas, NumPy, DuckDB, PyArrow/Parquet, pytest, Ruff, SHA-256 JSON identities.

## Global Constraints

- Read only frozen daily source SHA-256 `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701` and universe SHA-256 `3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.
- Use only daily OHLCV/VWAP/trade-count and derived return-distribution fields; issuer-event data is forbidden.
- Treat 2021-2026 as consumed; never claim independent OOS evidence.
- Bind every score column to both family and lookback; no score may silently reuse another lookback.
- Missing selected entry/exit/path bars and selected triple-zero liquidity rows invalidate the cell; never convert them to cash or zero return.
- Preserve annualized return >40%, MDD <20%, IR >=1, z >=3, 4/5 positive folds, 9/18bp, delay, start-date, 70% neighborhood, Bonferroni <=0.05, and both 500-repetition native maxT gates.
- Keep Paper activation false and order routing forbidden.

---

### Task 1: Freeze the contract and grid

**Files:**
- Create: `src/us_intraday_lab/full_market_tail_shape.py`
- Create: `tests/unit/test_full_market_tail_shape.py`

**Interfaces:**
- Produces: `Specification`, `specifications()`, `FAMILIES`, `LOOKBACKS`, `REBALANCE_HOLDING_PAIRS`, `TOP_COUNTS`, and `score_column(family, lookback)`.

- [ ] Write a failing test asserting the five exact families, lookbacks `(20,42,63,126)`, rebalance/holding pairs `((1,1),(5,5),(5,10),(10,10),(21,21))`, top counts `(10,20,40,80)`, exactly 400 unique specifications, and lookback-bound score-column names.
- [ ] Run `python -m pytest tests/unit/test_full_market_tail_shape.py -q`; expect failure because the module does not exist.
- [ ] Implement frozen constants and a frozen `Specification` dataclass whose Cartesian product is deterministic and exactly 400 cells.
- [ ] Re-run the focused test; expect pass.
- [ ] Commit with `git commit -m "Add tail shape campaign contract"`.

### Task 2: Implement causal tail-shape features

**Files:**
- Modify: `src/us_intraday_lab/full_market_tail_shape.py`
- Modify: `tests/unit/test_full_market_tail_shape.py`

**Interfaces:**
- Produces: `build_tail_shape_features(daily_bars: pd.DataFrame, lookback: int) -> pd.DataFrame` and `score_tail_shape_families(features: pd.DataFrame, lookback: int) -> pd.DataFrame`.

- [ ] Add hand-computed fixtures proving close-to-close log returns, maximum return, positive-tail mean, skewness, downside semideviation, worst return magnitude, 5% expected shortfall, arithmetic/geometric drag, jump fraction, kurtosis, overnight-gap variance share, upside/downside tail balance, and peak-to-trough drawdown use completed sessions only.
- [ ] Add failure tests for duplicate symbol/session keys, nonpositive OHLC prices, invalid non-sentinel VWAP, zero variance, insufficient tail counts, nonfinite ratios, and insufficient history remaining missing.
- [ ] Run focused tests and confirm the new tests fail.
- [ ] Implement schema validation, exact triple-zero VWAP-to-missing handling, causal grouped rolling calculations, within-session winsorized percentile ranks, deterministic normalized-symbol tie breaks, and the five fixed family equations.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Implement causal tail shape features"`.

### Task 3: Implement open-to-open portfolios

**Files:**
- Modify: `src/us_intraday_lab/full_market_tail_shape.py`
- Modify: `tests/unit/test_full_market_tail_shape.py`

**Interfaces:**
- Produces: `evaluate_tail_shape_scenarios(panel: pd.DataFrame, spec: Specification) -> dict[str, ScenarioResult]`.

- [ ] Add fixtures proving the decision at completed session `t`, standard entry at open `t+1`, delayed entry at open `t+2`, exit after the frozen holding horizon, rebalance/holding cohort overlap, equal weights, and exact 9/18bp round-trip costs.
- [ ] Add deterministic selection and tie-break tests for every `(family, lookback)` score column.
- [ ] Add fail-closed tests for selected missing entry/exit/intermediate path bars and selected zero-volume plus zero-trade-count held sessions.
- [ ] Run focused tests and confirm failure.
- [ ] Implement deterministic selections, active-cohort averaging, open-to-open returns, shared selection hashes, and explicit invalid reasons without post-outcome deletion.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Add tail shape portfolio engine"`.

### Task 4: Bind atomic checkpoints and pre-null gates

**Files:**
- Modify: `src/us_intraday_lab/full_market_tail_shape.py`
- Modify: `tests/unit/test_full_market_tail_shape.py`

**Interfaces:**
- Produces: `RunIdentity`, `AtomicCheckpoint`, `evaluate_cell_record`, and `evaluate_cells_sequential`.

- [ ] Add tests for exact source/universe/design/code/gate identity binding, sequential cell indices, terminal hash-chain verification, corrupt or mismatched resume refusal, annualized return, MDD, IR, z-score, five folds, and independent standard/cost/delay pre-null decisions.
- [ ] Run focused tests and confirm failure.
- [ ] Implement atomic replace-on-write checkpoints, one immutable cell JSON per completed cell, chain verification, metrics, and unchanged basic pre-null gates.
- [ ] Re-run focused tests; expect pass, then commit with `git commit -m "Add tail shape checkpoints and gates"`.

### Task 5: Add the immutable-source runner

**Files:**
- Create: `scripts/evaluate_full_market_tail_shape.py`
- Modify: `tests/unit/test_full_market_tail_shape.py`

**Interfaces:**
- Consumes: Task 1-4 module interfaces.
- Produces: external `state/full-market-tail-shape-v1/` checkpoints and tracked aggregate JSON under `research/results/`.

- [ ] Add tests that runner constants match exact source identities/counts, monthly eligibility joins causally, evidence is labeled consumed, aggregates write only at 400/400, and `paper_activation=false` plus `order_route=FORBIDDEN` remain fixed.
- [ ] Run focused tests and confirm failure.
- [ ] Implement the DuckDB loader, point-in-time eligibility join, source audit, panel cache, design/code/gate hashes, resumable sequential evaluation, and complete-only aggregate writer.
- [ ] Run focused tests and Ruff; expect all pass, then commit with `git commit -m "Add tail shape campaign runner"`.

### Task 6: Run, freeze, and continue

**Files:**
- Create after completion: `research/results/2026-10-12-full-market-tail-shape-cells.json`
- Create after completion: `research/results/2026-10-12-full-market-tail-shape-summary.json`
- Create: `memory/2026-10-12-full-market-tail-shape-result-local.md`

**Interfaces:**
- Consumes: exact frozen runner and identities.
- Produces: immutable rejection evidence or inputs to later robustness gates.

- [ ] Run the CLI sequentially, polling its atomic checkpoint rather than restarting a live process.
- [ ] Verify `status=COMPLETE`, `cells_completed=400`, exact identity hashes, empty stderr, and a valid terminal chain.
- [ ] If zero cells pass the basic pre-null gate, freeze rejection and skip neighborhood/Bonferroni/native-null work. If cells pass, execute the remaining frozen gates in order without changing the grid.
- [ ] Write structured local fallback memory with `project:quant-agent-team`, `market:cn_a`, and `freq:daily`; state that MCP memory was unavailable.
- [ ] Run focused tests, Ruff, `git diff --check`, commit tracked evidence, and push. Never add `state/`.
