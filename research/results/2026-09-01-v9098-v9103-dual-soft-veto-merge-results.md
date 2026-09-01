# v9098-v9103 dual soft-veto merge results

## Outcome

- Economic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 5 / 5
- Cumulative comparison cells: 257,982
- Strict pre-factory-null passes: 5 / 5
- Native factory null: 500 repetitions, two max-T methods
- Native factory null passes: 5 / 5
- Preregistered primary: `lev-v9100-87067c388a289dba` (50/50 parent exposure merge)
- Paper-pool changes: 0

The preregistered equal-gross merge passed every economic, cost, delay,
historical, fold, start-date, neighborhood, consumed-period, prospective-z,
and native-null gate. Its 2024-2025 metrics were 110.10% annualized return,
12.11% maximum drawdown, and 2.373 IR at 9bp; 91.20%, 12.69%, and 2.034
at 18bp; and 93.75%, 16.50%, and 2.214 with an extra five-minute delay.

The independent 2018-2020 annualized returns were 41.76%, 29.26%, and
35.02% in the three scenarios. Consumed diagnostics, not used for selection,
were +9.47% for 2026 Q1 and +27.23% for all available 2026. The prospective
z-score was 3.125 and all five fixed weight neighbors passed the primary gate.

The primary candidate's observed development compound profit was 11.0775,
above both the session-permutation max-T threshold (7.3128) and safe-shift
max-T threshold (7.2878). The native-null evidence hash is
`4c65a032506458ad19b4b329b7b13463fb7f79372e0250b3fd7995db95ecede5`.

This is research admission only. Production admission remains fail-closed
until a dedicated brokerless evaluator reproduces both parent exposures and
the convex merge with exact research parity. The next unused version is v9104.
