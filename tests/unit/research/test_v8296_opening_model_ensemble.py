from __future__ import annotations

import evaluate_full_universe_intraday_v8296_v8395_opening_model_ensemble as subject


def test_opening_model_ensemble_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 8296
    assert subject.LAST_VERSION == 8395
    assert subject.dual.OPENING_SLOT == (2, 11)
    assert subject.dual.PREROUTE_SLOT == (11, 23)
    assert subject.dual.PREROUTE_SLOT[1] < 24
    assert subject.AUCTION_FAMILY in subject.residual.FACTOR_SETS
    definition = subject.dual.foundation.campaign.EXTRA_COMPONENT_DEFINITION
    assert definition["opening_model_weights"] == [0.5, 0.5]
    assert subject.dual.foundation.campaign.EXTRA_COMPONENT_BUILDER is subject._ensemble_components
