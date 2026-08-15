# Full-data intraday v33 and fixed-data exhaustion audit

Date: 2026-08-15

## Decision

V33 is not promotable, and the existing fixed 16-ETF OHLCV data contract no longer contains a materially independent untested source that can be explored without repeating rejected hypotheses or escalating multiple-comparison risk. The research objective is blocked pending an external-state change such as a broader tradable universe, an independent volatility/macro/constituent-breadth feature set, or genuinely future sessions.

The observation pool remains unchanged. No broker, credential, paper state, or order path was used.

## V33 result

V33 predeclared six shrinkage configurations. Models fit only 2022-2023, 2024 set activity thresholds, and 2025 remained the development test. Consumed 2026 and the separate 2018-2020 source were attached only after all six records froze.

| Configuration | Train annual | 2024 annual | 2025 annual | Dev OOS annual | 18bp annual | Consumed 2026 total | Historical annual |
|---|---:|---:|---:|---:|---:|---:|---:|
| alpha 100, q 0.60 | +86.0% | -23.3% | +6.4% | -9.8% | -32.6% | +29.9% | -37.8% |
| alpha 10, q 0.60 | +87.1% | -29.0% | +34.5% | -2.4% | -27.4% | -0.7% | -37.4% |
| alpha 1000, q 0.75 | +53.8% | -21.1% | -33.1% | -27.3% | -39.6% | +72.7% | -32.0% |
| alpha 1000, q 0.60 | +60.8% | -30.0% | -33.4% | -31.7% | -48.6% | +6.8% | -42.1% |
| alpha 100, q 0.75 | +63.7% | -34.2% | +10.4% | -14.9% | -30.1% | +54.1% | -38.5% |
| alpha 10, q 0.75 | +81.4% | -38.1% | +16.0% | -15.4% | -30.9% | +40.4% | -41.2% |

Four configurations exceeded 20% total return in consumed 2026, but every configuration failed immediately in 2024 and aggregate development OOS. The +72.7% diagnostic maximum therefore provides evidence of regime drift, not a selectable strategy.

## Exhaustion audit

The verified local manifests contain the same 16 symbols: SPY, QQQ, IWM, TQQQ, SOXL, and eleven sector ETFs. Newly present snapshots extend or duplicate historical windows; they do not add a new cross-sectional universe or a new feature class.

The completed development-frozen program now covers:

- existing opening/morning momentum and its v8/v9 replays;
- low-turnover cash regimes, prior-5 and prior-20 states;
- fixed-asset breakouts, recoveries, gaps, and long holding windows;
- cross-sectional relative strength, reversal, industry rotation, breadth, dispersion, and beta residuals;
- causal relative volume, VWAP, range compression, reclaim, and breakout structure;
- prior-session volatility, calendar states, trailing performance overlays, and frozen ensembles;
- QQQ-to-TQQQ and XLK-to-SOXL proxy execution, including asset-isolated frontiers;
- ridge, KNN, extra-tree, and state-conditioned shrinkage models with development-only fitting.

Across repeated stages, consumed-2026 returns above 20% occur, but no candidate simultaneously passes the authoritative 50% annualized development gate, the same gate at 18bp, the extra-bar-delay gate, folds, historical transfer, parameter stability, and multiple-comparison pressure. Continuing to vary thresholds within these same feature families would not constitute a new hypothesis and would make the consumed diagnostic increasingly misleading.

## Evidence required to unblock

At least one of the following materially new inputs is required before further search can be scientifically distinct:

- a broader liquid equity/ETF universe with the same immutable minute-data protocol;
- causal volatility, options, macro, or constituent-level breadth features covering training and validation periods;
- an additional independent historical provider with sufficient exact-boundary coverage;
- genuinely future, previously unconsumed sessions for forward confirmation of a frozen candidate.

Status: blocked on the fixed-data research frontier; no strategy added to simulation observation.
