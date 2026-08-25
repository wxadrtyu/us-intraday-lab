from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_campaign_preregisters_one_hundred_new_versions() -> None:
    scripts = Path(__file__).parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    module = importlib.import_module(
        "evaluate_full_universe_intraday_v1664_v1763_preregistered_campaign"
    )
    campaign = module.campaign
    specifications = campaign.specifications()
    assert (campaign.FIRST_VERSION, campaign.LAST_VERSION) == (1664, 1763)
    assert campaign.PRIOR_COMPARISON_CELLS == 94_355
    assert len(specifications) == len({repr(value) for value in specifications}) == 100
    assert sum(value[0] == "state" for value in specifications) == 50
    assert sum(value[0] == "rule" for value in specifications) == 50
