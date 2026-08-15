# Full-data v34-v45 multi-factor research

Date: 2026-08-15

## Decision

No strategy is approved for simulated observation from this campaign.

The strongest research candidate is `lev-v42t-4ab46f5ea0372d0e`. It passes the
standard-cost, 18 bp, five-minute-delay, five-fold, old-history drawdown, and
consumed-2026 diagnostic gates. It remains research-only because its strict
parameter neighborhood is narrow and the global multiple-comparison gate fails.
The observation pool and all broker/order surfaces remain unchanged.

## Protocol

- All factor selection, model fitting, sleeve ranking, portfolio ranking, state
  gates, and volatility-target parameters use 2022-2025 only.
- 2026 is consumed diagnostic data. It is attached only after each development
  frontier is frozen and is never described as independent OOS.
- Historical 2018-2020 is a post-freeze start-date/regime stress.
- Strategies are long-only, have gross exposure at most one, and close before
  the session ends.
- Standard cost is 9 bp per completed trade; the cost stress is 18 bp. Delay
  stress enters one additional five-minute bar later.
- Missing entry/exit prices fail closed to cash. During this campaign the shared
  rank-ensemble execution helper was hardened to enforce finite, positive prices
  in delay scenarios. A later causal audit separated training-label availability
  from signal-time availability: ranking may not use knowledge that a future exit
  price will be missing. The v40-v45 headline figures below use corrected causal
  execution artifacts.

## Factor pool

The causal pool contains trend, flow, structure, volatility, cross-sectional,
and state groups. New minute-path factors added in v34 are path efficiency,
trend consistency, signed volume imbalance, volume acceleration, current
cross-sectional rank, and prior-20-day cross-sectional rank. The complete pool
also includes current/recent/relative return, VWAP distance, close location,
range ratio, realized volatility, session range, sector breadth, prior-one-day
return, prior-20-day return, gap, SPY prior-20-day return, and SPY volatility.

The factor audit evaluates IC separately in 2022-2023, 2024, and 2025. It found
stable but time-of-day-dependent effects. Examples include positive opening path
efficiency/current rank, negative morning volume acceleration, positive morning
trend consistency, positive midday range/volatility for diversified assets, and
positive afternoon prior-20-day rank. This evidence justified multi-factor
models but did not justify a single universal linear score.

## Campaign results

| Stage | Search | Trials | Main result |
| --- | --- | ---: | --- |
| v34 | static ridge multi-factor sets | 108 | zero eligible; best consumed-2026 diagnostic +8.9%, development OOS negative |
| v35 | stable-sign rank ensembles | 96 planned, 28 evaluated | zero eligible; best 2026 diagnostic +76.0%, but development OOS +6.0% and 18 bp negative |
| v36 | rolling causal IC weighting | 144 | zero eligible; adaptive weights chased unstable development effects |
| v37 | three-period stable factor voting | 108 planned, 12 evaluated | zero eligible; best 2026 diagnostic +34.7%, development OOS -6.1% |
| v38 | sleeve boundary scan plus portfolio beam | 4,428 sleeve and 6,268 portfolio trials | development OOS +56.2% for the leader, but MDD 28.6%, 18 bp +28.5%, delay +12.7%, 2026 +12.0% |
| v39/v41 | causal market-state gates | 25,600 and 51,200 | reduced some drawdowns but destroyed the hard return gates; zero eligible |
| v40 | one-trade-per-day stable multi-factor search | 10,176 planned, 6,200 evaluated | found the v40 parent of the strongest candidate |
| v42 | causal 20/40/60-day volatility targets | 6,000 | two equivalent variants pass all core gates except multiplicity and pending focused stresses |
| v43 | focused ablation, neighborhood, and start-date stress | 4 ablations and 243 planned neighbors | start dates 5/5 pass; strict neighborhood only 3/135 evaluated variants pass; multiplicity fails |
| v44 | fixed-direction multi-horizon confirmation | 810 | zero eligible; averaging adjacent decision horizons does not reproduce the v42 edge |
| v45 | first-crossing event trigger | 1,296 | six candidates pass all economic/history/2026 gates, but none passes global multiplicity |

Total explicitly recorded parameter/portfolio cells in v34-v45 exceed 106,000.
The individual scripts record exact elapsed time and evaluated/rejected counts in
atomic JSON artifacts under `artifacts/accelerated_research`.

## Strongest candidate

`lev-v42t-4ab46f5ea0372d0e` is a one-trade-per-day leveraged-ETF rotation between
TQQQ and SOXL. At decision bar 23 it combines four factors:

1. positive current intraday return;
2. negative volume acceleration;
3. negative prior-20-day cross-sectional rank; and
4. negative prior-20-day asset return.

It trades only when the reliability-weighted standardized score is at least 0.5,
exits at bar 72, and caps exposure using a causal 20-session 30% volatility
target. Gross exposure never exceeds one.

| Period/scenario | Annualized return | Total return | MDD | IR | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022-2023 train, standard | 21.59% | 47.49% | 13.11% | 1.08 | 108 |
| 2024, standard | 31.15% | 31.15% | 13.28% | 1.21 | 68 |
| 2025, standard | 98.73% | 97.11% | 12.68% | 1.66 | 60 |
| 2024-2025 OOS, standard | 61.24% | 158.50% | 13.28% | 1.44 | 128 |
| 2024-2025 OOS, 18 bp | 54.13% | 136.35% | 13.84% | 1.29 | 128 |
| 2024-2025 OOS, +5-minute delay | 61.54% | 159.47% | 15.28% | 1.46 | 125 |
| 2018-2020 historical stress | 10.27% | 24.46% | 18.24% | 0.58 | 124 |
| 2026 Q1 consumed diagnostic | 25.52% | 5.66% | 3.89% | 1.34 | 10 |
| 2026 all consumed diagnostic | 43.38% | 24.45% | 9.05% | 1.60 | 54 |

The five chronological development folds are all positive. The candidate also
passes positive-return/MDD checks for five alternative start dates from
2022-01-01 through 2024-01-01.

## Why it is not approved

The focused neighborhood varies decision 20/23/26, exit 69/72/75, score
threshold 0.25/0.50/0.75, target volatility 25%/30%/35%, and lookback 15/20/25.
Only 135 of 243 combinations retained a valid stable-factor model, and only
three passed all standard, cost, and delay primary gates. All three retained the
same decision 23 and exit 72 boundary. This is insufficient parameter-neighborhood
support.

All four leave-one-factor-out ablations fail the complete primary-gate set. That
supports the multi-factor interpretation, but it also shows the result is not
carried by a broad redundant factor ensemble. Most importantly, the candidate
does not pass the pre-existing global Bonferroni gate after the large correlated
research family. The campaign does not waive or redefine that gate after seeing
the result.

## Event-trigger follow-up

v45 replaces the fixed decision bar with the first score crossing over bars
20/23/26/29, optionally requiring two consecutive confirmations. Six variants
pass the standard, 18 bp, delay, fold, historical-MDD, and consumed-2026 gates.
The representative `lev-v45e-0d302fbf92727a31` has 2024-2025 standard/18 bp/delay
annualized returns of 60.47%/56.38%/57.03%. Its consumed-2026 diagnostic total
return is 48.16%, with 5.53% MDD and 2.78 IR. However, 2024 contributes only
13.46% standard annualized return while 2025 contributes 127.93%, historical
2018-2020 annualized return is only 1.50%, and the 1,296-member family fails the
global Bonferroni gate. It is therefore not approved despite materially reducing
fixed-bar dependence.

## Next falsifiable directions

- Seek a separately motivated interaction factor for intraday continuation after
  medium-term weakness and declining relative volume, then test it as a small
  predeclared family.
- Test event-triggered, once-daily formulations whose decision time is determined
  by a causal state transition rather than a fixed bar.
- Preserve the v42 candidate as a research benchmark only. Do not add it to the
  observation pool unless a future predeclared family supplies broad timing
  neighborhoods and multiplicity-safe evidence.

## Revision log

- 2026-08-15: initial v34-v44 multi-factor campaign report.
- 2026-08-15: corrected signal-time availability and added causal v40-v45 reruns.
