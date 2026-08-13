# Full-universe intraday v11 result

## Outcome

The search produced a long-only, non-overlapping candidate that clears the
requested numerical thresholds under the declared 9 bp round-trip cost model.
It is retained as a research candidate, not promoted to the paper observation
pool, because both the doubled-cost and one-additional-bar execution stresses
fail materially.

| Interval / scenario | Return measure | MDD | IR | Result |
|---|---:|---:|---:|---|
| 2024-2025 OOS, 9 bp | 51.49% annualized | 7.67% | 2.45 | requested gate pass |
| 2026 through Aug 12, 9 bp | 20.85% total | 17.68% | 1.01 | requested gate pass |
| 2024-2025 OOS, 18 bp | 35.45% annualized | 8.25% | 1.69 | stress fail |
| 2026 through Aug 12, 18 bp | 5.22% total | 19.31% | 0.32 | stress fail |
| 2024-2025 OOS, 5-minute delay at 9 bp | 30.29% annualized | 10.83% | 1.58 | stress fail |
| 2026 through Aug 12, 5-minute delay at 9 bp | 13.84% total | 15.52% | 0.81 | stress fail |

Candidate: `lev-v11-4e846213afaa35db`.

## Stability disclosures

- Train 2021-2023 annualized return was 13.31%, MDD 13.12%, IR 0.93.
- Calendar 2024 returned 23.94%; calendar 2025 returned 85.62%. The aggregate
  OOS result is therefore dominated by 2025 and is not year-uniform.
- The 2026 interval was deliberately consumed during this search at the user's
  request. It is target validation, not a fresh blind result and cannot be used
  again as independent evidence.
- Of the first 100 retained parameter hits, only 11 distinct performance
  outcomes existed. Broad threshold neighborhoods did pass, but many parameter
  records were signal-equivalent because some thresholds did not bind.
- A causal trailing-return overlay did not rescue robustness. Its best baseline
  result narrowly missed the OOS target at 49.5%, while its best 18 bp result
  reached only 33.6% OOS annualized and 9.9% total in 2026.
- Alpaca IEX bars are sparse for some leveraged products. Every executed sleeve
  required at least four one-minute observations in its decision, entry, and
  exit five-minute buckets; missing data was never forward-filled.

## Search and architecture

The vectorized search read seven immutable Alpaca IEX snapshots covering 1,407
sessions from 2021-01-04 through 2026-08-12. It scanned 76,752 sleeve variants,
98,876 portfolio combinations, and 2,416 compatible gap boosters. The selected
four sleeves trade sequentially, so maximum gross exposure remains 1.0.

The strategy combines cross-sectional relative strength after the open and in
the morning with cross-sectional pullback/rebound entries in the afternoon and
near the close. Entries use the next five-minute bar open and costs are charged
independently to every active sleeve.

## Lifecycle decision

Lifecycle is `research_candidate_target_hit_stress_failed_not_for_paper`.
No broker was constructed, no order route was touched, and no paper/live state
was changed. A genuinely new forward interval plus improved cost and latency
stability are required before paper-shadow admission.
