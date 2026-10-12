# Bounded Alpaca SIP one-minute capacity pilot

The existing read-only Alpaca historical-bars account returned SIP one-minute
bars for one representative session. This pilot did not save source bars or
read strategy outcomes. The next acquisition stage must save immutable raw
shards and repeat the audit before any backtest.

## Frozen request

- Universe: the existing frozen 15,399-symbol candidate asset snapshot
  `alpaca-us-equity-assets-4cf36da00fead42b3b669620`.
- Pilot: 100 symbols, ten hash-ordered symbols from each prior-day SIP daily
  dollar-volume decile on 2025-12-30. The newline-joined, sorted symbol list
  has SHA-256 `1221aae690a87377656aa0c7a027be49272c8e4b98852815879823c4910429f6`.
- Alpaca `feed=sip`, `timeframe=1Min`, `adjustment=split`,
  `asof=2025-12-30`, request interval `2025-12-30T00:00:00Z` through
  `2025-12-31T00:00:00Z`.
- Causal session filter: 2025-12-30, 09:30 inclusive to 16:00 exclusive,
  America/New_York.

## Observed result

- API response: success in 4.202 seconds.
- Provider rows: 10,994; regular-session rows: 10,162.
- Symbols with at least one regular-session row: 70 of 100. The other 30
  remain explicit no-row symbols, not zero-return observations.
- In-memory Zstandard Parquet serialization: 239,168 bytes. These bytes were
  not retained as an immutable shard; the SHA-256 of that transient byte
  sequence was `9cbda8bfa3269f947edfbafb64dd3805d84b12e68a47bb4af971330a9eb80032`.
- Source fields: symbol, timestamp, OHLC, volume, trade_count, VWAP.

Scaling the observed row and byte density to all 15,399 candidates across
753 XNYS sessions in 2021-2023 yields approximately 1,178,329,324 rows and
25.8 GiB of compressed Parquet. Naive sequential request time is roughly
5.6 days at this one-request rate. These are planning estimates only; API
latency, sparse periods, rejected historical symbols, partition overhead,
retries, and validation will change the actual result. E: had about 1,385 GiB
free at the probe, so disk size alone is not the limiting gate.

Before bulk acquisition, freeze a distinct one-minute source namespace,
monthly and deterministic symbol-batch request identities, point-in-time
`asof`, raw missingness and provider rejections, atomic shard manifests and
hash verification. Start with a bounded immutable pilot and validate exact
coverage against the frozen monthly universe. Do not treat 2021-2026 as
independent out-of-sample data.
