# v1941: requested August 27/28 replay

The user's "run yesterday and today too" request was handled at Beijing 2026-08-29 00:49.
The intended US sessions are August 27 (finished) and August 28 (still open). August 29 is
Saturday, not an XNYS session. v1254 Paper already ran both sessions independently.

Neither date had v1941 live-shadow records and both decision windows had passed. Therefore these
outputs are explicitly `RETROSPECTIVE_DIAGNOSTIC_NOT_LIVE_SHADOW`, `prospective=false`,
`actual_orders=0`, `order_route=FORBIDDEN`. They are not backfilled into the live shadow database,
do not count as prospective observations, and cannot support a new OOS/admission claim.

## Frozen implementation and data boundary

- Reuse frozen v1941 factors/threshold/scaling and existing v1254 pure signal functions. No refit,
  ranking, new strategy version, allocation change or order logic change.
- Reuse hash-verified prior IEX context from the original August 26 run, then retrieve non-overlapping
  subsequent IEX sessions. No provider splicing, gap fill, or credential recovery.
- Every reconstructed decision sees only its historical decision cutoff; data after the observation
  timestamp is also excluded. This is causal historical evaluation, not evidence of contemporaneous
  availability or a real signal-receipt timestamp.
- Compare 9bp, 18bp and one extra 5-minute entry-bar delay. The receipt-based scenario is explicitly
  unavailable: no live receipt time was recorded on these dates.
- Missing exact entry/exit prices and future exit clocks yield incomplete/null results, not zero
  profit. Every batch gets a unique directory; initial/final snapshots and reports are separate files.
- Preserve all existing failure labels (inherited v45 null, incomplete overlay null, global null fail).

## Initial outputs, Beijing 2026-08-29 approximately 00:54

| US session | v1941 budget | 9bp return | 18bp return | +5-minute delay/9bp |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-27 | 90% | -0.820820% | -0.901820% | -1.144306% |
| 2026-08-28 | 90% | Pending exits | Pending exits | Pending exits |

Both sessions reconstructed two signals. August 27 remained a loss and never entered the 45%
risk-budget state; the 10% difference from the baseline is only proportional exposure reduction.
The delayed scenario lost more, so this session is not evidence that delay sensitivity is solved.
August 28 has no final outcome yet and is not reported as a profitable or completed session.

Runtime batch: `state/research_replay_v1941/20260828T165332832913Z-14980/`.
Hidden process PID 14980 reached `WAITING_FINAL` until Beijing August 29 **03:40**. It then retrieves
exit prices and appends final-stage diagnostic files for both dates. This is one date-bound process,
not a recurring schedule. The computer must remain on, connected, and awake.
The existing `USIntradayLab-V1254-AlpacaPaper` task remains running and unchanged.

## Verification

- 14 targeted tests passed, including no invented receipts, no future exit prices, incomplete-input
  handling, and the original live-runner tests.
- Replay of the frozen August 26 final snapshot matched both baseline and candidate returns for all
  three comparable scenarios to 1e-12; no original live record was modified.
- Full suite: **900 passed** in 57.33 seconds, one existing websockets deprecation warning.
- Repository-wide Ruff passed. Raw snapshots, runtime logs, and databases remain local/untracked.

Reproduction command (creates a new diagnostic batch, never rewrites this one):

```powershell
python scripts/replay_v1941_sessions.py --sessions 2026-08-27 2026-08-28 `
  --seed state/research_shadow_v1941/2026-08-26/prior.parquet `
  --output state/research_replay_v1941 --follow-final
```
