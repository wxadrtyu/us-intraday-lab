# Full-data intraday continuation: v21-v25

Date: 2026-08-15
Branch: `codex/full-data-v13-2026-gated`

## Decision

No v21-v25 candidate is eligible for future simulation observation. The consumed-2026 return objective was exceeded by v21 (best diagnostic +30.27%, following v20's +32.23%), but that result is diagnostic only and failed the predeclared development, 18bp, 5-minute-delay, historical-transfer, and multiple-comparison gates. The current simulation-observation pool remains unchanged.

All candidate generation and ranking used 2022-2025 only. Consumed 2026 was attached after each frontier was frozen. No blind-data task output, broker path, credential, paper state, or order route was read or changed.

## Falsifiable hypotheses and results

| Stage | Hypothesis | Trials | Seconds | 2026 >20 count | Best consumed 2026 total / MDD / IR | Dev OOS annual | 18bp annual | Delay annual | Historical annual |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v21 | causal VWAP reclaim, range compression breakout, VWAP support | 206,417 | 171.67 | 204 | +30.27% / 6.16% / 2.94 | 16.00% | 9.83% | 8.69% | -9.67% |
| v22 | prior-session volatility shock/recovery and calm continuation | 350,678 | 291.80 | 0 | +9.16% / 6.09% / 1.58 | 22.26% | 16.29% | 15.62% | -7.60% |
| v23 | rolling-beta residual strength/recovery and defensive rotation | 266,544 | 235.30 | 0 | +2.01% / 16.43% / 0.24 | 22.92% | 13.26% | 17.06% | -1.78% |
| v24 | sector breadth, dispersion, narrow leadership and breadth recovery | 287,181 | 256.61 | 0 | -0.49% / 1.69% / -0.84 | 3.60% | 1.47% | 3.06% | -0.74% |
| v25 | frozen v20/v21 top-frontier weighted ensemble | 1,728 | 16.06 | 0 | -7.03% / 13.26% / -0.47 | 34.48% | 21.78% | 27.66% | -23.51% |
| v25b | development-rank-stratified frozen ensemble | 120,000 | 198.98 | 0 | +13.04% / 4.33% / 1.76 | 31.13% | 20.76% | 20.30% | -9.50% |

Total completed scan scale was 1,232,548 trials in 1,170.42 seconds. The interrupted warning-only v24 attempt is excluded from both totals; it produced no checkpoint and was rerun unchanged after replacing noisy all-NaN reductions with explicit finite-value reductions.

## Interpretation

The v21 result confirms that the consumed-2026 target can be reached by a distinct intraday structure source, but it is not robust evidence: its development OOS annualized return was only 16.00%, falling to 9.83% at 18bp and 8.69% with one extra 5-minute bar, while the independent historical source was -9.67% annualized. Treating its +30.27% as a promotion signal would therefore tune to consumed data.

The strongest transferable finding is negative but useful. Prior-session volatility states, beta residuals, sector breadth, and development-only ensembles did not repair the joint regime/cost problem. v25b materially reduced 2026 drawdown and kept IR above 1, but its +13.04% total return remained below the requested 20% diagnostic threshold and its historical transfer stayed negative.

## Gate disposition

- Standard primary gate (annualized return >=50%, MDD <20%, IR >=1, positive development segments): failed.
- 18bp primary gate: failed.
- Extra one-bar delay primary gate: failed.
- Historical cross-source positive return with MDD <20%: failed.
- Multiple-comparison Bonferroni 5% gate: failed.
- Start-date and parameter-neighborhood gates: intentionally fail-closed because no candidate cleared the earlier gates.
- Consumed-2026 >20%, MDD <20%, IR >=1: v21 diagnostic candidates passed, but this cannot override the failed development and stress gates.

Status: research-only, not promotable, not added to simulation observation.

## Verification

- `ruff check`: passed for v21-v25 scripts.
- `py_compile`: passed for v21-v25 scripts.
- `pytest -q` with `PYTHONPATH` bound to this worktree's `src`: 838 passed, one pre-existing `websockets.legacy` deprecation warning.
