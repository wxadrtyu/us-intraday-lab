# US market SIP fixed-one-second trade feature audit

- Status: `COMPLETE`
- Event rows: 799,799 / 799,799
- Trade availability: 569,396 (71.1924%)
- Explicit no-trade rows: 230,403
- Canonical shards: 2,120 / 2,120
- Noncanonical one-day probe shards excluded: 50
- Duplicate keys: 0
- Missing keys: 0
- Contract failures: 0
- Causality: fixed one-second request window and strict pre-cutoff filter are frozen in acquisition code; raw trade timestamps are not retained in the aggregate cache.
