# CFPB Consumer Complaint Database source rejection

Decision: **ABANDON_CFPB_CONSUMER_COMPLAINT_SOURCE**. The proposed 2021–2023 Consumer Financial Protection Bureau Consumer Complaint Database line is frozen at the public-availability and historical-vintage source gates, before preregistration, database download, company matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Public posting is conditional and not dated in the public record

CFPB states that a complaint becomes eligible for publication only after it is sent to a company. It is published after the company responds and confirms a commercial relationship, or after 15 calendar days, whichever occurs first. A company that shows it was wrongly identified can delay or prevent publication until the correct company is identified. The database generally updates daily.

Consequently, neither `Date received` nor `Date sent to company` is the actual first-publication time. A fixed 15-day lag is also invalid because a confirming response can trigger earlier publication and company-identification disputes can trigger later or no publication. The public field reference includes `Date received`, `Date sent to company`, response fields, and `Complaint ID`, but does not expose the date or timestamp when that complaint first appeared in the public database.

Official references:

- CFPB Consumer Complaint Database and publication rule: https://www.consumerfinance.gov/data-research/consumer-complaints/
- CFPB database field reference: https://cfpb.github.io/api/ccdb/fields.html
- CFPB company complaint process and removal rule: https://www.consumerfinance.gov/compliance/consumer-complaint-program/company-process/
- CFPB 2013 Final Policy Statement: https://files.consumerfinance.gov/f/documents/201303_cfpb_Final-Policy-Statement-Disclosure-of-Consumer-Complaint-Data.pdf
- CFPB API documentation: https://cfpb.github.io/api/ccdb/api.html

## The cumulative database is mutable and cannot reconstruct daily history

The 2013 Final Policy Statement says that once some data for a complaint are disclosed, newly disclosable complaint data are added as they become available; a later company response can overwrite the initial `In progress` value. The current company-process page also says CFPB removes complaints that do not meet all publication criteria. Company public responses may be selected as late as 180 days after a complaint was sent to the company. Thus the current row is not guaranteed to be the information set first published.

The main page's `past database releases` material describes product, sub-product, issue, and sub-issue taxonomy changes. It is not an immutable daily archive of every 2021–2023 database state. The official pages reviewed do not provide a per-record first-publication timestamp, immutable daily object hashes, or a complete ledger of subsequent additions, field overwrites, removals, company reassignments, and duplicate treatment. A current API or CSV snapshot therefore cannot establish what the public knew on each historical trading date.

No economically homogeneous complaint event or aggregation rule was preregistered and no company mapping was attempted because the point-in-time source failed first. Any later design would have had to freeze one product, issue, company-response state, narrative-consent state, and duplicate rule before observation. Exact matching would have allowed only the database's full `Company` legal name equal to a frozen SEC issuer name; brands, products, subsidiaries, parents, former names, addresses, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by using `Date received`, `Date sent to company`, a fixed 15-day lag, an API sort timestamp, today's cumulative CSV/API state, or an observed response date as a proxy for first publication; by silently excluding complaints later removed or reassigned; or by mixing products, issues, response states, narrative states, or duplicates after inspection.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `dataset_downloaded=false`, `complaint_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
