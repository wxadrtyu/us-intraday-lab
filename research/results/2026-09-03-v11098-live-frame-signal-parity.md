# v11098 live-frame and signal parity

The frozen v11098 adapter now reproduces both the raw Alpaca-bar feature views
and the complete branch-causal research return stream.

- Live DataFrame feature parity: 80 recent sessions, 7 decision bars, 455
  factor/view comparisons, maximum absolute error
  `6.661338147750939e-16`, and zero finite-mask mismatches.
- Full signal replay: 1,347 sessions after the required 60-session warm-up,
  2,345 emitted legs, maximum daily-return error
  `6.938893903907228e-18`, zero active-session mismatches, and zero gross-limit
  violations.
- Route diagnostics: zero outer-gate, modern-state, transfer-gate, fill-gate,
  parent-stream, or frozen-route mismatches.

The parity implementation preserves two distinct frozen feature views over the
same bars: the v34 parent/opening/transfer view and the sector-flow outer-gate
view. Treating every model as if it used the later sector-flow cube caused a
measurable mismatch and was rejected during validation.

No Paper allocation or runner was changed. The candidate remains fail-closed
as `LIVE_FRAME_SIGNAL_PARITY_PASSED_RUNNER_WIRING_PENDING` until the adapter is
wired into the managed runner and separately authorized for allocation.
