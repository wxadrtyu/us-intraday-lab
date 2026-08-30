from __future__ import annotations

import evaluate_full_universe_intraday_v7696_v7795_preroute_reversal as subject


def test_preroute_reversal_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 7696
    assert subject.LAST_VERSION == 7795
    assert subject.PREROUTE_SLOT == (11, 23)
    assert subject.PREROUTE_SLOT[1] < 24
    assert subject.PREROUTE_FAMILY == "intraday_reversal_quality"
    assert subject.PREROUTE_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "signed_volume_imbalance" in subject.PREROUTE_FACTORS
