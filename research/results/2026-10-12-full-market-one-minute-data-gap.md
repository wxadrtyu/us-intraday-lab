# Full-market one-minute data inventory gate

## Decision

`BLOCKED_FULL_MARKET_1MIN_SOURCE_MISSING`

The repository does not contain a full-market one-minute or finer technical
dataset capable of supporting a causal 5-10 minute strategy evaluation. No
return outcome was opened and no strategy cell was evaluated.

## Frozen inventory evidence

- Audited roots: `G:\us-intraday-lab` and `E:\us-intraday-lab-data`.
- One-minute datasets found: 18 immutable Alpaca IEX datasets.
- Manifest inventory SHA-256: `e3857929b7538b43886a7bbe6eda5aac6e6f0367d3a832645ee636b151ce4cfc`.
- Per-dataset symbol count: 16 or 21; union: 36 symbols.
- Total stored rows: 18,473,449.
- Time span across separate snapshots: 2020-07-27 through 2026-08-28.
- Every manifest declares `feed=iex` and `quality_complete=false`.
- No Alpaca SIP one-minute or finer dataset was found in either audited root.
- The only full-market point-in-time intraday catalog is the already consumed
  SIP five-minute family; its 2,900 OHLCV/VWAP/volume/trade-count and
  quote/trade technical versions are frozen and cannot be renamed or reused.

The existing 16/21-symbol IEX scopes and their 36-symbol union are not the
point-in-time full market. They cannot be used to satisfy the user's full-market
requirement, and missing symbols cannot be treated as cash, zero returns, or
post-outcome exclusions.

## Consequence

Research stops at the source-coverage gate. A valid next step requires a new,
immutable, point-in-time full-market SIP one-minute or finer acquisition with
complete session/path evidence. Acquiring that materially larger licensed
dataset requires new data-source authority or credentials. Daily data, five-
minute family relabeling, fixed ETF scopes, and incomplete IEX samples are not
fallbacks.

Paper activation, broker access, submit/cancel, order routing, and monitoring-
pool changes remain forbidden.
