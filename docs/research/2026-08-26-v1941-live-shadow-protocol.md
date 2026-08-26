# v1941: 2026-08-26 prospective signal-capture protocol

This is a **single-session brokerless engineering/behavioral validation**, not Paper admission,
not proof of positive alpha, and not a replacement for native-null or global-comparison gates.
The user authorized tonight's validation after the v1865-v1965 offline risk-overlay research.
The existing v1254 Alpaca Paper task, allocation, strategy, credentials, ledger and clocks are unchanged.

## Frozen hypothesis and boundaries

- Candidate `risk-v1941-d230dcf6cfea997c`; original v1254 signals and sleeve weights, multiplied
  by a frozen risk budget. This scales the existing strategy; it is not an independent return source.
- Four bar17 factors: sector breadth, sector dispersion, SPY current return, SPY realized volatility.
  All coefficients are +1. Means/scales must exactly match the committed research result.
- Threshold `-0.3998694619090091`: score at/above threshold gives 0.9 budget;
  below gives 0.45; missing state gives cash. No tuning tonight.
- Long-only, gross <=0.9, fixed same-day exits. No broker construction, submit/cancel or account access.
  Read-only market data uses active environment credentials and Alpaca IEX only.
- Preserve inherited v45 null failure, incomplete native overlay null, and global Bonferroni failure.
  2026Q1 and historical 2026 development data remain consumed diagnostics, never fresh OOS.

## Beijing schedule (US session 2026-08-26)

| Event | Beijing time |
| --- | --- |
| Existing Paper market open | Aug 26 21:30; existing task already started at 20:00 |
| Freeze candidate state (bar17 closed) | Aug 26 23:00 |
| Original decision bars 23 / 26 / 29 close | Aug 26 23:30 / 23:45 / Aug 27 00:00 |
| Component theoretical exit bar65 | Aug 27 02:55 |
| Anchor theoretical exit bar72 | Aug 27 03:30 |
| Fetch final prices and write comparison | Aug 27 03:40 |

Signals/state are captured only within two minutes after their window opens. All inputs are truncated
at the decision boundary. The state is frozen once; later snapshots cannot revise it. A missed window
or missing data is explicitly recorded, never reconstructed later. Failures do not affect Paper.
The process must remain running on this Windows computer; shutdown/sleep/network loss can prevent
completion. This is a one-session process, not a recurring task or a cloud deployment.

## Outcomes to record, without cherry-picking

Append-only `state/research_shadow_v1941/2026-08-26/events.sqlite3` records startup, context prefetch,
state, signal/no-signal/skip, theoretical exposure, and final result. SHA-256 snapshots are retained
locally. An OS-held lock rejects duplicate processes. Restart reuses frozen observations and verifies
the prior-context snapshot; it cannot backfill missed decisions.

At 03:40, compare raw v1254, state-availability-matched v1254, and v1941 theoretical daily returns:
9bp round trip, 18bp, extra one 5-minute entry-bar delay, and the first full minute after receipt plus
9bp. Exit clock is unchanged. Prices must be present at the exact minute; no imputation or provider
splicing. These are IEX reference prices, **not realizable broker fills or live account PnL**.
The ordinary next-bar-open reference can precede actual signal receipt; the receipt-based scenario
exists to expose that optimism. Missing any required fill invalidates the scenario, not a zero return.
Candidate cash is reported separately from a missing baseline price.

Engineering success requires all four live captures on time, valid state, bounded gross, intact
snapshots and complete price scenarios. No-signal is a valid observation but supplies no profitability
evidence. Economic outcomes, including underperformance and losses, are retained. A single profitable
night does not satisfy the unchanged strategy-admission/forward gates.

## Pre-launch checks

- Frozen factor calculation matched the original research cube for nine sessions in 3.381 seconds:
  2024-08-07 (missing state -> cash), and 2026-08-03 through 2026-08-12. Tolerance 1e-12.
- The 2026-08-11 budget is 0.45; the other seven August sessions use 0.9.
- Targeted tests cover frozen identity, causal truncation, missing boundaries, breadth denominator,
  append-only evidence, cost/delay/receipt prices, no-order runner and no retrospective signals.

Run manually for this authorized session only:

```powershell
./scripts/start_v1941_research_shadow.ps1 -Session 2026-08-26
```

No raw snapshots, credentials, SQLite files or runtime logs belong in Git.

## Activation evidence (before market open)

- Started the independent hidden Python process at Beijing 20:23:17, PID 18196.
- `STARTUP` and `PREFETCH` events exist; the process reached `READY`.
- Prefetch: 298,381 IEX rows, 16 symbols, 51 regular sessions through 2026-08-25.
- Existing `USIntradayLab-V1254-AlpacaPaper` remains `Running`.
- No live state or strategy signal exists yet: those windows have not opened.
- Ten targeted tests passed, including a simulated end-to-end night and a fully missed session.
- Final full suite: **896 passed** in 70.28 seconds; one existing websockets deprecation warning.
  Repository-wide Ruff check passed. Existing Paper code/task installer files have no diff.
