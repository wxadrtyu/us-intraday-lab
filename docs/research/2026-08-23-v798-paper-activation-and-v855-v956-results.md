# v798 Paper activation and v855-v956 research results

## Outcome

The user-authorized Alpaca Paper pool now contains v247, v449 and v798 at one third of account
capital each. The controller applies the existing 0.99 portfolio gross buffer, remains long-only
and closes positions before the overnight boundary. No real-money route was added, no prior
observation record was rewritten, and the superseded scheduled tasks were disabled rather than
deleted.

The following 100-version v855-v954 campaign produced one frozen development winner,
`lev-v925-ab69d3ff58fe564c`. v925 passed its routed-component null and all 36 joint-neighborhood
cells. It is classified `USABLE_INHERITED_EXCEPTION_REVIEW`, not an independent alpha discovery or
a full hard-gate pass. It has not been added to the Paper pool.

## v798 Alpaca Paper activation

- Pool members: v247, v449 and v798; account fraction `1/3` each.
- Maximum aggregate gross after the controller buffer: `0.99`.
- Alpaca endpoint: `https://paper-api.alpaca.markets`; real-money routing is unavailable.
- Preflight on 2026-08-23: market closed, zero positions and zero open orders; next market open was
  reported as 2026-08-24 13:30 UTC.
- Entry task: `USIntradayLab-V247-V449-V798-AlpacaPaperPool`, ready for 2026-08-24 20:00 China time.
- Closeout task: `USIntradayLab-V247-V449-V798-AlpacaPaperPool-Closeout`, ready for 2026-08-25
  03:45:45 China time.
- Exact factor parity was checked on the five latest comparable sessions from 2026-08-06 through
  2026-08-12; maximum absolute error was `1.11e-16`.

## v855-v954 scan boundary

- 100 versions, 400 new cells and 66,755 cumulative comparison cells.
- Four distinct multi-factor state hypotheses, crossed with five component totals, five
  v247/v449 component shares and four state quantiles.
- Runtime: 6.75 seconds.
- Ranking used 2022-2025 only. Historical 2018-2020 and consumed 2026 diagnostics were attached
  after each development frontier froze.
- 291 of 300 frozen records passed every economic pre-null gate. Nine failed historical transfer;
  all 300 failed cumulative Bonferroni.

## Frozen v925 evidence

v925 holds 90% in the frozen v45 anchor and routes 10% to the frozen v449/v60 component when the
prior-close state exceeds the training-fitted 20th percentile. Its state score combines SPY
direction and risk-asset agreement positively with sector dispersion and SPY volatility negatively.
It otherwise holds the component allocation in cash.

| Period or stress | Annualized return | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2022-2023 training | 11.94% | 11.19% | 0.784 | 25.13% |
| 2024 | 13.28% | 11.86% | 0.768 | 13.28% |
| 2025 | 118.43% | 3.29% | 1.926 | 116.41% |
| 2024-2025 standard OOS | 56.99% | 11.86% | 1.460 | 145.14% |
| 2024-2025 at 18 bp | 52.24% | 12.19% | 1.354 | 130.63% |
| 2024-2025 with +5-minute delay | 54.67% | 14.91% | 1.405 | 138.00% |
| Consumed 2026 Q1 diagnostic | 44.97% | 0.75% | 2.261 | 9.41% |
| Consumed 2026 all diagnostic | 81.58% | 5.00% | 2.723 | 43.65% |
| Historical 2018-2020 | 0.91% | 16.31% | 0.211 | 2.05% |

All five chronological folds were positive and the 2022, 2023 and 2024 start-date stresses were
positive. v956 evaluated 36 joint neighbors across component weight, component share and routing
quantile; 36 passed, versus the preregistered 70% threshold.

The v955 routed-component null also passed:

- observed profit: 0.9583 across 277 accepted entries;
- session-signal permutation 95% threshold: 0.7810;
- session-safe timestamp-shift 95% threshold: 0.7540;
- 200 repetitions per null family, frozen seed 20260823;
- evidence SHA-256: `bf414d669c9156e5b5682802316e01476e2a100434e057897eef430271743714`.

## Decision

v925 clears the economic, cost, delay, historical-transfer, fold, start-date, routed-null and local
joint-neighborhood checks. It also exceeds the consumed-2026 Q1 5% diagnostic threshold and has a
43.65% consumed-2026 total return.

Two permanent failures remain explicit: the inherited v45 factory null is false, and the global
Bonferroni adjustment over 66,755 cumulative cells is false with adjusted p-value 1.0. Therefore
v925 is usable only as an inherited-exception candidate for review. Paper admission requires a
separate user authorization and is not part of this research batch.
