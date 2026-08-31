"""v9097 architecture-native maxT null for soft sparse-gap candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v8997_v9096_soft_sparse_gap_veto as soft
import numpy as np

VALIDATION_VERSION = 9097
REPETITIONS = 500
PERCENTILE = 0.95
SEED = 20260831
SAFE_SHIFT_MINIMUM = 20


def _compound(values):
    return float(np.prod(1.0 + values) - 1.0)


def _route_and_factors(root, source_path):
    soft._configure()
    campaign = soft.sparse_veto.campaign
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
    route = campaign._route(
        development,
        state,
        parents,
        core_model,
        override_model,
        gate_model,
        fill_model,
    )[0]
    return development, factors, route


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    eligible = [item for item in selection["records"] if item["strict_pre_factory_null_pass"]]
    if selection["status"] != "COMPLETE" or selection["version_range"] != [8997, 9096]:
        raise RuntimeError("V8997_SELECTION_NOT_FROZEN_COMPLETE")
    if len(eligible) != 4:
        raise RuntimeError("V9097_ELIGIBLE_CANDIDATE_COUNT_CHANGED")
    development, factors, route = _route_and_factors(args.root, args.source)
    index = np.flatnonzero(development.masks()["development_all"])
    route_values = route.values[index]
    exposures = []
    for item in eligible:
        definition = item["definition"]
        model = soft.sparse_veto.campaign.quality._fit(
            factors,
            route,
            route.active,
            soft.sparse_veto.campaign.FACTOR_SETS[definition["factor_set"]],
            float(definition["score_quantile"]),
            float(definition["ridge_alpha"]),
        )
        score = soft.sparse_veto.campaign.quality._score(factors, model)
        allowed = np.isfinite(score) & (score >= model["threshold"])
        exposures.append(np.where(allowed[index], 1.0, soft.LOW_EXPOSURE))
    observed = [_compound(route_values * exposure) for exposure in exposures]
    rng = np.random.default_rng(SEED)
    permutation_max, shift_max = [], []
    for _ in range(REPETITIONS):
        permutation_max.append(
            max(_compound(route_values * exposure[rng.permutation(len(index))]) for exposure in exposures)
        )
        shift_max.append(
            max(
                _compound(
                    route_values
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
        passed = profit > permutation_threshold and profit > shift_threshold
        records.append(
            {
                "candidate_id": item["candidate_id"],
                "observed_profit": profit,
                "session_signal_permutation_maxT_95pct": permutation_threshold,
                "safe_circular_shift_maxT_95pct": shift_threshold,
                "passed": passed,
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
    print(json.dumps({key: evidence[key] for key in ("status", "candidate_count", "native_factory_null_passes", "evidence_sha256")}))


if __name__ == "__main__":
    main()
