from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _module():
    scripts = Path(__file__).parents[2] / "scripts"
    path = scripts / "evaluate_full_universe_intraday_v349_v448_preregistered_campaign.py"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("v349_v448", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_preregisters_one_hundred_unique_versions() -> None:
    module = _module()
    specifications = module.specifications()
    assert len(specifications) == 100
    assert len({repr(value) for value in specifications}) == 100
    assert sum(value[0] == "state" for value in specifications) == 50
    assert sum(value[0] == "rule" for value in specifications) == 50
    assert module.FIRST_VERSION == 349
    assert module.LAST_VERSION == 448
