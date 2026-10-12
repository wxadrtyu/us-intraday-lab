# Immutable full-market SIP one-minute source design

## Decision

The user authorized continued 5-10 minute intraday research. The existing
Alpaca market-data account passed a bounded historical SIP one-minute request,
and the 100-symbol capacity probe returned 10,162 regular-session rows. The
one-minute source is a prerequisite for evaluating causal intraday signals and
fills. It is not itself a strategy or an independent out-of-sample result.

Three approaches were considered: reuse the 36-symbol IEX snapshots, resample
the already exhausted SIP five-minute source, or acquire native SIP one-minute
bars. The first lacks point-in-time full-market coverage; the second lacks
within-bar paths and repeats an exhausted information contract. Native SIP
one-minute bars are selected.

## Scope and immutable identity

Use the frozen 15,399-symbol candidate asset snapshot
`alpaca-us-equity-assets-4cf36da00fead42b3b669620` and symbol-list SHA-256
`03af744e8cd30ef307251e9484ac08ec6d79fa4c8a4607a768cf45ba672d61c9`.
Point-in-time monthly eligibility is the separately frozen SIP-v2 universe
whose content SHA-256 is
`3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.
Candidate assets define an acquisition upper bound; they do not confer
eligibility or justify a full-market claim by themselves.

The first source window is 2021-01-01 through 2023-12-31, all previously
consumed. Requests use `feed=sip`, `timeframe=1Min`, `adjustment=split`,
`asof=calendar-month-end-or-window-end`, and sorted deterministic batches of
100 symbols. Partition keys are month, batch index, and the SHA-256 of the
complete request identity. Data live under a new `alpaca_sip_1min_v1` namespace
on E:, never in the Git repository. The request grid and candidate hash are
frozen in an acquisition contract before downloading.

## Acquisition and validation

Only Alpaca's historical market-data client is imported. The tool cannot
place, submit, cancel, or route orders. Each shard stores regular-session
OHLCV, trade count, VWAP, provider/feed/asof, source-row count, excluded
out-of-session count, requested symbols, provider-rejected symbols, exact
request identity, retrieval time, quality diagnostics, and Parquet SHA-256.
Empty provider responses are not silently accepted. Explicit provider invalid
symbol errors are recorded and those symbols removed only from the attempted
request, not from the frozen candidate or point-in-time universe.

Each shard is written to temporary files and atomically renamed. Resume
verifies the contract, manifest, request hash, content hash, row count,
quality, and all previously committed shards before reuse. A partial file or
identity mismatch stops the run. Duplicate symbol-minute keys, unexpected
symbols, off-grid timestamps, nonpositive prices, malformed OHLC, negative
volume/trade count, invalid VWAP, and nonfinite required values stop the
affected shard. Missing symbol-minutes remain missing; no fill, cash, or zero
return is inserted.

Run a bounded 100-symbol, one-session immutable pilot first. Record actual
latency, bytes, provider rejections, and low-liquidity sparse rows. Estimate
full-window completion and disk use with a conservative safety factor before
launching bulk acquisition. Bulk work advances via finite shard-index ranges
and atomic checkpoints, so each scheduled run can stop cleanly.

## Coverage and research boundary

After acquisition, audit every session and one-minute decision/entry/exit
clock against the frozen monthly point-in-time eligible symbols. Publish
returned, missing, rejected, duplicate, and path-completeness counts by month,
session, and liquidity stratum. Define the permissible strategy clocks only
after this independent data audit passes the existing coverage floor. No
outcome or signal ranking is opened during acquisition and coverage.

All 2021-2026 observations are consumed evidence. A later surviving training
candidate can only propose new prospective shadow validation. The existing
return, drawdown, IR, cost, delay, fold, neighborhood, Bonferroni, and two
native maxT gates remain unchanged. Single-trade holding time is at most ten
minutes, with five minutes preferred. Daily, overnight, issuer-event, broker,
Paper, order-routing, and monitoring-pool paths are excluded.
