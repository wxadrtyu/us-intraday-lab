# Full-data intraday v13 regime/rotation protocol

> Superseded evidence note: the first v13 implementation grouped 2021-2023 as
> training. The required evidence contract is explicitly 2022-2023. V14-v16
> correct that boundary, and the results report does not treat v13 as a valid
> promotable search.

## Purpose and boundary

V13 tests whether cross-sectional ETF rotation and low-frequency pullback
continuation can preserve the useful pieces of v11 with fewer, higher-quality
round trips. It is offline research only: long-only, no overnight position,
maximum gross exposure one, no broker/order route, and no modification to any
paper or live observation pool.

The user requires consumed-2026 total return above 20%. That is an explicit
diagnostic veto, not a ranking input. A candidate is frozen using 2021-2025
only; 2026 and the separately sourced 2018-2020 history are attached after the
frontier is immutable. Repeated 2026 inspection means it is not independent
OOS and can never establish promotion by itself.

## Pre-registered hypotheses

1. Select the strongest member of the risk, sector, or broad ETF universe after
   a causal relative-strength confirmation, otherwise remain in cash.
2. Select a causally recovering cross-sectional laggard after an intraday
   pullback, otherwise remain in cash.
3. Use previous-session asset and SPY returns only as state gates, so weak
   regimes can remain in cash without intraday look-ahead.
4. Combine at most three non-overlapping opening, morning, afternoon, or late
   sleeves. Each sleeve pays its own round-trip cost.

## Evidence and execution contract

- immutable Alpaca IEX 1-minute snapshots: 2021-2023 training, 2024 validation,
  2025 development OOS, 2026 consumed diagnostic;
- immutable HF/Finnhub-derived 2018-2020 snapshots: cross-provider stress only;
- scheduled five-minute signal close, next scheduled bar-open entry, scheduled
  bar-open exit;
- exact boundary print required in the strict run; a separately labelled
  one-minute-tolerance diagnostic cannot override strict failure;
- 9 bp standard cost, 18 bp doubled-cost stress, and one additional five-minute
  entry delay at 9 bp.

## Selection and hard gates

Shortlists and portfolio beams are ranked only by the weakest 2021-2023, 2024,
and 2025 standard return, followed by the weakest 2024-2025 return across 9 bp,
18 bp, and delay scenarios, then the weakest stress IR. No 2018-2020 or 2026
number can affect retention.

Observation recommendation requires all of the following:

- 2024-2025 annualized return at least 50%, MDD below 20%, and IR at least one
  under 9 bp, 18 bp, and one-bar-delay scenarios;
- positive training, 2024, and 2025 returns; at least four of five positive
  development folds; at least 70% immediate-neighbor primary passes;
- positive 2018-2020 cross-source annualized return with MDD below 20%;
- consumed-2026 total return above 20%, MDD below 20%, and IR at least one;
- multiple-comparison disclosure. Even a numerical pass remains consumed-data
  evidence and needs genuinely future sessions before promotion.
