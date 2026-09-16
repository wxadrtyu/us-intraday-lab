# Polygon Listing Lifecycle Coverage Audit

- Audit status: **BLOCKED BEFORE STRATEGY EVALUATION**
- Dataset: `polygon-listing-lifecycle-v1-2b918188c8cda2feaf298eb3`
- Frozen strategy range: `v18010-v18109`
- Strategy versions evaluated: **0**
- Eligible month-symbol rows: **215,895**
- Causal lifecycle mappings under the frozen uppercase-normalized contract: **214,566**
- Coverage: **99.384423%**
- Preserved exceptions: **1,329**
  - Uppercase-normalization collision: **1,163**
  - Exact symbol unmatched: **100**
  - Polygon inactive or lifecycle state unavailable: **66**
- Polygon source collision rows across monthly snapshots: **19,490**
- Strategy evaluation permitted: **NO**
- Paper activation: **false**
- Provider splicing: **FORBIDDEN**
- Order route: **FORBIDDEN**

## Evidence hashes

- Historical-master validation report SHA-256: `f12a825f1800bdbf274ad3a8cfc39c336bd9abd4933852aae6cd0707ec4aeceb`
- Lifecycle mapping SHA-256: `78966bfe580206b6ab9ba51863054ea15d49a345bc85517115ff02904a5f05bf`
- Exception table SHA-256: `cea16f305010c8aa2ff999cffae9f986eff4b588ef2ac194787bb743c28869a6`

## Decision

The frozen contract requires exactly one causal Polygon lifecycle record for
every eligible symbol in every decision month and permits no case-fold
collision. The observed coverage and collision evidence fail both requirements,
so no return, candidate-selection, historical-stress, consumed-period, or
native-null result was computed for `v18010-v18109`.

A read-only diagnostic retaining Polygon's native case-sensitive ticker identity
would recover the 1,163 eligible collision rows, but coverage would still be
only **215,729 / 215,895 (99.923111%)**, with 100 unmatched and 66 inactive or
missing-state rows. Therefore a case-handling change alone cannot clear the
100% gate. Continuing this lifecycle hypothesis requires a separately approved,
point-in-time provider-native identity crosswalk that resolves all 166 remaining
rows; heuristics, silent exclusions, provider splicing, and a reduced universe
remain forbidden.
