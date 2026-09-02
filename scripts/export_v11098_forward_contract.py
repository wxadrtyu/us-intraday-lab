"""Freeze the branch-causal v11098 production input contract."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import export_v10824_forward_contract as exporter


def main() -> None:
    exporter.CANDIDATE_ID = "lev-v11098-2ddc1d07c9cfe31e"
    exporter.SELECTION_RANGE = [11006, 11105]
    exporter.CAMPAIGN_CONFIGURE = branch._configure
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
        "outer_gate_low_exposure": branch.boundary.logical.clock.parent.parent.LOW_EXPOSURE,
    }
    exporter.main()


if __name__ == "__main__":
    main()
