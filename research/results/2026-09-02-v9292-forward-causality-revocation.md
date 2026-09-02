# v9292 forward-causality revocation

v9292 is not eligible for Paper activation. A production-parity audit found
that its bar-23 soft veto scales the complete daily return of routed v42 parent
strategies whose native decisions and entries occur before the declared bar-24
late entry. The research graph never reprices those parent positions at bar 24.

The prior repair correctly prevented bar-23 information from changing the
separate bar-2 / bar-3 / bar-11 opening sleeve, but it did not remove earlier
entries embedded inside the so-called late route. Consequently, the published
v9292 performance cannot be reproduced by a causal two-stage forward executor.

- Candidate: `lev-v9292-d229bbc0e792bfcf`
- Revised execution status: `REJECTED_NONCAUSAL_LATE_ROUTE_REPRICING_PARITY`
- Paper allocation: 0%
- Existing Paper pool: unchanged
- Historical research artifact: retained unchanged as failed evidence

A valid successor must reconstruct every selected late parent from the bar-24
open (or later), recompute costs and volatility exposure from those executable
returns, and pass all economic, historical, robustness, multiplicity, native
null, and exact forward-parity gates as a new unused strategy version.
