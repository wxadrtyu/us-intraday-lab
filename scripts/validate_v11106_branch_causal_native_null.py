"""v11106 native maxT null for the branch-causal v11098 candidate."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import validate_v10905_causal_bar5_and_native_null as native


class _BranchCampaignFacade:
    logical = branch.boundary.logical

    @staticmethod
    def _configure() -> None:
        branch._configure()


def main() -> None:
    native.VALIDATION_VERSION = 11106
    native.SELECTION_RANGE = [11006, 11105]
    native.SEED = 20260903
    native.boundary = _BranchCampaignFacade
    native.main()


if __name__ == "__main__":
    main()
