# Alpaca SIP one-minute access supplement

This append-only supplement resolves the authority/access portion of the prior
`BLOCKED_FULL_MARKET_1MIN_SOURCE_MISSING` finding. It does not alter the earlier
inventory evidence: no full-market SIP one-minute snapshot exists locally yet.

On 2026-10-12, after the user explicitly instructed the research to continue,
the existing read-only Alpaca market-data credentials were tested with one
bounded request:

- provider/feed: Alpaca SIP;
- timeframe: one minute;
- symbol: AAPL only;
- requested interval: 2023-01-03 through 2023-01-04 UTC;
- adjustment: split;
- point-in-time `asof`: 2023-01-31;
- response: success, 811 provider rows;
- fields: symbol, timestamp, OHLC, volume, trade_count, VWAP;
- credential values were neither printed nor persisted.

This proves the current account can read historical SIP one-minute bars. It
does not prove full-market capacity, coverage, completeness, or economic
fitness. The next stage is a preregistered immutable acquisition implementation
and bounded capacity probe using the frozen 15,399-symbol asset snapshot.

No return outcome was opened, no strategy cell was evaluated, and all broker,
Paper, submit/cancel, routing, and monitoring-pool paths remain forbidden.
