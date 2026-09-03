# v12409-v12508 train-fixed beta-orthogonal alpha

The preregistered batch completed 100 versions and 1,000 parameter cells in
20.19 seconds. No candidate passed every pre-native-null gate; no native null
or Paper-pool change was allowed.

The best candidate, `lev-v12437-18f05a3aa3bff08d`, used market betas fixed
from 2022-2023 to predict beta-orthogonal TQQQ/SOXL residual returns while
retaining long-only execution. Standard 2024-2025 performance reached 43.93%
annualized, 15.14% MDD, and IR 1.11. The 18bp scenario fell to 35.16% and IR
0.89; the delayed scenario reached 43.83% and IR 1.20.

The mechanism failed every primary return gate, every historical gate, the
70% neighborhood gate, and the cumulative Bonferroni gate. Historical
standard performance was -10.58% annualized with 39.87% MDD, while consumed
2026Q1 and all-2026 returns were -2.55% and -12.49%. Its neighborhood share
was zero, z was 0.840, and cumulative Bonferroni p was 1.0. This is a broad
regime reversal rather than a promising local miss, so the next batch starts
from v12509 with a different economic mechanism.
