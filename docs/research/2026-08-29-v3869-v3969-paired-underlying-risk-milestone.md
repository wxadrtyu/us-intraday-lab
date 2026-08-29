# v3869-v3969 paired-underlying risk milestone

## Outcome

The 100-version paired-underlying campaign completed in 22.52 seconds. The legacy evaluator identified 25 records that passed its positive-history pre-null contract. A strict audit against this campaign's frozen 15% historical annualized-return floor found zero fully eligible records, so there is no automatic admission.

The development-ranked candidate `risk-v3929-ada080220b281afd` nevertheless passed the separately preregistered v3969 family-wise native risk-timing null. It is retained as `RISK_MILESTONE_HISTORICAL_EXCEPTION_REVIEW`, not as a strict hard-gate pass and not as a Paper-pool member.

## Frozen mechanism

The v1254 multifactor entry, symbol selection and dynamic sleeve weights are unchanged. The anchor sleeve uses the following causal post-entry policy:

- hard loss threshold: 7% on the selected leveraged ETF;
- hard-loss confirmation: its paired QQQ or XLK completed five-minute return since entry is at most -1%;
- profit protection: activate after a +1.5% completed-close peak and exit after a 2.5% peak-to-close giveback;
- execution: next complete five-minute bar open;
- one re-entry only after the selected ETF recovers 0.25% from the exit open and the paired underlying is nonnegative from its exit open;
- same-symbol aggregate gross cap: 0.775;
- long only, maximum gross one, flat overnight.

## Candidate evidence

| Scenario / period | Annualized return | MDD | IR | Total return |
| --- | ---: | ---: | ---: | ---: |
| 2024-2025, 9 bp | 60.67% | 6.28% | 1.750 | 156.70% |
| 2024-2025, 18 bp | 55.63% | 6.35% | 1.628 | 140.95% |
| 2024-2025, +5 minute delay | 57.36% | 6.43% | 1.673 | 146.30% |
| consumed 2026 Q1, 9 bp | 37.48% | 1.03% | 2.238 | 8.01% |
| consumed 2026 through August, 9 bp | 74.40% | 5.71% | 2.881 | 40.17% |

All five development folds are positive in all three scenarios. All start-date returns are positive. The primary parameter-neighborhood share is 100%. Matched-validity MDD reductions are 54.02%, 54.32% and 59.37%; five-percent expected-shortfall reductions are 20.19%, 19.82% and 25.17% for standard, 18 bp and delay.

## Binding exceptions

- 2018-2020 standard annualized return / MDD: +0.19% / 15.43%, below the frozen 15% return floor.
- 2018-2020 18 bp annualized return: -2.60%.
- 2018-2020 delay annualized return: +6.00%.
- Cumulative 201,805-cell Bonferroni p-value: 1.0.
- The reused evaluator's `historical_positive_mdd_below_20pct` gate did not implement the proposal's stronger 15% floor. The append-only result remains preserved, and the stricter audit reports zero qualifying records rather than relabeling its 25 legacy-contract hits.

## v3969 native risk-timing null

- Eligible legacy-contract family: 25 candidates
- Development OOS sessions: 501
- Repetitions: 200
- Observed normalized worst risk improvement: 1.3211
- Session-permutation family-wise maxT 95% threshold: -1.0717
- Safe-circular-shift family-wise maxT 95% threshold: -1.1744
- Result: pass
- Evidence SHA-256: `2563a81c289d93f0cfe1be388de0e85667fb82a81a4be890ae9de34e4acf8672`

This null validates timing-specific risk reduction, not independent alpha, the historical return floor, or global multiple-comparison significance. No broker, submit, cancel, credential, Paper strategy, weight, clock or order path changed.

