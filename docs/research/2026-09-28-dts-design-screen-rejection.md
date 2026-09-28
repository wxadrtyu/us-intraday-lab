# Daily Treasury Statement design-screen rejection

Decision: **ABANDON_DTS_DESIGN_SCREEN**. This line is frozen before preregistration, bulk acquisition, field extraction, or any post-publication return read. The frozen 2021–2023 event cube contains 527 symbols and is a **coverage-limited sample, not the full US market**.

## Point-in-time source gate

The official Treasury material establishes that the Daily Treasury Statement is normally available by 4:00 p.m. on the following business day, and the dated official PDFs expose the relevant cash-flow tables. It does not establish a public, report-level revision ledger, immutable first-release object history, or a reproducible way to recover the bytes visible at the original publication time.

The earlier eight-object audit found embedded PDF creation dates consistent with the stated release schedule. That is useful timing evidence, but it is not a first-vintage guarantee. Several 2021 and early-2022 objects have substantially later S3 modification dates. Those dates may reflect archive migration, but neither that interpretation nor the opposite interpretation can prove that today's bytes equal the first-published bytes. Current FiscalData API values also cannot be substituted for historical first releases.

The source therefore fails the preregistered-style point-in-time requirement. Conservative next-session dating cannot repair unknown historical content revisions.

## Causal exposure gate

KRE cannot support a fixed three-year exposure contract because the frozen cube has no finite bar-5 KRE observations in 2021. XLF has broader availability (221/230/180 dates in 2021/2022/2023), but it is a diversified financial-sector instrument rather than a direct commercial-bank reserve or deposit exposure. A rolling stock beta to XLF is historical co-movement; it does not identify issuer-level causal sensitivity to Treasury General Account flows.

Using XLF would therefore replace a missing causal map with broad financial beta. Changing the reference instrument after observing coverage would also violate the fixed-contract requirement.

## Frozen outcome

- Source/version gate: fail.
- Fixed causal exposure gate: fail.
- Training cells evaluated: 0.
- Post-publication returns loaded: no.
- Bulk DTS PDFs downloaded: no.
- Development or consumed-period ranking: none.
- Reopening by local timing, proxy, or threshold changes: forbidden.

This rejection does not claim that Treasury cash flows have no market effect. It says the available free official archive and the frozen sample cannot support the required historical first-vintage and cross-sectional exposure semantics without unverifiable assumptions.

Next research must start from a genuinely different free official source with independently auditable publication timestamps or immutable dated artifacts and a strict issuer/exposure map. Coverage must be established before any outcome data are loaded.
