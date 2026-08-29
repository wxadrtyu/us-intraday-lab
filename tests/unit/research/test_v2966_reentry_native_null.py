from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import numpy as np
import validate_full_universe_intraday_v2966_reentry_native_null as subject


def test_compound() -> None:
    assert subject.compound(np.array([0.1, -0.05])) == 1.1 * 0.95 - 1.0
