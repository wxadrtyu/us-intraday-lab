"""Validate v11800 by reusing the parity-proven branch forward planner."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import validate_v11098_branch_forward_parity as validator


def main() -> None:
    validator.CANDIDATE_ID = "lev-v11800-90804cea426c9753"
    validator.SELECTION_RANGE = [11708, 11807]
    validator.CAMPAIGN_CONFIGURE = hard._configure
    validator.main()


if __name__ == "__main__":
    main()
