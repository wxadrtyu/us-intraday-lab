# Alternative five-minute technical source entitlement check

Status: read-only source feasibility; no bulk download, candidate return, or
trading action.

The validated SIP five-minute source has complete signal-entry-exit paths in
only 1 of the 20 fixed five-to-ten-minute routes at the 95% aggregate floor;
that route misses 95% in 37/96 months. This is a data limitation, not a reason
to tune the decision time or remove missing names.

An existing Polygon/Massive credential was available. A single read-only
request for unadjusted historical AAPL five-minute aggregates on 2023-12-29
returned HTTP 403 with provider status `NOT_AUTHORIZED`. No price result was
retained and the credential was not printed. This confirms the current account
cannot use this REST path for a replacement full-market dataset. It does not
prove that an independently entitled flat-file or exchange product would also
be denied. No subscription or purchase was made.

The provider's [stock flat-file overview](https://massive.com/docs/flat-files/stocks/overview)
describes full-market SIP minute aggregates, but access is plan-dependent and
there is no local S3 credential or staged stock minute-aggregate flat-file
dataset. Its [aggregate-bars documentation](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
also states that intervals with no qualifying trades have no aggregate bar.
Thus even a new aggregate vendor cannot be assumed to repair every absent
execution bar. It must be independently audited, never spliced into the
frozen Alpaca result or used to recode missing as cash.

The distinct technical field still worth a source audit is timestamped primary
exchange auction imbalance/indicative price, with all listing venues and
point-in-time symbols represented. The local staging tree has no such feed.
Venue-specific product descriptions are not an accessible full-market dataset.
Until an entitled, independently complete source is available, no new five-
minute strategy-return test is justified. Ten-minute monitoring remains
active; unchanged entitlement is a quiet data gate, not a candidate failure.
