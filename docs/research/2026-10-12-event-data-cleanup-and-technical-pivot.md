# Event-data cleanup and technical-factor pivot

Date: 2026-10-12

## Decision

The news, regulatory, and issuer-event research line is closed. Its source
caches, derived feature tables, and feasibility cell tables were deleted. The
shared market-data foundation, the frozen 2021-2023 execution cube, source code,
Git history, and frozen rejection evidence remain intact.

The deletion covered 34 exact targets, 6,583 files, and 3,012,830,631 bytes.
The removed data included Alpaca news metadata, FAA/FDA/ITA/SEC source-audit
caches, USPTO event snapshots, SEC event feature tables, and their external
training-feasibility outputs. Recovery requires reacquisition or recomputation;
there is no local archive.

Quote, trade, OHLCV, volatility-regime, positioning, macro-regime, FINRA, listing,
calendar, and frozen-universe data were not deleted. In particular,
`v14309_v14408_events.parquet` remains because it is a price-derived execution
cube used by non-event strategies, not a news corpus.

## Replacement research source

The replacement line uses technical indicators derived only from completed daily
SIP bars and executes against the existing intraday cube. It does not use news,
filings, agency releases, or issuer events.

- Daily source: `alpaca_sip_1day_v2`
- Daily source tree SHA-256:
  `00cf180747d9174e104dbcb84b7c5911d4e89cd1c6fec9696d3200e524c4ed6c`
- Daily source files: 1,584 parquet plus 1,584 JSON manifests
- Daily source bytes: 596,431,311
- Execution cube SHA-256:
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`
- Training scope: 2021-2023, 527-symbol coverage-limited sample; not the full
  US market

The daily source contains 453,996 rows for the frozen symbols from 2020-07-01
through 2023-12-29, with zero duplicate symbol-session keys, zero missing OHLCV,
zero non-positive prices, and zero negative volume. Strictly lagged 60-session
history is available for 133,931 execution symbol-sessions across 526 symbols
and all 753 training sessions. Forty-four execution pairs have no earlier daily
bar and 46 have fewer than 60 earlier bars; they remain explicit missingness.

## Safety boundary

No development or consumed-period data was read or ranked during cleanup and
source coverage. No Paper pool, broker path, order route, or monitoring state was
changed.
