# DOJ Antitrust enforcement design-screen rejection

Decision: **ABANDON_DOJ_ANTITRUST_ENFORCEMENT_DESIGN**. The line is frozen before preregistration, URL inventory acquisition, defendant matching, coverage measurement, or any post-filing return read. The frozen 2021–2023 event cube contains 527 symbols and is a **coverage-limited sample, not the full US market**.

## Point-in-time source assessment

Current Justice Department press-release pages display an original release date, but sampled 2022 pages also display a common `Updated February 6, 2025` marker. They are therefore current CMS renderings, not immutable first-release pages. The press-release text cannot be assigned to the original date without a historical version source.

Antitrust case pages provide a stronger narrow source: a case-open date, full case name, and links to docketed complaint or indictment PDFs. Examples in the training window include American Airlines/JetBlue, UnitedHealth/Change Healthcare, Booz Allen/EverWatch, Google, Activision Blizzard, and JetBlue/Spirit. A complaint filing is a public legal event; a conservative contract could begin on the first sample session strictly after the filed complaint date and use only defendant names appearing in the filed document. Later case-page edits would not redefine the docketed complaint.

## Structural coverage bound

The official Antitrust Division workload statistics bound the usable civil complaint population before issuer matching. For fiscal years 2021, 2022, and 2023, total merger complaints filed were 12, 10, and 1; total non-merger litigation complaints were 3, 6, and 1. That is at most **33 civil complaint events** across the three fiscal years before excluding private firms, foreign-only listings, individuals, cases outside the calendar training dates, duplicate defendants, and names that do not exactly match the frozen issuer identities.

Thirty-three source events cannot support the established issuer-event coverage scale or a five-family 400-cell training diagnostic without repeatedly slicing the same few litigations. Adding follow-on briefs, orders, settlements, or press commentary would turn procedural updates into pseudo-independent events and mix materially different causal mechanisms. Adding criminal individual cases would not repair listed-issuer coverage and would further change the hypothesis.

## Frozen outcome

- Docketed complaint point-in-time semantics: provisionally defensible.
- Press-release first-vintage semantics: fail.
- Structural event-count coverage: fail at design stage.
- URL inventory or document archive acquired: no.
- Exact issuer matches evaluated: 0.
- Training cells evaluated: 0.
- Post-event returns loaded: no.
- Reopening by procedural-event duplication or mixed enforcement types: forbidden.

This decision does not assert that antitrust complaints lack price impact. It rejects the source as a repeatable 2021–2023 cross-sectional training family for this frozen sample. Research must move to a genuinely different official source with a materially larger population of independently dated causal events.
