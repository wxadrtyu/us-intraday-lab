"""v7495-v7594 last-pre-entry-bar loss veto over the frozen v6776 route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as quality
import evaluate_full_universe_intraday_v7395_v7494_full_route_loss_veto as campaign

FIRST_VERSION = 7495
LAST_VERSION = 7594
PRIOR_COMPARISON_CELLS = 256_355
GATE_DECISION = 23
ENTRY_BAR = 24


def _configure() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    quality.GATE_DECISION = GATE_DECISION


if __name__ == "__main__":
    _configure()
    campaign.main()
