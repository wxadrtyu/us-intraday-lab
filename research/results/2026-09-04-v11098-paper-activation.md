# v11098 Paper activation

- Candidate: `lev-v11098-2ddc1d07c9cfe31e`
- Allocation: 100% of the dedicated Alpaca Paper account
- Replaced runner: v1254, disabled by user instruction
- Safety boundary: Paper only, long only, gross at most 1, no overnight position
- Pre-activation cleanup: the stale 7,715-share SOXL Paper position was closed; the verified post-cleanup state was zero positions and zero open orders.
- Timing: activation happened after every legal v11098 entry window for the 2026-09-04 XNYS session. No catch-up order was submitted. The first eligible orders are therefore deferred to the next valid XNYS session.
- Frozen contract: `research/results/2026-09-03-v11098-forward-contract.json`
- Append-only runtime ledger: `state/paper/v11098.sqlite3`

The executable entry schedule covers bars 3, 11, 12, 18, 24, and 42 so every causal transfer, modern/fallback, and fill-parent route in the frozen contract is represented.
