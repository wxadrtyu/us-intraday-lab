"""Native maxT null for the two v11708-v11807 hard-veto candidates."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import validate_v10905_causal_bar5_and_native_null as native


class _HardVetoFacade:
    logical = hard.branch.boundary.logical

    @staticmethod
    def _configure() -> None:
        hard._configure()


def main() -> None:
    native.VALIDATION_VERSION = 11808
    native.SELECTION_RANGE = [11708, 11807]
    native.SEED = 20260903
    native.EXPECTED_ELIGIBLE = 2
    native.boundary = _HardVetoFacade
    native.main()


if __name__ == "__main__":
    main()
