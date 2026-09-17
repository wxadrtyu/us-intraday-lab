# Federal Reserve macro-regime training feasibility plan

1. Add tests and a read-only acquisition parser for the six exact FRED training-window CSV requests; persist only validated training rows with hashes and missingness.
2. Build lagged curve, yield-change, inflation-change, and dollar-change features joined only to the immediately prior equity session.
3. Add a frozen 400-cell diagnostic using the established event-return, cost, delay, calendar-year, IR, and drawdown accounting.
4. Acquire and freeze the external training snapshot and causal feature hash, then run all 400 cells without loading development or consumed dates.
5. Freeze JSON/Markdown and external Parquet evidence. If fewer than two families retain cells, create no version and move on.
6. Run focused, data/research, lint, and full-suite verification; record exact pre-existing failures and write the mandatory local fallback memory.
