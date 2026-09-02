"""v10905 native maxT null for the causal bar-5 AND-gate candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as boundary
import numpy as np

VALIDATION_VERSION = 10905
SELECTION_RANGE = [10805, 10904]
REPETITIONS = 500
PERCENTILE = 0.95
SEED = 20260902
SAFE_SHIFT_MINIMUM = 20


def _compound(values):
    return float(np.prod(1.0 + values) - 1.0)


def _development_route(root: Path, source_path: Path):
    boundary._configure()
    campaign = boundary.logical.clock.parent.parent.sparse_veto.campaign
    if campaign.base.prior.parent._sha(source_path) != campaign.base.prior.SOURCE_SHA256:
        raise RuntimeError("V10905_SOURCE_HASH_CHANGED")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    campaign.base.prior.cash._configure()
    base_ids = tuple(
        dict.fromkeys(
            (
                campaign.base.prior.route.MODERN_PARENT,
                campaign.base.prior.route.TRANSFER_PARENT,
                campaign.base.prior.cash.FALLBACK_PARENT,
            )
        )
    )
    required = tuple(dict.fromkeys((*base_ids, *campaign.base.FILL_PARENTS)))
    development = v34.Cube(root, "alpaca", 0)
    factors = sector.SectorFlowLeadershipCube(root, "alpaca", 0)
    state = campaign.base.prior.parent.cross.Cube(root, "alpaca", 0)
    models = {
        item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    parents = {
        item: campaign.base.prior.parent._parent_streams(
            development, source_map[item], models[item]
        )
        for item in required
    }
    core_model = campaign.base.state._fit_state(
        state, campaign.base.CORE_LOW_DISPERSION_TREND, 0.20
    )
    override_model = campaign.base.state._fit_state(
        state, campaign.base.CORE_OVERSOLD_REPAIR, 0.35
    )
    _, transfer_state = campaign.base.prior.route._base_state(
        state, core_model, override_model
    )
    gate_model = campaign.base.prior.route._fit_gate(
        development,
        parents[campaign.base.prior.route.TRANSFER_PARENT][0],
        transfer_state,
        campaign.base.prior.route.FACTOR_SETS[campaign.base.prior.BASE_FAMILY],
        campaign.base.prior.BASE_QUANTILE,
        campaign.base.prior.BASE_ALPHA,
    )
    fill_model = campaign.base.state._fit_state(
        state, campaign.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    late = campaign._route(
        development, state, parents, core_model, override_model, gate_model, fill_model
    )[0]
    opening = boundary.logical.clock.parent.parent._opening_by_late_stream[id(late)]
    return campaign, development, factors, late, opening


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if (
        selection.get("status") != "COMPLETE"
        or selection.get("version_range") != SELECTION_RANGE
    ):
        raise RuntimeError("V10905_SELECTION_NOT_FROZEN_COMPLETE")
    eligible = [item for item in selection["records"] if item["strict_pre_factory_null_pass"]]
    if len(eligible) != 1:
        raise RuntimeError("V10905_ELIGIBLE_CANDIDATE_COUNT_CHANGED")
    campaign, development, factors, late, opening = _development_route(
        args.root, args.source
    )
    index = np.flatnonzero(development.masks()["development_all"])
    exposures = []
    for item in eligible:
        definition = item["definition"]
        model = campaign.quality._fit(
            factors,
            late,
            late.active,
            campaign.FACTOR_SETS[definition["factor_set"]],
            float(definition["score_quantile"]),
            float(definition["ridge_alpha"]),
        )
        score = campaign.quality._score(factors, model)
        exposures.append(
            np.where(
                np.isfinite(score[index]) & (score[index] >= model["threshold"]),
                1.0,
                boundary.logical.clock.parent.parent.LOW_EXPOSURE,
            )
        )
    late_values = late.values[index]
    opening_values = opening.values[index]
    observed = [
        _compound(opening_values + late_values * exposure) for exposure in exposures
    ]
    rng = np.random.default_rng(SEED)
    permutation_max, shift_max = [], []
    for _ in range(REPETITIONS):
        permutation_max.append(
            max(
                _compound(
                    opening_values + late_values * exposure[rng.permutation(len(index))]
                )
                for exposure in exposures
            )
        )
        shift_max.append(
            max(
                _compound(
                    opening_values
                    + late_values
                    * np.roll(
                        exposure,
                        int(rng.integers(SAFE_SHIFT_MINIMUM, len(index) - 4)),
                    )
                )
                for exposure in exposures
            )
        )
    permutation_threshold = float(np.quantile(permutation_max, PERCENTILE))
    shift_threshold = float(np.quantile(shift_max, PERCENTILE))
    records = []
    for item, profit in zip(eligible, observed, strict=True):
        records.append(
            {
                "candidate_id": item["candidate_id"],
                "observed_profit": profit,
                "session_signal_permutation_maxT_95pct": permutation_threshold,
                "safe_circular_shift_maxT_95pct": shift_threshold,
                "passed": profit > permutation_threshold and profit > shift_threshold,
            }
        )
    evidence = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "validation_version": VALIDATION_VERSION,
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
    v34.v12._atomic(args.output, evidence)
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
