# SIP quote information-contract result

- Completed versions: v17109-v17708 (600), with zero pre-null or admitted candidates.
- Tested direct quote states, inventory reversal, quote/price divergence, microprice,
  execution-quality filtering, and market-wide quote regimes.
- The strongest train/development-consistent conditioned mean event edge was only
  1.42 bp gross, versus the declared 9 bp round-trip cost.
- The best milestone, v17292, reached 17.21% annualized at 9 bp but had 23.43% MDD,
  only 2/5 positive folds, Bonferroni p=1, and -5.52% in the frozen 2026Q1 diagnostic.
- `quotes_seen` is excluded from future alpha research because progressive quote
  lookback made its counting window unequal across observations.
- No quote-only strategy is eligible for Paper admission.
- The next independent causal source is a fixed-window SIP trade-print aggregate
  immediately before each decision timestamp; acquisition remains read-only and
  brokerless.
