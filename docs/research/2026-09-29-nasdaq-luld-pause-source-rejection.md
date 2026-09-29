# Nasdaq LULD trading-pause source rejection

Decision: **ABANDON_NASDAQ_LULD_HISTORY_GATE**. The proposed 2021-2023 Nasdaq Trader single-stock Limit Up-Limit Down pause line is frozen at the historical-source gate, before event counting, symbol matching, event-cube access, or any post-pause return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Fixed homogeneous family

The contemplated family was Nasdaq halt reason code `LUDP` (`Volatility Trading Pause`) only. `LUDS` (`Volatility Trading Pause - Straddle Condition`) is a separately identified reason and was not pooled. News-pending, regulatory, operational, IPO, corporate-action, market-wide, resumption, delisting, and other halt events may not be added for volume.

## Official source audit

Nasdaq's official halt-code page defines `LUDP` and the published fields, including Halt Date, Halt Time, Issue Symbol, Reason Code, and resumption timestamps. Nasdaq's official LULD FAQ says the Nasdaq Trader page reflects pauses and the SIP disseminates the public action and reason code in real time. The official RSS documentation says its free halt feed supplies the same information and is updated once per minute. These sources support contemporaneous public observability of a pause.

They do not support a reproducible 2021-2023 corpus in September 2026. The official Trading Halt Search explicitly says that halt history for only the last year is displayed. The official Trading Halt History page exposes recent daily links rather than a complete 2021-2023 archive. The RSS documentation does not provide an immutable historical daily-file inventory, object hashes, a stable pause identifier, or a complete correction/cancellation/resumption version manifest. A current search result, current RSS representation, date-shaped URL, HTTP header, search-engine cache, or third-party mirror cannot establish the bytes and record state first published during 2021-2023.

Official sources:

- https://www.nasdaqtrader.com/trader.aspx?id=tradinghaltsearch
- https://nasdaqtrader.com/trader.aspx?id=TradingHaltHistory
- https://classic.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS
- https://beta.nasdaqtrader.com/Trader.aspx?id=TradeHaltCodes
- https://nasdaqtrader.com/content/MarketRegulation/LULD_FAQ.pdf

Because the complete official historical universe and its version state cannot be proven, event volume and point-in-time symbol coverage were not measured. No current or guessed historical symbol, share-class folding, successor/predecessor relation, subsidiary, parent, brand, former name, abbreviation, fuzzy match, or manual alias may be used to reopen the line.

Final state: `historical_source_gate_passed=false`, `preregistered=false`, `halt_corpus_persisted=false`, `volume_counted=false`, `point_in_time_symbol_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_pause_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
