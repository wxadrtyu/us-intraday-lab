# v449 brokerless research-shadow admission

## Admission

The user explicitly authorized simulated observation on 2026-08-21. Candidate
`lev-v449-03e9e3f9c4b21390` was added as a new append-only brokerless campaign:

- campaign: `research-shadow-aa9f2cc8e5208b876180e9d800d284f4`;
- first eligible XNYS session: 2026-08-24;
- required prospective sessions: 120;
- initial observations: 0;
- order route: `FORBIDDEN`.

The existing original v4, v4.1, v45, and v247 campaigns and every prior observation were left
unchanged. Before admission, `state/research_shadow.sqlite3` was copied to
`state/backups/research_shadow-pre-v449-20260821.sqlite3`; source and backup SHA-256 hashes were
identical at the time of the copy.

## Frozen evidence and exception labels

The proposal and selection manifests freeze the 95% v45 anchor and the 5% v60 static
flow-persistence component. They also preserve all non-passing labels:

- `inherited_v45_factory_null_passed=false`;
- `component_factory_null_passed=true`;
- `global_bonferroni_passed=false`;
- `all_hard_gates_passed=false`.

This is a user-authorized research-shadow exception, not a reclassification of v449 as an
independent hard-gate pass. Parameters, weights, costs, and timing cannot be tuned using forward
observations.

## Recorder parity

The new evaluator is pure and has no broker, submit, cancel, credential, position, or order path.
It records standard 9bp, 18bp, and one-extra-five-minute-bar theoretical returns.

Two consumed sessions were checked against the research engine before admission:

- 2026-08-11 exercised an active SOXL component at 100% component-sleeve exposure. Absolute
  differences were below `2e-18` for standard, 18bp, and delayed returns.
- 2026-08-12 exercised the inactive-component path. The three ensemble returns matched the
  frozen research values exactly to displayed precision.

## Automation

The existing heartbeat was updated additively to include v449. It records only after a complete
390-minute XNYS session plus the close safety buffer, fails closed on missing credentials or data
quality, and does not fill missing minutes or splice providers. The other observation paths run
independently if one path fails.
