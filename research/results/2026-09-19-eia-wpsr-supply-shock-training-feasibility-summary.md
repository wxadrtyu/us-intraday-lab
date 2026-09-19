# EIA WPSR physical-inventory training feasibility: coverage rejection

The official dated EIA archive yielded 154/154 page-linked Table 4 CSVs for 2021-2023 (52/51/51 by year). All raw source, CSV, and derived hashes verified. This remains a **527-symbol coverage-limited training sample, not the full market**.

The frozen coverage gate failed: only **77** release-availability sessions had at least 150 eligible positive historical XLE-beta symbols, versus the preregistered **100** required. The other measured floors passed: 263 unique positive-beta symbols, 20,084 eligible symbol-release pairs versus 20,000, complete release-year coverage, and all five family activation floors. Of 81,004 symbol-release exposure rows, 51,737 lacked 60 prior paired bar-5 observations and 9,183 had nonpositive beta. These losses were preserved, not imputed or reclassified.

Decision: `ABANDON_EIA_WPSR_COVERAGE_GATE`. The diagnostic stopped before post-availability outcome loading: **zero of 400** return cells ran. No parameter, threshold, exposure mapping, or signal family will be tuned on this line. There is no strategy candidate, version, Paper action, broker path, or observation-pool change. The external raw and derived snapshot remains retained under `E:\us-intraday-lab-data\us-market\research\cache\eia_wpsr_training_v1`; exact source, CSV, feature and cube hashes are in the adjacent JSON summary.

Verification: the terminal JSON was checked against the live frozen gate and manifest, and the 26 focused EIA tests passed. Full repository pytest finished with 1,405 passed, 16 pre-existing unrelated research campaign-definition failures, and two warnings; those failures are not EIA regressions and were not changed for this line.
