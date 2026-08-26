# Homogeneous Paper pool consolidation

The user requested consolidation of homogeneous strategies on 2026-08-26 and explicitly said not
to change any execution times. The Alpaca Paper execution pool now contains only frozen v1254,
using the former pool's total account budget with the unchanged 0.99 gross cap. v247, v449 and
v798 are retired from execution, not erased from history.

## Why v1254

All four admitted candidates share the v45 anchor. On the 2026-08-25 session, every strategy held
the same SOXL anchor and TQQQ component. About 87.22% of starting account equity was invested in
SOXL. Four names were not four independent sources of risk.

The selection criterion is the minimum 2024-2025 annualized return across standard cost, doubled
cost and an extra five-minute entry delay, with existing transfer and component-null constraints.
Neither consumed 2026 nor the most recent Paper loss ranks candidates. v1254 has the strongest
stress floor (58.35%, versus 55.57% for v449 and 54.95% for v247), standard return (63.60%), and
slightly lower standard drawdown (11.36%). Its original 35/36 joint-neighborhood pass and routed
component-native null pass remain valid; its inherited v45 null and cumulative Bonferroni failures
remain explicit. Historical 2018-2020 annualized return is only 0.07%, so this is not proof of
independent robustness or a real-money promotion.

Consolidation does not add a concentration limit or a stop loss. v1254 can still allocate most
capital to the same anchor. It removes redundant execution, not all market risk.

## Safe migration

- Broker preflight confirmed Paper endpoint, zero positions and zero open orders.
- An online SQLite backup preserved all 50 prior events and passed integrity_check.
- All legacy Windows task XML definitions were exported before any task-state change.
- The runner now instantiates and evaluates only members in the active allocation map.
- Legacy strategy IDs remain recognized for reconciliation and independent closeout.
- New v1254 entry/closeout tasks are Ready; legacy tasks are retained but Disabled.
- Entry preparation is still 20:00 local weekdays. Decision bars remain 23/26/29; component and
  anchor exits remain bars 65/72. Backup closeout times remain 03:45 and 04:45 local.
- v1254 state-factor parity passed five source sessions with maximum absolute error 1.11e-16.
- No orders were submitted or canceled as part of migration; no brokerless shadow was mutated.
- Full-repository Ruff passed; pytest passed 874 tests (one upstream websockets deprecation
  warning) in 71.70 seconds. All 50 original ledger rows match the backup; the sole new row is
  the append-only POOL_CONSOLIDATION lifecycle event.

The structured lifecycle record is `research/results/2026-08-26-paper-pool-consolidation.json`.

## Independent-source research boundary

The next campaign excludes the v45 anchor and trades the eleven unleveraged sector ETFs only.
It must pass the existing economic and stress gates plus a preregistered development-return
correlation gate against frozen v1254. It may not enter Paper automatically.
