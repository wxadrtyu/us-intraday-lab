# Full-data intraday v13-v16 results

## Decision

The requested consumed-2026 numerical line was reached, but no strategy passed
the research gates. Diagnostic candidate `lev-v16d-1001c728344f3150` returned
21.47% in 2026 through August 12 at 9 bp with exact scheduled boundaries. It is
**not eligible for simulation observation**: its fixed v11 base was previously
selected using consumed 2026, 2022-2023 training return is negative, doubled
cost and delay miss the return gate, 2026 IR is below one, and the historical,
fold, neighborhood, and multiple-comparison checks fail.

No paper/live observation-pool record was changed. No broker or order route was
created or invoked.

## Evidence boundary

- Selection contract for new searches: 2022-2023 training, 2024 validation,
  and 2025 development OOS only.
- 2026 Q1 and April-August are consumed diagnostics. Repeated inspection means
  neither interval is independent OOS and neither can rank parameters.
- Alpaca IEX one-minute snapshots are content-addressed inputs for 2021 through
  August 12, 2026. Separately sourced 2018-2020 HF/Finnhub data is stress only.
- Execution is long-only, gross at most one, flat overnight, next scheduled
  five-minute open entry, scheduled open exit, and one cost charge per sleeve.
- Strict results require the scheduled boundary minute. One-minute tolerance is
  separately labelled and cannot override a strict failure.

## Falsification sequence

| Stage | Hypothesis | Cells / frontier | Seconds | Result |
|---|---|---:|---:|---|
| v13 exact | prior-day regime plus relative-strength/pullback rotation | 90,720 + 7,580 / 500 | 139.30 | 0 eligible; later superseded because training included 2021 |
| v13 tolerance | same, one-minute tolerance | 90,720 + 10,178 / 500 | 150.92 | 0 eligible; diagnostic only |
| v14 exact | fixed Ridge forecasts plus causal stop/trailing-risk controls | 23,400 / 100 | 71.45 | 0 standard-plus-2026 hits, 0 eligible |
| v14 tolerance | same, one-minute tolerance | 23,400 / 100 | 70.77 | 0 diagnostic hits, 0 eligible |
| fixed Ridge beam | explicit 2022-2023 fit, four windows | 95,335 / 19,044 | exploratory | 0 consumed-2026 >20% hard hits |
| expanding Ridge | annual expanding fit, never using 2026 labels | 74,847 / 2,338 | exploratory | 0 development primary hits |
| v15 exact | prior-five-day cross-sectional rotation | 280,612 / 1,000 | 203.91 | 0 consumed-2026 >20% hits, 0 eligible |
| v16 exact | fixed consumed v11 base plus development-ranked midday sleeve | 37,440 / 2,000 | 65.46 | 144 diagnostic hits; best 21.47%; 0 eligible |

V16 computes only 2022-2025 metrics during the 37,440-cell scan. It freezes the
2,000-member frontier before calculating any 2026 metric. This prevents the
midday overlay scan from using 2026 for retention, but it cannot undo the fixed
v11 base's prior consumption. The displayed v16 best is selected from the
frozen frontier by the user's consumed-2026 diagnostic condition and is
therefore diagnostic-selected, not a strategy recommendation.

## V16 diagnostic-best metrics

The added midday sleeve selects the strongest ETF in the full cross-section at
13:25 ET, requires current return at least 1.5%, relative return at least 0.6%,
five-day asset and SPY returns above -5%, and intraday SPY return above zero;
it enters at 13:30 and exits at 13:55. It is non-overlapping with the four fixed
base sleeves.

| Period | 9bp annualized | Total return | MDD | IR | Trades |
|---|---:|---:|---:|---:|---:|
| 2022-2023 training | -6.93% | -13.30% | 21.76% | -0.54 | 231 |
| 2024 | 22.16% | 22.16% | 9.98% | 1.32 | 86 |
| 2025 | 90.85% | 89.39% | 5.76% | 3.05 | 140 |
| 2024-2025 OOS | 52.49% | 131.36% | 9.98% | 2.24 | 226 |
| 2026 Q1 consumed | 54.89% | 11.17% | 9.31% | 1.34 | 46 |
| 2026 all consumed | 37.75% | **21.47%** | 19.34% | 0.97 | 115 |

| Scenario | 2024-2025 annualized | 2026 total | 2026 MDD | 2026 IR |
|---|---:|---:|---:|---:|
| 9bp exact | 52.49% | 21.47% | 19.34% | 0.97 |
| 18bp exact | 31.96% | 1.46% | 21.16% | 0.07 |
| 9bp + one 5-minute bar | 30.93% | 18.15% | 15.07% | 0.95 |

Starting in 2022, 2023, and 2024 produces 19.13%, 32.66%, and 52.49%
annualized return respectively; the associated MDDs are 25.46%, 25.46%, and
9.98%. Only three of five chronological development folds are positive. The
2018-2020 cross-source stress is -32.53% annualized with 59.00% MDD. No immediate
parameter neighbor passes the standard primary gate, and the 37,440-trial
Bonferroni p-value is 1.0.

## Gate disposition

| Gate | Result |
|---|---|
| Consumed 2026 total >20% | Pass, 21.47% |
| Consumed 2026 MDD <20% | Pass, 19.34% |
| Consumed 2026 IR >=1 | Fail, 0.97 |
| Standard 2024-2025 annualized >=50%, MDD <20%, IR >=1, positive training/years | Fail: training is negative |
| 18bp primary | Fail, 31.96% OOS annualized |
| One-bar-delay primary | Fail, 30.93% OOS annualized |
| Four of five positive folds | Fail, three of five |
| Parameter-neighborhood 70% primary | Fail, 0% |
| Historical positive with MDD <20% | Fail |
| Bonferroni 5% | Fail |
| Independent selection | Fail: fixed base and displayed diagnostic are consumed |

The honest action is to retain the candidate as a documented research-only
diagnostic and make no observation-pool change. The 20% numerical request is
satisfied, but the evidence does not support simulation or promotion. Any
future promotion case must be built on genuinely future sessions frozen before
inspection rather than further tuning against 2026.

## Reproduction

Run the exact-boundary prior-five-day search and diagnostic overlay from the
repository root:

```powershell
python scripts/search_full_universe_intraday_v15_prior5.py `
  --root G:\us-intraday-lab `
  --output G:\us-intraday-lab\artifacts\accelerated_research\full-universe-intraday-v15-prior5-exact.json

python scripts/evaluate_full_universe_intraday_v16_midday_overlay.py `
  --root G:\us-intraday-lab `
  --output G:\us-intraday-lab\artifacts\accelerated_research\full-universe-intraday-v16-midday-overlay-exact.json
```

Artifacts, databases, raw data, and archives remain untracked.
