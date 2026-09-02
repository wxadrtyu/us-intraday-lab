"""Freeze the hard-cash branch-causal v11800 production input contract."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import export_v10824_forward_contract as exporter


def main() -> None:
    exporter.CANDIDATE_ID = "lev-v11800-90804cea426c9753"
    exporter.SELECTION_RANGE = [11708, 11807]
    exporter.CAMPAIGN_CONFIGURE = hard._configure
    exporter.EXECUTION_METADATA = {
        "long_only": True,
        "gross_limit": 1.0,
        "overnight": False,
        "bar_minutes": 5,
        "outer_gate_decision_bar": 5,
        "opening_decision_bar": 2,
        "opening_entry_bar": 3,
        "opening_exit_bar": 11,
        "transfer_route_decision_bar": 2,
        "transfer_fill_minimum_entry_bar": 11,
        "modern_fallback_route_decision_bar": 23,
        "modern_fallback_fill_minimum_entry_bar": 24,
        "outer_gate_low_exposure": 0.0,
    }
    exporter.main()


if __name__ == "__main__":
    main()
