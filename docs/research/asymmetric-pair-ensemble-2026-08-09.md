# Asymmetric TQQQ/SOXL Pair Ensemble — Sealed OOS Result

## Decision

Retain `tqqq-soxl-asymmetric-pair-ensemble-v1-b3c0082d34ab` as a rejected
research candidate. It cleared the absolute-return, drawdown, profit-factor,
cost-stress, robustness-neighbor, and symbol-concentration floors, but it must
not enter `paper_shadow` because the unchanged OOS information-ratio floor
failed.

## Frozen strategy

- TQQQ branch: after a completed three-session return at or below -10%, decide
  90 minutes after the open and exit at minute 180.
- SOXL branch: at minute 120, require SOXL to lag TQQQ by at least 0.5%, remain
  no worse than -1.75% from its session open, and require both prior completed
  session returns to be at least -3%; exit at minute 330.
- Long only, market orders, at most one entry per session, 49% of available
  cash, and no effective tuned stop or take-profit barrier.

## Evidence

The immutable dataset was
`hf-finnhub-5min-138ddc27bc3de530051d01e30087e449`. The chronological split was
60% train, 20% development validation, and 20% sealed final test. The campaign
evaluated 12 preregistered variants; 8 passed training, and all 4 selected
robustness neighbors passed development validation.

| Segment | 1.5x-cost annualized return | MDD | PF | Trades |
|---|---:|---:|---:|---:|
| Development validation | 28.20% | 3.05% | 4.66 | 34 |
| Sealed final test | 10.17% | 7.01% | 1.98 | 30 |
| Combined OOS | 18.84% | 6.17% | 2.91 session PF | 64 |

Combined OOS returned 30.27% after 1.5x modeled costs. SOXL contributed
$19,200.14 and TQQQ contributed $10,450.93 of base-cost PnL, for 64.8% maximum
symbol concentration. The benchmark total return was -17.96%, strategy total
return was 31.40%, and total excess return was 49.36%.

The computed information ratio was -0.079, below the fixed 0.50 floor. The
current metric compares this sparse, maximum-49%-cash intraday strategy against
full close-to-close TQQQ returns. That benchmark includes overnight exposure
the strategy cannot hold and produces a negative arithmetic active mean despite
positive geometric excess return. This is a benchmark-contract concern, but it
was discovered after the sealed result and therefore is not grounds to change
the campaign decision post hoc.

## Reproducibility

- Experiment: `lh-aa3bbf0521e40570ee4ae707fdf1ee84`
- Selection SHA-256:
  `a072c8b375e2cd0ac1a53e1cd7d515de3be9d57d0bbaea682ccc571a445df617`
- Winner: `tqqq-soxl-asymmetric-pair-ensemble-v1-b3c0082d34ab`
- Final interval ledger status: consumed exactly once

The SPY/TQQQ follow-up crash-rebound scan produced zero cells satisfying the
training-return, validation-return, four-positive-subperiod, and two-symbol
concentration requirements, so it was stopped before formal screening and its
final interval remains sealed.
