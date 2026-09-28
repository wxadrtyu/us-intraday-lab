# SEC administrative-proceedings source rejection

Decision: **ABANDON_SEC_ADMINISTRATIVE_PROCEEDINGS_SOURCE**. The line is frozen during source design, before preregistration, full index/PDF acquisition, respondent mapping, event-cube access, or any post-release return read. The frozen 2021-2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Public-time semantics fail

The SEC's [Administrative Proceedings index](https://www.sec.gov/enforcement-litigation/administrative-proceedings) is a chronological list of orders instituting litigated and settled matters **and other issuances** by the Commission or the Division of Enforcement. Its displayed date and the date printed in an order establish the legal release date, but the SEC does not define either field as the first time the file became available online.

The SEC's own [Administrative Proceeding Documents notice](https://www.sec.gov/litigation/apdocuments) says the lists may not be exhaustive, not all associated filings may be online, and filings made available online are generally posted within five business days. A rule using the printed release date followed by the next sample trading session would therefore sometimes trade before the official document was actually available on the website. The current archive provides no historical posting timestamp ledger that closes that gap for 2021-2023.

## Current bytes do not preserve first-publication bytes

Two official 2023 examples demonstrate an independent version problem. The current PDFs for [Exchange Act Release 34-97497](https://www.sec.gov/files/litigation/admin/2023/34-97497.pdf) and [34-97498](https://www.sec.gov/files/litigation/admin/2023/34-97498.pdf) both print `May 12, 2023`, retain those release numbers, and identify themselves as **CORRECTED ORDER INSTITUTING ADMINISTRATIVE PROCEEDINGS**. The current index labels both `(Corrected)` under the same May 12 date. Their official HTTP `Last-Modified` values are May 18, 2023 at 16:49:36Z and 16:49:37Z respectively. The archive exposes the corrected current objects, but no immutable original bytes or correction-publication timestamp for those release numbers.

The frozen external audit manifest SHA-256 is `bf14cc3c35b1b2fc025ce4322ece0a5a2b582ea6040637e979c2a02fe56846ab`. It records the official documents-page HTML (`3fc695a4ba4d59be681c026df29baea56dd05ead1e03790ebfbec1b988a68389`), the 2023 index page containing the two corrected entries (`53727bb596ac20c26f71e21ffb95fdc6527d5f37c3d12614e928ebbd602f0033`), and the two current PDFs (`0b72786f0dc67086781f4a5dac5961800ed38669d3645ac6b804a44e740bfa67` and `3dbe0785e1463575df981cbf85ae1b59906f5c394f30c249d07a5b7d4d2575f9`).

## Event volume and mapping were not opened

The filtered 2023 index currently reports 698 items, but that number mixes institution/settlement orders with later procedural, distribution, and delegated-authority issuances. It is not a count of first OIPs and was not repurposed as one. Because point-in-time availability and first-version bytes already fail, no 2021-2023 OIP inventory, PDF corpus, respondent extraction, current-SEC or frozen-527 matching, family design, calendar mapping, or outcome access is justified.

Final state: `source_point_in_time=false`, `preregistered=false`, `full_index_acquired=false`, `pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. Do not rescue this line by assuming release date equals posting date, using the current corrected PDF as original content, dropping corrected records after observing them, or substituting adviser/broker subsidiaries for listed parents. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
