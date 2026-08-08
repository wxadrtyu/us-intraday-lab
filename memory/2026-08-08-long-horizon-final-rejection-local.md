summary: The first AAPL/QQQ five-minute long-horizon campaign passed every pre-final check but failed its one-use 63-session blind final and was rejected.
stage: final-test
kpi_version: long-horizon-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - failed-experiment
  - strategy:late-dip-close-5m-v1-c6bc69016ace
  - status:rejected
next_step: Use previously untouched symbols or genuinely new forward sessions for the next sealed campaign; never retune and reopen the consumed AAPL/QQQ final.

Evidence: validation 1.5x-cost annualized return 12.31%, final combined OOS 1.5x-cost annualized return -0.87%, OOS IR -1.43, selection SHA-256 125ab94e00d8d26394ca2b73c625d74642a7106efdda474e0f77cbd8d04aba9f.
