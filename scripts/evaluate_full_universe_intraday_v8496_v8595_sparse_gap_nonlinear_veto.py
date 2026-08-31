"""v8496-v8595: nonlinear causal veto over the sparse-gap route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v7595_v7694_nonlinear_loss_veto as nonlinear
import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto

FIRST_VERSION = 8496
LAST_VERSION = 8595
PRIOR_COMPARISON_CELLS = 257_366
GATE_DECISION = 23
ENTRY_BAR = 24


def _configure():
    sparse_veto._configure()
    campaign = sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    campaign.FACTOR_SETS = nonlinear.FACTOR_SETS
    campaign.quality.GATE_DECISION = GATE_DECISION
    campaign.sector.SectorFlowLeadershipCube = nonlinear.NonlinearInteractionCube


if __name__ == "__main__":
    _configure()
    sparse_veto.campaign.main()
