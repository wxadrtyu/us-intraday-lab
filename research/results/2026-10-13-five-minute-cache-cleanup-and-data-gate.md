# Five-minute research cache cleanup and next data gate

Status: cache cleanup complete; no new strategy return was read or candidate admitted.

## Cache disposition

The 2026-10-13 inventory found 11.84 GiB in `research/cache`. The following
four DuckDB build-time working databases were moved to the Windows Recycle Bin
after verifying each corresponding Parquet context and frozen `COMPLETE` result
report existed. They were not source SIP bars, the point-in-time master, or the
immutable result reports.

| Working database | Bytes |
| --- | ---: |
| `v16309_v16408_trade_context.duckdb` | 285,749,248 |
| `v16509_v16608_volatility_surface.duckdb` | 3,663,736,832 |
| `v16609_v16708_ohlc_pressure.duckdb` | 3,903,074,304 |
| `v16709_v16808_liquidity_curve.duckdb` | 4,327,223,296 |

Total moved: 12,179,783,680 bytes (11.34 GiB). The cache now contains 503
files / 536,955,863 bytes (0.50 GiB). The four Parquet contexts remain.
Rebuilding the working databases from the retained source shards and code is
possible, but is not a reason to reopen these rejected research families.
Moving files to Recycle Bin is recoverable and does **not** yet reclaim their
physical disk allocation. No other cache directory or raw market-data shard was
deleted. The remaining cache requires item-by-item provenance classification;
its 0.50 GiB must not be described as wholly useful or wholly disposable.

## Five-minute strategy path

The frozen full-market SIP five-minute audit reports 714,742,115 rows and
97.443652% aggregate required-clock coverage. This does not establish that
the signal, entry, and exit bars for a particular five-to-ten-minute holding
path are jointly present. Such a path requires an exact, prespecified coverage
audit before returns are read. Missing bars cannot be filled, converted to cash,
or excluded after seeing outcomes.

The frozen bar-field information contract tested 2,900 versions using OHLC,
VWAP, volume, trade count, calendar, and cross-asset context and admitted zero
candidates. No renamed variant of that contract is a new hypothesis. The local
staging inventory contains SIP five-minute bars and exhausted quote/trade
families, but no historical exchange auction-imbalance feed. Exchange auction
imbalance is a genuinely different technical field to investigate: the NYSE
historical catalog lists order-imbalance data, and Nasdaq documents historical
NOII in TotalView-ITCH. These are venue-specific products, not proof of an
accessible full-market, point-in-time data path. No subscription, purchase, or
download was initiated. Until a permitted source can cover all point-in-time
eligible names and the exact five-to-ten-minute route, strategy-return work
remains gated.

All previously viewed 2021-2026 periods remain consumed, never independent
out-of-sample evidence. No trading, Paper, order routing, or monitoring-pool
state was changed.

Sources: `2026-09-15-alpaca-sip-5min-polygon-validated-audit.json`,
`2026-09-07-current-information-contract-exhaustion.json`, frozen v16309-v16808
results, [NYSE historical data](https://www.nyse.com/market-data/historical/),
and [Nasdaq historical NOII announcement](https://www.nasdaqtrader.com/TraderNews.aspx?id=dtn2009-059).
