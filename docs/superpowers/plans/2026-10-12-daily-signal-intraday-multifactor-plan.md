# Daily-Signal Intraday Multi-Factor Implementation Plan

> **For agentic workers:** Execute inline with test-driven development; do not dispatch subagents.

**Goal:** Evaluate the frozen 400-cell technical-only open-to-close hypothesis.

**Architecture:** Reuse frozen daily loading and factor primitives, then add an isolated vectorized mapping from lagged scores and known open gaps to same-session open-to-close returns. Write immutable output through a separate CLI.

**Tech Stack:** Python, pandas, NumPy, pytest, Ruff, Parquet.

## Global Constraints

- Use only frozen 2021-2023 training outcomes and declared lookback history.
- Evaluate exactly 400 cells with 9/18 bp and one-session delay.
- Missing selected exits fail closed.
- No event/news input or execution-state mutation.

---

### Task 1: Engine and accounting

**Files:**
- Create: `tests/unit/test_daily_signal_intraday_multifactor.py`
- Create: `src/us_intraday_lab/daily_signal_intraday_multifactor.py`

- [ ] Write failing tests for the exact grid, gap modes, equal weighting,
      round-trip cost, delay mapping, and missing-close invalidation.
- [ ] Implement minimal vectorized score mapping and cell evaluation.
- [ ] Add and pass tests for frozen retention and two-family decision rules.

### Task 2: Immutable CLI and run

**Files:**
- Create: `scripts/diagnose_daily_signal_intraday_multifactor.py`
- Create: `research/results/2026-10-12-daily-signal-intraday-multifactor-summary.json`
- Create: `research/results/2026-10-12-daily-signal-intraday-multifactor-summary.md`
- Create: `memory/2026-10-12-daily-signal-intraday-multifactor-result-local.md`

- [ ] Test direct CLI startup and safety fields before implementation.
- [ ] Verify tests, Ruff, diff, commit and push before outcomes.
- [ ] Run once, require COMPLETE/400, freeze hashes and decision, write tagged
      fallback memory, verify, commit and push.
