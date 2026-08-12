# Accelerated research and simulation-only paper shadow

## Decision

Historical minute replay is the primary strategy-development loop. A strategy
that passes every frozen historical hard gate may enter `paper_shadow`, where it
emits signals and theoretical fills only. The 120-session prospective campaign
remains useful evidence, but it is not a prerequisite for this zero-capital
simulation state.

No historical result permits broker order submission. Promotion beyond
`paper_shadow` still requires separate prospective evidence and an explicit
review.

## Research loop

1. Generate bounded, causal long-only strategy families.
2. Replay years of historical minute data with 1.5-times transaction costs.
3. Reject cells that fail the unchanged annual-return, information-ratio,
   drawdown, profit-factor, trade-count, fold, concentration, parameter,
   start-date, leave-one-symbol-out, or null-test gates.
4. Rank only the surviving cells by the weakest time-segment return, then OOS
   return quality.
5. Activate qualified strategies in simulation-only `paper_shadow`.
6. Continue collecting realtime observations to detect data-provider,
   execution, or regime drift.

## Paper-shadow activation contract

Activation must fail closed unless:

- the proposal and selection files match their recorded SHA-256 identities;
- every historical gate in the immutable selection is true;
- the selected winner and parameters match the research-shadow campaign;
- the campaign has the database-enforced order route `FORBIDDEN`;
- the activation artifact explicitly states that broker construction and order
  submission are forbidden.

The activation writes one immutable JSON artifact. Re-running with identical
inputs is idempotent; conflicting content at the same path is rejected.

## Evidence boundary

The historical evidence supports research and simulated observation, not a
claim of guaranteed profitability. Realtime five-minute bars add execution and
drift evidence but are not counted as independent trading sessions. The
prospective session count is retained as a separate long-term gate for any
future state that could submit orders.
