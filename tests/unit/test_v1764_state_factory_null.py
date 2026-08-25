from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def test_pre_null_candidates_reads_only_frozen_survivors(tmp_path: Path) -> None:
    scripts = Path(__file__).parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    module = importlib.import_module("validate_full_universe_intraday_v1764_state_factory_null")
    for version in range(1664, 1764):
        records = [
            {
                "candidate_id": f"candidate-{version}",
                "pre_factory_null_pass": version in {1684, 1704},
            }
        ]
        (tmp_path / f"full-universe-intraday-v{version}-exact.json").write_text(
            json.dumps({"records": records}), encoding="utf-8"
        )
    candidates = module._pre_null_candidates(tmp_path)
    assert [value["candidate_id"] for value in candidates] == [
        "candidate-1684",
        "candidate-1704",
    ]
