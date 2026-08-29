"""Family-wise native null for the recovery-confirmation reentry campaign."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2866_v2965_one_reentry as reentry
import evaluate_full_universe_intraday_v2967_v3066_reentry_confirmation as confirmation
import validate_full_universe_intraday_v2966_reentry_native_null as native

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v3067_reentry_confirmation_null/proposal.json"
)


def candidate_streams(cube, development, record, models, definition):
    reentry.REENTRY_RECOVERY = confirmation.recovery_threshold(definition["application_mode"])
    base.stopped_raw = reentry.stopped_raw
    return confirmation.build_streams(cube, development, record, models, definition)[0]


if __name__ == "__main__":
    native.PROPOSAL = PROPOSAL
    native.CODE_PATH = Path(__file__)
    native.CODE_DEPENDENCIES = (
        Path(native.__file__),
        Path(base.__file__),
        Path(reentry.__file__),
        Path(confirmation.__file__),
    )
    native.EXPECTED_ELIGIBLE = 43
    native.candidate_streams = candidate_streams
    native.main()
