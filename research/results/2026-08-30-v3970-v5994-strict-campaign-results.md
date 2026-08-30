# v3970–v5994 strict multifactor campaign results

## Decision

Completed 2,025 independently numbered versions across 12 preregistered
campaigns. There were 53,050 newly evaluated cells/frontiers within these
campaigns and 2,425 retained decision records. The final cumulative comparison
count is 254,855. Strict pre-factory-null passes: **0**. Native factory nulls:
**0**, because no candidate reached their preregistered boundary. Admissions:
**0**.

No Paper pool, broker, order, submit or cancel code/state was changed. All
strategies remain long-only, maximum concurrent gross 1, and flat overnight.

## Campaign decisions

| Versions | Versions | Evaluated cells | Pre-null passes | Closest record | 2024–25 9bp annualized | IR | Failed gates |
|---|---:|---:|---:|---|---:|---:|---|
| v3970–v4069 | 100 | 100 | 0 | lev-v4043-439875adffb2dce7 | 36.4% | 0.93 | consumed_2026q1_above_5pct, cost_18bp_primary, cumulative_bonferroni_5pct, delay_5min_primary, historical_15pct_mdd_below_20pct_all_scenarios, parameter_neighborhood_70pct_primary, standard_primary |
| v4070–v4169 | 100 | 50000 | 0 | lev-v4101-6b4a8349f205f365 | 73.5% | 1.48 | cumulative_bonferroni_5pct, historical_15pct_mdd_below_20pct_all_scenarios, parameter_neighborhood_70pct_primary |
| v4170–v4269 | 100 | 1000 | 0 | lev-v4257-5511a435fd6c77a0 | 63.7% | 1.29 | cumulative_bonferroni_5pct |
| v4270–v4369 | 100 | 100 | 0 | lev-v4280-0957f91c2251f58e | 65.1% | 1.50 | consumed_2026q1_above_5pct, cumulative_bonferroni_5pct, historical_15pct_mdd_below_20pct_all_scenarios |
| v4370–v4469 | 100 | 100 | 0 | lev-v4423-5298677326af2b2b | 70.9% | 1.76 | cumulative_bonferroni_5pct |
| v4470–v4569 | 100 | 100 | 0 | lev-v4513-0d708bbd918157bb | 76.2% | 1.87 | cumulative_bonferroni_5pct |
| v4570–v4669 | 100 | 100 | 0 | lev-v4630-a7a07c2fbad73dbb | 51.6% | 1.54 | cost_18bp_primary, cumulative_bonferroni_5pct, delay_5min_primary, historical_15pct_mdd_below_20pct_all_scenarios, parameter_neighborhood_70pct_primary |
| v4670–v5669 | 1000 | 1000 | 0 | lev-v4956-4e75209af7e09dac | 29.3% | 0.81 | cost_18bp_primary, cumulative_bonferroni_5pct, delay_5min_primary, historical_15pct_mdd_below_20pct_all_scenarios, parameter_neighborhood_70pct_primary, standard_primary |
| v5670–v5769 | 100 | 100 | 0 | lev-v5760-e7557881b2cf83f3 | 69.2% | 1.74 | cumulative_bonferroni_5pct |
| v5770–v5869 | 100 | 100 | 0 | lev-v5863-62b7dbb55ce7e78d | 62.6% | 1.60 | cumulative_bonferroni_5pct |
| v5870–v5969 | 100 | 100 | 0 | lev-v5881-70a999525a732165 | 63.9% | 1.64 | consumed_2026_total_above_5pct, cumulative_bonferroni_5pct, parameter_neighborhood_70pct_primary |
| v5970–v5994 | 25 | 250 | 0 | lev-v5980-36034842055995ca | 22.8% | 0.90 | consumed_2026q1_above_5pct, cost_18bp_primary, cumulative_bonferroni_5pct, delay_5min_primary, historical_15pct_mdd_below_20pct_all_scenarios, parameter_neighborhood_70pct_primary, standard_primary |

The strongest milestone was `lev-v4513-0d708bbd918157bb`: 2024–2025
standard annualized 76.25%, MDD 12.68%, IR 1.875, 2026Q1 total 10.0%, and
all-2026 total 9.9%. It passed every economic, scenario, history, fold,
start-date and neighborhood gate, but its cumulative Bonferroni p remained
1.0. It is rejected, not a usable strategy or an exception.

The new v5970–v5994 experiment combined four non-overlapping causal intraday
slots while enforcing gross <= 1 in each slot. It performed materially worse:
its closest record had 22.78% annualized, 22.99% MDD and 0.896 IR; every
version failed the standard, 18bp, delay, historical, Q1, neighborhood and
global gates. This mechanism should not be extended by parameter tuning.

## Data and selection boundaries

All fitting, factor signs, thresholds, model coefficients, parent ranking and
cell ranking used only 2022–2025 development data. Historical 2018–2020 and
consumed 2026 diagnostics were attached after each frozen choice and did not
feed selection. No other task's blind data was read.

The 9bp, 18bp and extra five-minute delay scenarios were evaluated together.
The latest campaign additionally requires start-date positivity in every
scenario. Outputs are immutable atomic JSON under
`E:/us-intraday-lab-data/research/v3970-v5969`; their hashes and per-campaign
failure counts are in the machine summary.

## Runtime and verification

The existing eleven preregistered campaigns were resumed from v3970 without
rerunning any complete output. v4070–v4169 was the largest scan: 50,000 cells
in 308.66 seconds. The v5970–v5994 four-slot campaign evaluated 250 cells in
29.92 seconds. Targeted preregistration tests passed (21 total across the
phase, including 2/2 for v5970), and Ruff passed for the new code.

Next unused strategy version is v5995.
