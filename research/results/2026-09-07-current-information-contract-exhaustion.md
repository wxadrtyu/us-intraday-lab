# Current information-contract exhaustion audit

- Status: COMPLETE; 2,900 strategy versions reviewed; admitted candidates: 0.
- Permitted raw columns: symbol, timestamp, open, high, low, close, volume, trade_count, vwap, session_date, provider, feed, ingested_at.
- Every economically meaningful bar field has already been represented by endpoint, path, volatility, VWAP, volume, trade-count, calendar, and cross-asset families.
- Corporate actions and assets are current retrospective snapshots, not safe historical vintages.
- 2026Q1 rows loaded for this audit: 0; 2026-04+ rows loaded: 0.
- Decision: NO_NEW_CAUSAL_FIELD_WITHIN_CURRENT_CONTRACT.
- Required next step: authorize and immutably acquire a new timestamped data contract, preferably historical quotes/NBBO, trade prints, auction imbalance, or point-in-time events.
- No Paper/broker/order state was touched.
