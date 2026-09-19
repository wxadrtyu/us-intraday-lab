# Daily Treasury Statement source feasibility audit (pre-registration)

Status: source feasibility only. No DTS training line has been preregistered, no bulk report archive has been acquired, and no post-publication stock return has been loaded. The frozen 2021–2023 event cube contains 527 symbols and is a **coverage-limited sample, not the full US market**.

The [Treasury cash and debt forecasting page](https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/cash-and-debt-forecasting) says the Daily Treasury Statement (DTS) is available by 4:00 p.m. on the following business day. Its [Fiscal Service description](https://fiscal.treasury.gov/accounting/daily-treasury-statement/) identifies cash and debt operations, including the Treasury account at the Federal Reserve and commercial-bank accounts. A report date is therefore not an investable publication date. A prospective training rule would first allow the signal on a frozen-sample trading session strictly after the following-business-day publication date; holidays require a calendar check.

The official FiscalData date-only API query for `record_date` in 2021–2023 returned 752 distinct dates (2021-01-04 through 2023-12-29). This was an inventory probe, **not a first-print values feed**. Dated official PDFs exist at `https://fiscaldata.treasury.gov/static-data/published-reports/dts/DailyTreasuryStatement_YYYYMMDD.pdf`. Eight in-memory PDF probes, including year-end and July holiday adjacencies, returned HTTP 200. Their embedded creation dates were the following business day; their first pages named the matching report day and Table I operating cash balance, and the 2021-01-29 Table II contained today's deposits, withdrawals, and net change. The 2021 and early-2022 objects had later S3 Last-Modified dates consistent with archive migration, **not proof that the currently served bytes were exactly the first-published bytes**. Current API values must not be used as historical first releases; the PDF version/revision risk remains to be settled before ranking.

| Report date | PDF creation (Eastern) | S3 Last-Modified (UTC) |
|---|---|---|
| 2021-01-04 | 2021-01-05 13:09 | 2022-07-06 17:41 |
| 2021-01-29 | 2021-02-01 13:41 | 2022-07-06 17:41 |
| 2021-07-02 | 2021-07-06 10:58 | 2022-07-06 17:44 |
| 2021-12-31 | 2022-01-03 11:38 | 2022-07-06 17:48 |
| 2022-06-30 | 2022-07-01 11:00 | 2022-09-28 15:37 |
| 2022-12-30 | 2023-01-03 11:31 | 2023-01-03 21:00 |
| 2023-07-03 | 2023-07-05 12:19 | 2023-07-05 20:00 |
| 2023-12-29 | 2024-01-02 11:51 | 2024-01-02 21:00 |

For a cross-stock map, a fall in Treasury cash at the Fed could mechanically add private-sector deposits/reserves, but the economic effect and its delay are unproven. The frozen cube has finite bar-5 observations for XLF on 221/230/180 dates in 2021/2022/2023. KRE has none/74/171, so a three-year KRE exposure contract is structurally impossible without changing reference mid-study. XLF is broad financials rather than a pure bank-liquidity instrument; its beta is only a historical sensitivity proxy, not proof of direct issuer exposure. A previous read-only 60-prior-pair XLF audit found an optimistic 36/251/250 sample sessions per year with at least 150 eligible symbols, but this has not been intersected with actual DTS publication dates or report fields. No outcome data were consulted.

Next decision: investigate official report revision/version policy and whether report-specific PDF metadata plus conservative dating can justify a point-in-time first-print contract. If not, reject at design stage. If yes, preregister source hashes, exact fields, a single XLF historical map, missingness and coverage gates, the frozen 400-cell 9/18 bp and one-bar-delay diagnostic **before** sequential training PDF acquisition. Never relax a failed gate after seeing data.
