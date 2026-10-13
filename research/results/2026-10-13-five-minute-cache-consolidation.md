# Five-minute technical data and cache consolidation

Status: inventory and prior-result audit only. No new strategy outcome was read, no
new strategy version was reserved, and no trading state was changed.

## One conclusion

The cache footprint is primarily reproducibility material from rejected research,
not a stock of qualified strategies. The existing Alpaca SIP five-minute source is
large enough and passed its frozen required-clock source audit, but the 2,900
versions evaluated under the same bar-field information contract admitted zero
candidates. A five-to-ten-minute strategy may use this source only after a
genuinely distinct economic mechanism and its complete entry/exit coverage are
preregistered; relabeling old laggard-recovery, VWAP, volatility, volume, or
cross-asset signals is not a new test.

## Read-only inventory on 2026-10-13

- `E:/us-intraday-lab-data/us-market/data`: 23.50 GiB / 69,048 files.
- SIP five-minute staging: 17.97 GiB / 30,493 files. Source audit recorded
  714,742,115 usable rows, zero duplicate rows, validated historical master,
  and 97.443652% required-clock coverage over the audited dataset. This is not
  a fresh five-to-ten-minute two-endpoint execution-path audit.
- IEX dynamic one-minute staging: 2.49 GiB / 2,138 files. It is not full-market
  SIP one-minute history.
- `research/cache`: 11.84 GiB / 507 files. Three DuckDB intermediate files
  total 11.08 GiB: liquidity curve 4,327,223,296 bytes; OHLC pressure
  3,903,074,304 bytes; volatility surface 3,663,736,832 bytes. Their frozen
  100-version result batches each admitted zero candidates. The remaining
  cache is mostly other failed-research intermediates; physical database
  integrity was not revalidated by this inventory.
- Frozen SIP one-minute 2023-12-29 pilot: 0.03 GiB / 309 files. Its 78.55%
  eligible symbol-minute and 39.64% fixed execution-path coverage remain a
  rejection of that one-minute path, not a verdict on the five-minute source.
- About 109 MiB of old DOL/EIA event cache directories still exist inside
  `research/cache`. They are prohibited for future research and were not
  deleted in this read-only audit; this residual must not be described as
  cleaned up.

## Novelty check before another five-minute backtest

The frozen information-contract audit covers all existing OHLC, VWAP, volume,
trade-count, calendar, and cross-asset bar families and reports 2,900 versions
with zero admissions. The previously tested v9305-v9404 campaign explicitly
included long-only contemporaneous laggard recovery, while v17009-v17108
tested stock-to-stock leader propagation. A proposed rolling-peer residual
reversion is therefore not yet proven economically distinct from prior
laggard-recovery work. Do not read its returns or create a renamed version
until a narrower, defensible distinction and a five-to-ten-minute execution
coverage protocol are frozen. All already viewed 2021-2026 data are consumed;
no independent out-of-sample claim is available.

Evidence: `2026-09-15-alpaca-sip-5min-polygon-validated-audit.json`,
`2026-09-07-current-information-contract-exhaustion.json`, and the frozen
v16509-v16808, v9305-v9404, and v17009-v17108 result reports.
