# v57-v58 two-hundred-round multi-factor campaign

## Result

No new candidate passed the unchanged forward-admission gates. The campaign completed 200
predeclared multi-factor rounds, 12,400 parameter cells, and 1,000 frozen frontier diagnostics.
Consumed 2026 was attached only after each round froze its five development leaders and was
never used to select a factor, sign, timing, threshold, or parameter.

The existing user-authorized v45 research-shadow exception remains active and unchanged. This
campaign searched for an independent second strategy; it did not modify v45 or its exception.

## v57: 100 single-state rounds

v57 combined 20 economically distinct multi-factor templates with five entry/holding schedules.
Each of the 100 rounds evaluated 60 cells across equal versus train-IC reliability weighting,
five score thresholds, three volatility targets, and two causal lookbacks.

- Rounds: 100/100
- Parameter cells: 6,000/6,000
- Frozen frontier: 500
- Runtime: 628.80 seconds
- Candidates passing standard primary gate: 0
- Candidates passing 18bp primary gate: 0
- Candidates passing delayed primary gate: 0
- Candidates with positive historical return and MDD below 20%: 61
- Candidates with consumed-2026 total return above 5%: 154
- Candidates passing all pre-null gates: 0

The development leader was `lev-v57r-4aea2697af180703`, a five-factor leverage-mean-reversion
round at bar 23 with exit bar 65. Its 2024-2025 standard annualized return was 30.26%, MDD
12.54%, IR 1.11, and 126 trades. At 18bp it fell to 23.42%; consumed 2026 was -1.63%; the
separate historical source returned -23.71% annualized with 55.37% MDD. It is not viable.

## v58: 100 multi-horizon event rounds

v58 retained the same 20 economic templates but replaced the static score with five distinct
four-horizon event schedules. Each round evaluated first-trigger versus two-confirmation entry,
factor weighting, score threshold, volatility target, and lookback. Cached NumPy score and
trigger matrices reduced runtime despite the larger cell count.

- Rounds: 100/100
- Parameter cells: 6,400/6,400
- Frozen frontier: 500
- Runtime: 234.02 seconds
- Candidates passing standard primary gate: 0
- Candidates passing 18bp primary gate: 0
- Candidates passing delayed primary gate: 0
- Candidates passing the global 6,400-cell Bonferroni reference: 13
- Candidates with positive historical return and MDD below 20%: 48
- Candidates with consumed-2026 total return above 5%: 197
- Candidates passing all pre-null gates: 0

The development leader was `lev-v58e-29017e5572d88961`, a six-factor cross-state rotation event.
Its 2024-2025 standard annualized return was 40.21%, MDD 22.17%, IR 0.98, and 161 trades. At
18bp it fell to 31.79%; one-bar delayed annualized return was 38.76%. Consumed 2026 returned
+20.84%, but the separate historical source returned -4.75% annualized with 44.28% MDD. The
strong consumed diagnostic therefore does not rescue the failed development and history gates.

## Interpretation

Increasing search breadth from small families to 200 full rounds did not reveal a hidden robust
strategy. The binding constraint is not a lack of profitable-looking 2026 paths: 351 frontier
records exceeded the 5% consumed diagnostic across the two campaigns. The binding constraint is
joint development economics under 18bp costs, MDD/IR, and cross-provider history. None of the
1,000 frontier records passed even the standard primary gate, so no factory-null promotion was
run.

Future batches must change the economic mechanism rather than enlarge these same static-score or
multi-horizon-event grids. The daily automation is authorized to execute at least 100 bounded
rounds per research batch while retaining the same global multiple-comparison accounting and
consumed-2026 boundary.
