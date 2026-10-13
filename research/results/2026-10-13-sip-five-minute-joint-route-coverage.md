# SIP five-minute joint execution-path coverage

Status: complete data-only diagnostic. No strategy return, candidate ranking,
broker path, or Paper state was touched.

The frozen source audit's 97.443652% figure counts individual required bars.
It is not joint availability of signal, entry, and exit for a five-to-ten-minute
trade. I checked the original audit's fixed decision bars 2, 5, 11, 17, and 23,
entry delays 1 and 2 bars, and only 1- or 2-bar holding periods. The exact
three timestamps must all be present for every point-in-time eligible
symbol-session. Missingness remained in the denominator; no zero, cash,
forward-fill, or post-outcome filtering was used.

The source is the existing immutable Alpaca SIP five-minute Parquet set. The
universe is the frozen validated `monthly_universe_sip_v2` dataset
`us-market-monthly-universe-sip-v2-3dc89bc9ab09e193372b2071`, not the older
v1 universe. The first exploratory pass accidentally used v1 and is discarded.
The corrected denominator is 4,520,552 eligible symbol-sessions per route,
exactly matching the frozen individual-clock audit's denominator. The
diagnostic spans all 96 months from 2018-04 through 2026-03, with the XNYS
calendar used to form each timestamp; 2021-2026 remain consumed.

Of 20 fixed routes, 19 fall below 95% aggregate joint coverage. The only
aggregate pass is decision bar 11, one-bar entry delay, one-bar hold:
4,297,713 / 4,520,552 = 95.0705%. It has monthly coverage below 95% in
37 of 96 months. Other routes range from 93.2872% to 94.9905%. This is a
descriptive data audit, not permission to select that one route after observing
coverage and read its returns. It does not establish any new economic edge or
waive fold, neighborhood, cost, delay, global-evidence, Bonferroni, or native
maxT gates. The prior 2,900-version bar-field contract still admitted zero.

Calculation: for each calendar month, select distinct uppercase eligible
symbols from v2 decisions; cross them with that month's XNYS sessions and the
20 fixed routes. Build UTC timestamps from the exchange's session open and
five-minute bar numbers. Join raw SIP Parquet bars to exact timestamps, then
left-join signal, entry, and exit to the complete expected grid. Aggregate
`count_if(all three present)` per route and count months below 95%. This was
read-only and did not create or overwrite source data.

Next: independently verify a genuinely different technical data contract and
its full-market, point-in-time, five-to-ten-minute joint path before any return
test. Existing local staging contains no historical exchange auction-imbalance
feed; no paid source was acquired. Do not rescue the failed coverage by
dropping names/months or reusing an exhausted bar/quote/trade family.
