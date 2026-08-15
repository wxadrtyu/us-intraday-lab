"""Development-only ensemble of independently frozen v20/v21 frontiers."""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v17_fixed_asset_state as v17
import search_full_universe_intraday_v20_unified_sources as v20
import search_full_universe_intraday_v21_vwap_structure as v21

from us_intraday_lab.fast_intraday_research import metrics


def _weighted(streams: list[v12.ReturnStream], weights: tuple[float, ...]) -> v12.ReturnStream:
    return v12.ReturnStream(
        np.average(np.vstack([item.values for item in streams]), axis=0, weights=weights),
        np.average(np.vstack([item.benchmark for item in streams]), axis=0, weights=weights),
        np.logical_or.reduce([item.active for item in streams]),
        np.vstack([item.component_trades for item in streams]).sum(axis=0),
    )


class Source:
    def __init__(self, root: Path, name: str, historical: bool = False) -> None:
        provider = "historical" if historical else "alpaca"
        self.name = name
        if name == "v20":
            self.prior = v15.Cube(root, provider, 0)
            self.fixed = v17.Cube(root, provider, 0)
            self.volume = v20.VolumeCube(root, provider, 0)
            self.base = self.prior
        else:
            self.base = v21.Cube(root, provider, 0)

    def replay(self, specs: list[dict[str, Any]], cost: float, delay: int) -> v12.ReturnStream:
        if self.name == "v20":
            return v13._combine(
                [
                    v20._dispatch(self.prior, self.fixed, self.volume, spec, cost, delay)
                    for spec in specs
                ]
            )
        return v13._combine([self.base.replay_spec(spec, cost, delay) for spec in specs])


def _load(path: Path, count: int) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Stratify across the stored development-ranked frontier without consulting 2026.
    frontier = payload["frontier"]
    indices = np.linspace(0, len(frontier) - 1, min(count, len(frontier)), dtype=int)
    return [frontier[index] for index in np.unique(indices)]


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-source", default=24, type=int)
    parser.add_argument("--frontier-size", default=300, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    artifact_root = args.root / "artifacts" / "accelerated_research"
    records = {
        "v20": _load(
            artifact_root / "full-universe-intraday-v20-unified-sources-exact.json",
            args.top_per_source,
        ),
        "v21": _load(
            artifact_root / "full-universe-intraday-v21-vwap-structure-exact.json",
            args.top_per_source,
        ),
    }
    sources = {name: Source(args.root, name) for name in records}
    cached: dict[tuple[str, str, float, int], v12.ReturnStream] = {}

    def replay(name: str, record: dict[str, Any], cost: float, delay: int) -> v12.ReturnStream:
        key = (name, record["candidate_id"], cost, delay)
        if key not in cached:
            cached[key] = sources[name].replay(record["specifications"], cost, delay)
        return cached[key]

    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    trials = 0
    products = itertools.product(records["v20"], records["v21"], (0.25, 0.5, 0.75))
    for serial, (left, right, left_weight) in enumerate(products, 1):
        weights = (left_weight, 1.0 - left_weight)
        streams = [replay("v20", left, 0.0009, 0), replay("v21", right, 0.0009, 0)]
        cost_streams = [replay("v20", left, 0.0018, 0), replay("v21", right, 0.0018, 0)]
        delay_streams = [replay("v20", left, 0.0009, 1), replay("v21", right, 0.0009, 1)]
        standard = v13._observe(sources["v20"].base, _weighted(streams, weights))
        cost = v13._observe(sources["v20"].base, _weighted(cost_streams, weights))
        delay = v13._observe(sources["v20"].base, _weighted(delay_streams, weights))
        weakest = min(float(standard[name]["annualized_return"]) for name in v15.DEVELOPMENT_NAMES)
        oos_cost = cost["development_oos_2024_2025"]
        rank = (weakest, float(oos_cost["annualized_return"]), float(oos_cost["information_ratio"]))
        item = {
            "legs": [
                {
                    "source": "v20",
                    "candidate_id": left["candidate_id"],
                    "weight": weights[0],
                    "specifications": left["specifications"],
                },
                {
                    "source": "v21",
                    "candidate_id": right["candidate_id"],
                    "weight": weights[1],
                    "specifications": right["specifications"],
                },
            ],
            "development_rank": rank,
            "standard": standard,
            "cost_18bp": cost,
            "delay_5min_9bp": delay,
        }
        trials += 1
        entry = (rank, serial, item)
        if len(heap) < args.frontier_size:
            heapq.heappush(heap, entry)
        elif rank > heap[0][0]:
            heapq.heapreplace(heap, entry)
    frontier = [item for _, _, item in sorted(heap, reverse=True)]

    historical = {name: Source(args.root, name, True) for name in records}
    masks = sources["v20"].base.masks()
    folds = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    diagnostic_hits = 0
    eligible = 0
    for item in frontier:
        weights = tuple(float(leg["weight"]) for leg in item["legs"])
        standard_stream = _weighted(
            [
                sources[leg["source"]].replay(leg["specifications"], 0.0009, 0)
                for leg in item["legs"]
            ],
            weights,
        )
        historical_stream = _weighted(
            [
                historical[leg["source"]].replay(leg["specifications"], 0.0009, 0)
                for leg in item["legs"]
            ],
            weights,
        )
        historical_obs = v13._observe(historical["v20"].base, historical_stream)
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * trials)
        gates = {
            "standard_primary": v15._primary(item["standard"]),
            "cost_18bp_primary": v15._primary(item["cost_18bp"]),
            "delay_5min_primary": v15._primary(item["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(float(x["annualized_return"]) > 0 for x in fold_obs)
            >= 4,
            "historical_positive_mdd_below_20pct": float(hist["annualized_return"]) > 0
            and float(hist["max_drawdown"]) < 0.20,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        item["candidate_id"] = v12._identity(item["legs"], "lev-v25e-")
        item["historical_cross_source"] = historical_obs
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {"total_trials": trials, "bonferroni_p": bonferroni}
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "v20/v21 inputs stratified over their development-ranked frozen frontiers; ensemble rank frozen on 2022-2025 before attaching 2026",
        "execution_contract": "long-only; weighted gross<=1; no overnight",
        "scan": {
            "source_candidates": {k: len(v) for k, v in records.items()},
            "total_trials": trials,
            "frontier_size": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": frontier,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    if frontier:
        best = max(
            frontier, key=lambda x: float(x["standard"]["consumed_2026_all"]["total_return"])
        )
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "historical": best["historical_cross_source"]["historical_2018_2020"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
