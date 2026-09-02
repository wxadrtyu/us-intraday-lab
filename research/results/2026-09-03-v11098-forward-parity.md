# v11098 forward route parity

The independently assembled branch-aware forward plan matched the frozen
research stream across all 1,407 Alpaca development/diagnostic sessions with
zero daily-return error and zero active-session mismatch.

The audit observed 92 bar-2-resolved transfer-route sessions and 1,315
modern/fallback sessions whose late positions were held until the bar-23 route
was resolved.  Early fill starts at bar 11 only on the resolved transfer
branch; all other fill starts at bar 24 or later.  The route-clock causality
check passed.

The remaining fail-closed item is the adapter from the runner's live Alpaca
IEX DataFrame into the frozen factor and exposure inputs.  v11098 is not yet in
the Paper allocation.
