"""Native maxT null for all pre-null v11098 portfolio-vol overlays."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v11307_v11406_v11098_portfolio_vol as campaign
import numpy as np

REPETITIONS = 500
PERCENTILE = 0.95
SAFE_SHIFT_MINIMUM = 20
SEED = 20260903


def _compound(values) -> float:
    return float(np.prod(1.0 + values) - 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--base-selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("status") != "COMPLETE" or selection.get("version_range") != [
        11307,
        11406,
    ]:
        raise RuntimeError("V11407_SELECTION_NOT_FROZEN_COMPLETE")
    eligible = [item for item in selection["records"] if item["strict_pre_factory_null_pass"]]
    if len(eligible) != 55:
        raise RuntimeError("V11407_ELIGIBLE_COUNT_CHANGED")
    development, _historical, base_streams, _hist_streams = campaign._base_streams(
        args.root, args.source, args.base_selection
    )
    index = np.flatnonzero(development.masks()["development_all"])
    base_values = base_streams[0].values[index]
    exposures = []
    for item in eligible:
        definition = item["definition"]
        full = campaign._portfolio_exposure(
            base_streams[0].values,
            int(definition["lookback"]),
            float(definition["target"]),
            float(definition["floor"]),
        )
        exposures.append(full[index])
    observed = [_compound(base_values * exposure) for exposure in exposures]
    rng = np.random.default_rng(SEED)
    permutation_max = []
    shift_max = []
    for _ in range(REPETITIONS):
        permutation_max.append(
            max(
                _compound(base_values * exposure[rng.permutation(len(index))])
                for exposure in exposures
            )
        )
        shift = int(rng.integers(SAFE_SHIFT_MINIMUM, len(index) - 4))
        shift_max.append(
            max(_compound(base_values * np.roll(exposure, shift)) for exposure in exposures)
        )
    permutation_threshold = float(np.quantile(permutation_max, PERCENTILE))
    shift_threshold = float(np.quantile(shift_max, PERCENTILE))
    records = []
    for item, profit in zip(eligible, observed, strict=True):
        records.append(
            {
                "candidate_id": item["candidate_id"],
                "observed_profit": profit,
                "portfolio_exposure_session_permutation_maxT_95pct": permutation_threshold,
                "portfolio_exposure_safe_circular_shift_maxT_95pct": shift_threshold,
                "passed": profit > permutation_threshold and profit > shift_threshold,
            }
        )
    evidence = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "validation_version": 11407,
        "candidate_count": len(records),
        "repetitions": REPETITIONS,
        "percentile": PERCENTILE,
        "seed": SEED,
        "native_factory_null_passes": sum(item["passed"] for item in records),
        "records": records,
    }
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    campaign.v34.v12._atomic(args.output, evidence)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "candidate_count": evidence["candidate_count"],
                "native_factory_null_passes": evidence["native_factory_null_passes"],
                "evidence_sha256": evidence["evidence_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
