# v46-v55 revised weak-market gate research

## Decision

No candidate is ready for simulated forward observation. The forward economic gates remain
unchanged: standard-cost annualized return at least 50%, maximum drawdown below 20%,
information ratio at least 1, plus the existing 18bp, one-extra-bar delay, folds, start-date,
neighborhood, historical-source, and multiple-comparison pressure checks. The only policy
change is that consumed 2026 is now a diagnostic pass when total return is greater than 5%.
It is not used to select factors, rank parameters, or claim independent OOS evidence.

The closest candidate remains `lev-v45e-0d302fbf92727a31`. It has 2024-2025 standard-cost
annualized return 60.47%, MDD 12.17%, IR 1.41; 18bp annualized return 56.38%; delayed
annualized return 57.03%; historical 2018-2020 annualized return 1.50% with MDD 17.79%; and
consumed-2026 total return 48.16%. It is not usable because every one of the six economically
qualified v45 definitions failed the factory-native 95th-percentile null tests. For the closest
definition, observed development profit was 1.280567 versus thresholds 1.326989 for session
signal permutation and 1.286955 for safe timestamp shift.

## Protocol

- Long only, no overnight positions, maximum gross exposure 1, and no broker/order path.
- Factor signs and parameter ranks use 2022-2025 only. Training is 2022-2023; 2024 and 2025
  are reported separately and together.
- Historical 2018-2020 and consumed 2026 are attached only after each bounded family is
  frozen. The separate historical provider is not spliced into the Alpaca source.
- Standard round-trip cost is 9bp; stress cost is 18bp; latency stress adds one 5-minute bar.
- The architecture-native null contract uses 200 repetitions, a fixed seed, session signal
  permutation, and session-safe timestamp shift.
- Generated JSON checkpoints are atomic and remain outside Git.

## Bounded scans

| Stage | Hypothesis | Scale / elapsed | Result |
|---|---|---:|---|
| v46 | Factory-native null validation of v45 | 6 candidates, 200 repetitions each | 0 null passes |
| v47 | Positive score slope before entry | 288 cells / 15.17s | 2 economic hits; both failed null tests |
| v48 | Path efficiency plus range-ratio timing | 192 cells / 11.56s | 0 revised-gate hits |
| v49 | Afternoon reclaim factors | 288 cells / 16.37s | 0 revised-gate hits |
| v50 | Strict first VWAP reclaim | 144 cells / 7.52s | 0 revised-gate hits |
| v51 | Relaxed VWAP reclaim zone | 240 cells / 12.87s | 0 revised-gate hits |
| v52 | Equal holding length across trigger times | 144 cells / 8.77s | 0 revised-gate hits |
| v53 | Cross-asset factor audit | 12 timing audits / 4.16s | Stable development-only signs found |
| v54 | Seven-factor cross-asset state model | 384 cells / 19.93s | 0 revised-gate hits |
| v55 | Factors conditional on v45 events | 13 factors, 141 events / 3.70s | 0 pooled or asset-specific stable factors |

The strategy scans evaluated 1,680 parameter cells, excluding factor-audit cells and null
replications. v47's two preliminary candidates had observed profits 1.2620 and 1.2467, below
both of their factory-null thresholds. v52 ruled out unequal signal-duration as the reason for
the v45 null failure: its best standard-cost OOS annualized return was 48.70%, historical
annualized return was -0.97%, and historical MDD was 24.59%. v54 showed that development-
stable cross-asset IC does not automatically create a robust portfolio; its best OOS annualized
return was 44.14%, historical annualized return was -10.00%, and consumed-2026 total return
was only 2.57%.

## Factor conclusions

The cross-asset audit found useful development-only signs around the 26th five-minute bar:
positive sector breadth, SPY/QQQ/IWM strength, risk-asset agreement, and cyclical-minus-
defensive strength; negative sector dispersion also predicted the subsequent leveraged-ETF
return. These factors were combined with current return, negative volume acceleration,
negative prior-20 rank, and negative prior-20 return in v54. The combined strategy failed the
hard economic and historical gates, so those factors are retained as research evidence rather
than a strategy recommendation.

The conditional v55 audit is more decisive for v45: none of 13 structure and cross-asset
factors kept the same IC direction across 2022-2023, 2024, and 2025, either pooled or separately
for TQQQ and SOXL. Therefore no post-hoc filter is justified to push the near-miss null statistic
over its threshold.

## Data coverage

The acquired Alpaca IEX snapshots cover their declared intervals from 2020-07-27 through
2026-08, including the completed 2026 partitions used only as consumed diagnostics. The
separate HF/Finnhub snapshots cover 2018-10 through 2020-12. Alpaca IEX does not provide the
requested pre-2020-07 boundary in this repository; this is a provider-history boundary, not a
missing session that can be safely filled. No rows were synthesized and no provider streams
were blended.

## Recommendation

Keep v45 as the leading research candidate, but do not add it to the existing observation pool.
Its economic, cost, latency, historical, and weak-market diagnostics are strong, yet the
predeclared factory-null gate fails. The next valid evidence is genuinely forward data under the
unchanged gate, not more filters selected on the consumed history. All current observation-pool
records remain unchanged.

## User-authorized admission update

After reviewing the failed-null distance, the user explicitly authorized v45 for a
research-shadow exception on 2026-08-16 and requested that prospective validation and new-factor
research proceed together. This does not change the null result or reclassify the candidate as a
full hard-gate pass.

- Campaign: `research-shadow-90b08a76631366856327b48d9d422c7b`
- Earliest prospective session: 2026-08-17
- Minimum prospective sessions: 120
- Route: `FORBIDDEN`
- Existing v4 and v4.1 campaigns: preserved unchanged
- Pre-admission database backup:
  `state/backups/research_shadow-pre-v45-20260816.sqlite3`

The forward evaluator was independently implemented against Alpaca IEX minute history. On the
2026-08-12 parity session it exactly reproduced the research engine's SOXL selection at bar 23,
exposure `0.8191278411818549`, raw standard return `-0.015319115627574808`, and scaled return
`-0.012548314112830567`.

The first post-admission independent family, v56 breadth-stabilization reversal, evaluated 3,888
cells in 66.80 seconds. It produced zero revised-gate hits. Its best development-ranked definition
had 2024-2025 standard annualized return 4.38%, IR 0.88, five trades, historical annualized return
-3.22%, and consumed-2026 total return +7.07%. The 2026 diagnostic passed, but the economic,
fold, historical, and multiplicity gates failed, so v56 was falsified without null promotion.
