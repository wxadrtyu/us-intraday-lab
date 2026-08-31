"""v8697-v8796 refined bar-23 veto around the sparse-gap evidence frontier."""

from __future__ import annotations

import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto

FIRST_VERSION = 8697
LAST_VERSION = 8796
PRIOR_COMPARISON_CELLS = 257_577
GATE_DECISION = 23
ENTRY_BAR = 24
QUANTILES = (0.10, 0.15, 0.20, 0.25, 0.30)
ALPHAS = (30.0, 100.0)


def _configure() -> None:
    sparse_veto._configure()
    campaign = sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.quality.GATE_DECISION = GATE_DECISION


if __name__ == "__main__":
    _configure()
    sparse_veto.campaign.main()
