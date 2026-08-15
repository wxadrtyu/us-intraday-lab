# Twelve Data dual-sleeve v4.1 freeze

## Decision

The original v4 campaign remains append-only and unchanged. It could not record
any forward sessions because its 51-stock universe included BLK, whose natural
minute trade density structurally fails the frozen 385-minute floor even on
consolidated data.

v4.1 removes only BLK, reruns the complete 36-variant historical selection on
data ending 2025-12-31, and starts a new prospective campaign on 2026-08-17.
Sessions from 2026-08-11 through 2026-08-14 are consumed diagnostics and are
forbidden from the new campaign.

## Pre-2026 observability evidence

| Segment | BLK sessions with at least 385 minutes |
|---|---:|
| 2020-2023 train | 0.53% |
| 2024 validation | 0.00% |
| 2025 research | 17.60% |

The exclusion is therefore justified without using the consumed August 2026
interval for strategy selection.

## Frozen winner

- Experiment: `portfolio-af167e23c2326d237b131c21cd098801`
- Winner: `twelvedata-dual-sleeve-v4-1-0e0230153290`
- Parameters: stock excess floor 0.005, range-position floor 0.7, SPY current
  floor 0.003, SPY exit minute 300.
- Survivors: 22 of 36 variants.

| Segment | Annualized return | MDD | IR |
|---|---:|---:|---:|
| Train 2020-2023 | 8.53% | n/a | n/a |
| 2024 | 15.86% | n/a | n/a |
| 2025 | 8.57% | n/a | n/a |
| Combined OOS 2024-2025 | 12.17% | 3.50% | 0.582 |

Combined OOS profit factor is 1.712 with 186 trades. Core, start-date,
leave-one-symbol-out, parameter-stability, and both 500-repetition null-test
gates passed.

## Forward contract

- Campaign: `research-shadow-86ea09c691248d86d4bf2e49820c2182`
- Earliest session: 2026-08-17
- Required observations: 120
- Initial observations: 0
- Order route: `FORBIDDEN`
- Primary data: Twelve Data one-minute history
- Cross-check data: Massive SIP minute aggregates
- Quality floor: SPY exactly 390 minutes and every one of the 50 stocks at
  least 385 minutes
- Forward fill and per-minute cross-provider merging are forbidden

The recorder imports no broker, exposes no submit/cancel path, and mutates only
the append-only research-shadow observation store after every quality gate
passes.
