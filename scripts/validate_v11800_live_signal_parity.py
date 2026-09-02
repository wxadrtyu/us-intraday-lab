"""Replay v11800 through the parity-proven live-frame leg adapter."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import validate_v11098_live_signal_parity as validator


def main() -> None:
    validator.CANDIDATE_ID = "lev-v11800-90804cea426c9753"
    validator.CAMPAIGN_CONFIGURE = hard._configure
    validator.main()


if __name__ == "__main__":
    main()
