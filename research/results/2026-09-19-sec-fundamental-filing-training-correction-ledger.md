# SEC fundamental-filing training correction ledger

The canonical decision artifact is
`2026-09-19-sec-fundamental-filing-training-feasibility-v3-summary.json`.
The earlier reports are retained as failed-diagnostic evidence and must not be used
for research decisions:

- The original v1 report counted only positive ranked strategy signals as data
  coverage, producing 132 qualified issuers and 1,000 filings.
- The corrected v2 report counted raw availability only after projection onto the
  active event panel. That projection drops filings without an eligible event row
  and collapses overlapping five-session filing windows, producing 176 qualified
  issuers and 1,373 filings.
- v3 carries the immutable per-issuer raw filing inventory independently of the
  active signal rows. It records 383 issuers with at least four valid filings and
  2,850 feature-bearing filings, so the preregistered 300/1,200 coverage gate passes.

The v3 diagnostic completed all 400 preregistered cells. No cell and no family
passed the retention gates. The best cell was revenue acceleration at decision bar
5, six-bar holding, and top one: 0.3774% standard annualized return, 0.0862
information ratio, -4.2896% annualized return at 18 bp, and -3.2004% annualized
return under the five-minute delay stress. The SEC fundamental-filing clue is
therefore abandoned without development or consumed-period loading, strategy
version creation, Paper activation, pool mutation, or order routing.

