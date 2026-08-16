"""Relaxed VWAP-reclaim zone campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v50_vwap_reclaim_event as campaign

campaign.PRIOR20_CEILINGS = (0.05, 0.10)
campaign.CURRENT_FLOORS = (-0.005, 0.0)
campaign.VWAP_CROSS_BANDS = (
    (-0.002, 0.0),
    (0.0, 0.0),
    (0.005, -0.002),
    (0.010, -0.005),
    (0.010, 0.0),
)
campaign.VOLUME_ACCELERATION_CEILINGS = (0.25, 0.50)
campaign.PATH_EFFICIENCY_FLOORS = (0.0, 0.10)
campaign.TARGETS = (0.25, 0.30, 0.35)
campaign.CANDIDATE_PREFIX = "lev-v51z-"
campaign.SELECTION_CONTRACT = (
    "the relaxed five-factor VWAP-reclaim zone and 240-cell family were declared before "
    "historical and 2026 diagnostics"
)


if __name__ == "__main__":
    campaign.main()
