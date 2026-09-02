# v11800 execution parity

Candidate: `lev-v11800-90804cea426c9753`

Status: `EXECUTION_PARITY_PASSED_BUT_RESEARCH_REJECTED_CUMULATIVE_BONFERRONI`

The frozen contract reuses the v11098 causal DataFrame feature and leg adapter. The only strategy change is the preregistered hard-cash late-sleeve quality veto: a rejected bar-5 outer gate now receives zero late exposure instead of 25%. Opening, routing, symbols, entry clocks, exit clocks, long-only behavior, no-overnight behavior, and gross-at-entry constraints are unchanged.

## Evidence

- Frozen contract SHA-256: `ad4df82c8a0624d52501943304193f43a3211eebcc6db1d9d02ad6ce10c09985`
- Daily forward-plan parity: 1,407 sessions, zero maximum return error, zero active-session mismatches, causal route clock passed.
- Full live signal replay: 1,347 sessions and 2,345 emitted legs.
- Maximum daily return error: `6.938893903907228e-18`.
- Opening error: zero; late-route error: `6.938893903907228e-18`.
- Outer gate, modern state, transfer gate, fill gate, active state, and parent checks: zero mismatches/failures.
- Gross limit violations: zero.

This closes research-to-live-signal parity only. A later gate-contract audit
found cumulative Bonferroni p=1.0, so the candidate is rejected and remains
excluded from `POOL_ALLOCATIONS`. The parity evidence is retained for audit;
it does not authorize runner wiring or Paper trading.
