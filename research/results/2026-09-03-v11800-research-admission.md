# v11800 branch-causal hard-veto research admission

`lev-v11800-90804cea426c9753` passed the primary, stress, historical, fold,
start-date, neighborhood, consumed-diagnostic, z-score screen, native
factory-null, and execution-parity checks. A subsequent contract audit found
that the evaluator substituted a z>=3 screen for the explicitly required
cumulative Bonferroni p<0.05 gate. Its cumulative Bonferroni p is 1.0, so the
candidate is rejected despite the other passes.

- 2024-2025 standard: 103.58% annualized, 9.66% MDD, IR 2.46.
- 2024-2025 18bp: 85.04% annualized, 10.21% MDD, IR 2.09.
- 2024-2025 delay: 101.67% annualized, 8.92% MDD, IR 2.41.
- 2018-2020 standard / 18bp / delay: 28.11% / 16.72% / 25.16% annualized.
- Consumed 2026 Q1 / all-2026: 9.34% / 5.26%.
- Prospective z-score: 3.196; neighborhood primary share: 100%.

The v11808 native maxT null covered both eligible hard-veto candidates with
500 repetitions. v11800's observed development profit was 7.185, above the
permutation 95th percentile of 5.807 and safe-shift 95th percentile of 5.660.
Both candidates passed. Evidence SHA-256:
`5d1645e7ae819f1b13fce874b92ad40d6037409e6cf9a4d32d56bb5493de41f0`.

The only architectural change from v11098 is that a rejected causal bar-5
late-route quality decision uses cash instead of 25% exposure. Opening signals,
branch decisions, parent selection, and entry/exit clocks are unchanged.

The corrected status is `REJECTED_CUMULATIVE_BONFERRONI_GATE`. The frozen
contract and parity evidence remain useful audit artifacts, but native max-T
and execution parity do not override a failed declared gate. No Paper
allocation, runner, broker, or order state changed.
