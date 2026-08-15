# Full-data intraday continuation: v26-v32

Date: 2026-08-15

## Decision

No v26-v32 candidate is eligible for simulation observation. Two development-frozen routes exceeded 20% total return in consumed 2026, but neither approached the required 50% annualized development, 18bp, and one-bar-delay gates. The observation pool remains unchanged.

Candidate fitting, thresholds, shortlists, beams, and ranking used information through 2025 only. Consumed 2026 and the separate 2018-2020 source were attached after each frontier froze. No broker, credential, paper state, or order path was used.

## Results

| Stage | Falsifiable hypothesis | Trials | Seconds | 2026 >20 count | Best consumed 2026 total / MDD / IR | Dev OOS annual | 18bp annual | Delay annual | Historical annual |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v26 | Fixed-asset calendar and prior-session state with long holding windows | 187,432 | 76.97 | 0 | +17.31% / 4.69% / 1.81 | 13.61% | 12.24% | 17.54% | -7.91% |
| v27 | Prior-20-session cross-sectional strength/reversal rotation | 71,322 | 38.62 | 4 | +23.30% / 2.72% / 2.50 | 13.44% | 12.07% | 15.77% | -11.45% |
| v28 | QQQ/XLK unlevered proxy signals executed in TQQQ/SOXL | 339,765 | 215.82 | 0 | +1.59% / 7.79% / -0.04 | 19.59% | 11.91% | 12.38% | -13.59% |
| v29 | Four predeclared prior-session regimes over a development-stratified v20 sample | 1,200 | 10.38 | 2 | +21.79% / 7.14% / 1.91 | 16.17% | 13.68% | 11.15% | -3.82% |
| v30 | Four predeclared extra-tree configurations; fit 2022-23, threshold 2024 | 4 | 5.22 | 0 | +16.60% / 18.44% / 0.70 | -3.77% | -12.43% | -15.89% | +11.43% |
| v31 | QQQ-to-TQQQ proxy route isolated from SOXL competition | 250,516 | 184.35 | 0 | +13.86% / 4.33% / 1.85 | 12.91% | 7.09% | 9.53% | -17.45% |
| v32 | XLK-to-SOXL proxy route isolated from TQQQ competition | 136,809 | 94.90 | 0 | +15.16% / 14.29% / 0.96 | 8.52% | 3.25% | 5.05% | -11.56% |

Completed scale: 987,048 trials in 626.25 seconds.

## Gate audit

- The authoritative protocol remains annualized return >=50%, MDD <20%, IR >=1 on 2024-2025, positive 2022-23/2024/2025, repeated at 18bp and with an extra five-minute bar.
- No candidate passed the standard, 18bp, or delay primary gate.
- v27 had 44 of 62 frozen candidates pass four-of-five positive folds and 10 pass the historical-positive/MDD gate, demonstrating that those checks were not universally impossible; return magnitude remained the binding failure.
- v29 reduced its family-level comparison count to 1,200 via four predeclared regimes, but its best 18bp annualized return was only 13.68% and historical return remained negative.
- v30 limited nonlinear model comparison to four predeclared configurations. Its immediate 2025/generalization failure rejects further complexity expansion.
- Start-date and parameter-neighborhood promotion gates remain fail-closed because no candidate cleared the earlier primary gates.
- No candidate was added to simulation observation.

## Interpretation

Long holding windows and prior-20-session rotation can produce low-drawdown consumed-2026 diagnostics above 20%, but only through sparse exposure with development annualized returns around 13%-16%. Leveraged proxy execution does not close the gap: TQQQ and SOXL both remain cost-sensitive and negative on the independent historical source. The failure is therefore not attributable to one leveraged ETF alone.

The nonlinear model test supplied the opposite trade-off: historical return became positive, while development OOS and both execution stresses became negative. This is direct evidence against increasing model complexity on the current sample.

Status: research-only, not promotable, goal remains open.
