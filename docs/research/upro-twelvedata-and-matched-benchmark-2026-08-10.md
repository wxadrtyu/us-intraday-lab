# UPRO / Twelve Data research and matched-benchmark contract

## Decision

Do not promote a new strategy to `paper_shadow`. The TQQQ/UPRO relative-laggard
families, their repeated-entry extension, the asymmetric crash/laggard ensemble,
and the 37-stock intraday cross-sectional families all failed unchanged research
floors before sealed-final use.

## Immutable TQQQ/UPRO data

- Dataset: `hf-finnhub-5min-4612a96827c4daa416e359fe51cb8c8f`
- Scope: TQQQ and UPRO, January 2022 through December 2025
- Rows: 130,728 five-minute bars across approximately 838 sessions
- The UPRO source after April 2024 can omit isolated one-minute observations.
  Aggregation accepts a session only when all 78 five-minute buckets are present;
  it never forward-fills price or volume and timestamps each bucket at its
  canonical start with availability at bucket end.

## Formal TQQQ/UPRO results

The first frozen relative-laggard proposal evaluated 50 variants. Only three
passed training floors, below the required four, so development validation and
final were not opened.

The second frozen proposal tested later confirmation and at most two entries per
session. Seven of 50 variants passed the broad training floor; the four highest
ranked training variants were evaluated on development validation. None passed
the validation floor and the campaign stopped with
`fewer than four variants passed validation floors`.

| Evidence | Best training | Best development |
|---|---:|---:|
| Annualized return after 1.5x costs | 9.43% | 1.44% |
| Maximum drawdown | 7.13% | 3.03% |
| Profit factor | 1.48 | 1.17 |
| Trades | 95 | 25 |

The best development result also failed symbol concentration because almost all
positive PnL came from TQQQ. The repeated-entry neighbors returned -5.77%
annualized on development, had 9.00% drawdown, and profit factor 0.87. No final
TQQQ/UPRO interval was read.

## Development-only diagnostics

The TQQQ crash-rebound plus UPRO laggard ensemble also failed. Its best balanced
cell returned 6.09% on training and 7.13% on development, with 11.77% development
drawdown and 88% maximum positive-symbol concentration.

The external Twelve Data research files remain outside Git on `E:`. Only
`train.parquet` (2020-2023) and `val.parquet` (2024) were used. The 2025 test file
was not downloaded or read. A scan of 88,080 price, VWAP, cumulative-volume, and
opening-range cross-sectional variants produced zero passing cells. The best
balanced cell returned 6.79% on training and 7.98% on development with 10.78%
drawdown. Higher 2024-only results had negligible earlier-period returns and
were rejected as regime-specific.

## Matched benchmark contract for future campaigns

The former information-ratio benchmark held one ETF close-to-close every day,
including overnight and flat-strategy periods. That exposure does not match a
sparse intraday strategy and can reverse the sign of active returns.

Future finalizations now construct the benchmark from the strategy's actual base
trades:

- use the pair's designated benchmark ETF;
- enter and exit at the same observable timestamps as each strategy trade;
- use the strategy trade's cash notional, allowing an exact exposure match;
- use the same session-by-session capital evolution;
- use the benchmark close only for forced end-of-session exits and the executable
  bar open for other fills.

The IR threshold remains 0.50. This contract change applies prospectively and
does not revise or overturn already consumed final-test decisions.

## Reproducibility

- TQQQ/UPRO v1 experiment: `lh-8cfe096b6313efb7c3ed1138f9544ead`
- TQQQ/UPRO v2 experiment: `lh-c3ef4db45ebe831aaf063ece8536bb1e`
- Twelve Data files: `E:/us-intraday-lab-data/twelvedata-http/bars_1min/`
- All hard return, drawdown, profit-factor, trade-count, stability, null,
  concentration, and final-isolation safeguards remain unchanged.
