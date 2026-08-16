# v247 admission and v248-v348 mechanism campaign

## Admission count

One strategy was newly admitted in this stage: `lev-v247-df683b8a37c927f6`.

- Campaign: `research-shadow-7ccd0906ec2adcddd9c78cb9ab46c9c0`
- Earliest prospective session: 2026-08-17
- Minimum prospective sessions: 120
- Current observations: 0
- Route: `FORBIDDEN`
- Labels retained: `inherited_v45_factory_null_passed=false`,
  `component_factory_null_passed=true`, and `global_bonferroni_passed=false`

The append-only database was backed up before admission. Original v4, v4.1, and v45 campaign
rows were not modified. The usable admitted set is now v4.1, v45, and v247. Original v4 remains
in the immutable database but is not usable because its BLK quality contract cannot record a
session.

## Forward recorder

The new pure evaluator combines the frozen v45 observation at 95% with the frozen dual-clock
flow-persistence component at 5%. It records standard 9bp, 18bp, and one-extra-5-minute-bar
returns and exposes no broker or order route. On the consumed 2026-08-12 parity session, all
three returns exactly matched the research engine:

| Scenario | Research | Recorder | Difference |
|---|---:|---:|---:|
| Standard 9bp | -1.1920898407% | -1.1920898407% | 0 |
| Cost 18bp | -1.2621252711% | -1.2621252711% | 0 |
| Delay 5 minutes | -0.7045312223% | -0.7045312223% | 0 |

## v248-v347 campaign

The campaign advanced 100 actual version numbers and evaluated 2,650 new parameter cells in
141.03 seconds. Cumulative multiple-comparison accounting increased to 31,510 cells.

- v248-v297: 50 v45 state-filter enhancement versions. Twenty-five distinct market-state
  concepts were evaluated at two causal clocks, with five development-ranked thresholds each.
- v298-v347: 50 independent long-only multi-factor rule versions. Ten mechanisms were evaluated
  across five distinct intraday entry/holding schedules, with cost, delay, volatility-target,
  confirmation, and lookback stresses.
- 2026 was attached only after each three-record development frontier froze and was diagnostic
  only.
- Result: one pre-factory-null candidate, zero new admissions.

## Why the 100 versions were rejected

Each version is assigned one first binding reason using the fixed gate order, so these counts are
mutually exclusive and sum to 100.

| Family | Versions | First binding rejection reason |
|---|---:|---|
| State enhancement | 39 | Standard 50%/MDD/IR primary gate |
| State enhancement | 5 | 18bp primary gate after standard passed |
| State enhancement | 1 | Extra 5-minute delay primary gate |
| State enhancement | 1 | Separate historical-source return/MDD gate |
| State enhancement | 3 | 70% immediate-neighborhood primary gate |
| State enhancement | 1 | Factory-native null test after every economic gate passed |
| Independent rule | 50 | Standard 50%/MDD/IR primary gate |

The 50 independent-rule versions therefore failed for insufficient development economics, not
because their 2026 diagnostics were ignored. The strongest independent version by displayed OOS
return was v344 at 44.74% annualized, still below the 50% floor.

## v291 falsification

`lev-v291-8edb7cfeb1c7009e` applied a prior-close low-risk-asset-agreement state to v45. It passed
standard, 18bp, delay, folds, historical transfer, neighborhood, and consumed-2026 gates, but the
filter did not change v45's realized opportunity set. Its factory-null evidence was exactly the
same failed evidence as v45:

- observed development profit: 1.2805671155;
- session-signal permutation 95th percentile: 1.3269893902;
- session-safe timestamp-shift 95th percentile: 1.2869546018.

v291 was rejected and was not added as a duplicate campaign. Its cumulative Bonferroni reference
also remained false.

## Next version boundary

The recurring task now starts at v349 and must run at least 100 actual versions per batch. At
least half of each batch changes or strengthens admitted strategies, and at least half explores
independent mechanisms. Every batch must report newly admitted count, rejected count, and
mutually exclusive rejection reasons.
