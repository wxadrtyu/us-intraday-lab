# v449 Alpaca Paper Trading activation

## Decision

The user authorized actual Alpaca Paper Trading for frozen candidate
`lev-v449-03e9e3f9c4b21390` on 2026-08-22. This adds an execution campaign; it does not alter or
remove the existing brokerless research-shadow campaign or any earlier observation.

The adapter is permanently restricted to `https://paper-api.alpaca.markets` and accepts only
`ALPACA_PAPER_API_KEY` plus `ALPACA_PAPER_SECRET_KEY`. Live credentials and the live endpoint have
no execution path. The account preflight found an active USD paper account with USD 100,000 equity,
zero positions, zero open orders, and no trading blocks. Alpaca reported a multiplier of four; the
controller ignores it and sizes from cash and equity with a 0.99 capital buffer.

## Frozen strategy and retained warnings

The order controller imports the exact v45 anchor and v60 component factor functions from the
prospective evaluator. The allocation remains 95% anchor plus 5% component, with per-sleeve
15-session volatility targeting at 35%, long-only TQQQ/SOXL, maximum gross one, and no overnight
position. No parameter was re-ranked using 2026 data.

The admission remains an explicit exception. The inherited v45 factory-native null test and global
Bonferroni test remain failed; the v60 component null test passed. Paper performance cannot be used
to relabel those tests as passing.

## Execution safety

- Entry decisions occur only after the close of frozen 5-minute bars 23, 26, and 29. An entry more
  than two minutes late is skipped.
- The component exits at bar 65 open and the anchor exits at bar 72 open. A separate 15:45 New York
  closeout flattens any residual TQQQ/SOXL paper position.
- Each order has a deterministic client order ID. A SQLite ledger records `ORDER_PREPARED` before
  submission and is protected by database triggers against update or delete. Restart recovery asks
  Alpaca for the client order ID before any resubmission.
- The account is treated as dedicated. Foreign orders or positions block entries. Same-session
  positions must reconcile exactly to filled v449 entry and exit quantities.
- The paper runner is scheduled at 20:00 Asia/Shanghai on Monday through Friday. It uses Alpaca's
  market clock for the actual XNYS session. Independent 03:45 and 04:45 Asia/Shanghai safeguards on
  Tuesday through Saturday cover both US daylight and standard time and only act when New York time
  is at least 15:40 and the market is open.

## Validation before activation

- Read-only Alpaca preflight: paper endpoint, active account, zero positions, zero open orders.
- 2026-08-11 factor parity using 307,256 fetched IEX minute rows: both engines selected SOXL at bar
  23; anchor exposure was `0.8215961476705926` and component exposure was `1.0`.
- Unit coverage includes cash-only two-sleeve sizing, independent same-symbol exits, restart
  idempotency, contaminated-account blocking, emergency flattening, and append-only ledger guards.
- Ruff, 85 paper unit tests, and all 849 repository tests pass. Both registered Windows tasks were
  manually invoked in the closed-market state and returned task result zero. Repository-wide mypy retains pre-existing pandas typing errors
  in `v45_research_shadow.py` and `long_horizon/orchestrator.py`; the new and changed source files
  pass targeted strict mypy.

The first eligible execution session is 2026-08-24. The market was closed at activation, so no
order was submitted on 2026-08-22.
