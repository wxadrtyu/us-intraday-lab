# Alpaca Paper IEX five-minute readiness fix

## Outcome

The Paper runner's current-session readiness gate now matches the frozen
research engine's sparse-IEX five-minute aggregation semantics. Missing
one-minute IEX trades remain missing; no forward fill or synthetic bar is
introduced.

## 2026-08-24 incident

The entry decisions at bars 23, 26, and 29 were rejected by the former gate,
which required every one-minute bar for all 16 context and traded ETFs. Alpaca
IEX legitimately omitted minutes for several sector ETFs. The account remained
flat and no order was submitted.

A causal replay after the fix showed:

- all three decision snapshots pass the five-minute readiness gate;
- bar 23 would have produced an SOXL anchor signal;
- bars 26 and 29 produce no additional signal.

The missed bar-23 order was not chased. The append-only ledger retains both the
original data incidents and the subsequent late-window skips.

## New boundary

For each decision, TQQQ and SOXL must each have at least one real IEX minute in
every closed five-minute bucket through the decision bar. Context ETFs no
longer block a current-session decision merely because IEX emitted no trade in
an individual minute. Frozen factor functions still reject or omit a signal
when a required five-minute input is absent.

## Verification

- Ruff: passed.
- Pytest: 862 passed, one third-party deprecation warning.
- Targeted Paper tests: 15 passed.
- v1254 factor parity: five sessions passed; maximum absolute error
  `1.1102230246251565e-16`.
- Alpaca Paper preflight after restart: market open, zero positions, zero open
  orders.

The repaired runner was started at 2026-08-25 00:40 Asia/Shanghai to retain
closeout monitoring only. All frozen entry windows had already expired. The
four-member scheduled pool will use the repaired gate from the next session.
