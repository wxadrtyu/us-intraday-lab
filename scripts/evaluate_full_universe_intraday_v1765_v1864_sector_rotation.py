"""Independent sector multifactor campaign, frozen before any outcome inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evaluate_full_universe_intraday_v146_v245_anchored_ensembles as anchored
import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as template
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import IntradayPathCube

from us_intraday_lab.fast_intraday_research import metrics

prior = template.prior
SECTORS = np.arange(5, 16)
PROPOSAL = (
    Path(__file__).resolve().parents[1]
    / "research/proposals/full_universe_intraday_v1765_v1864/proposal.json"
)
SCENARIOS = ((prior.v34.STANDARD_COST, 0), (prior.v34.STRESS_COST, 0), (prior.v34.STANDARD_COST, 1))
SCENARIO_NAMES = ("standard", "cost_18bp", "delay_5min_9bp")


class SectorCube(IntradayPathCube):
    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "sector_relative" not in output:
            current = self._features(decision)["current"]
            values = current[:, SECTORS]
            count = np.isfinite(values).sum(axis=1)
            mean = np.divide(
                np.nansum(values, axis=1), count, out=np.full(len(values), np.nan), where=count >= 2
            )
            relative = np.full_like(current, np.nan)
            relative[:, SECTORS] = values - mean[:, None]
            output["sector_relative"] = relative
            for name, source in (("sector_rank", current), ("sector_prior_rank", self.prior20)):
                ranked = np.full_like(source, np.nan)
                ranked[:, SECTORS] = (
                    pd.DataFrame(source[:, SECTORS])
                    .rank(axis=1, method="average", pct=True)
                    .to_numpy()
                )
                output[name] = ranked
        return output


def configure(proposal: dict) -> None:
    prior.ASSETS = SECTORS.copy()
    template.FIRST_VERSION, template.LAST_VERSION = proposal["version_range"]
    template.FAMILIES = tuple(
        (name, tuple(factors), tuple(signs)) for name, factors, signs in proposal["families"]
    )
    template.SCHEDULES = tuple(tuple(item) for item in proposal["schedules"])
    template.STATE_MODES = tuple(proposal["state_modes"])
    for key, name in (
        ("score_quantiles", "SCORE_QUANTILES"),
        ("confirmations", "CONFIRMATIONS"),
        ("targets", "TARGETS"),
        ("lookbacks", "LOOKBACKS"),
        ("state_quantiles", "STATE_QUANTILES"),
    ):
        setattr(template, name, tuple(proposal["grid"][key]))


def stress_rank(observations: tuple[dict, ...]) -> tuple[float, ...]:
    oos = [item["development_oos_2024_2025"] for item in observations]
    return (
        min(float(item["annualized_return"]) for item in oos),
        -max(float(item["max_drawdown"]) for item in oos),
        min(float(item["information_ratio"]) for item in oos),
        min(
            float(observations[0][name]["annualized_return"]) for name in template.DEVELOPMENT_NAMES
        ),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract() -> dict:
    # Hash loaded research dependencies, not unrelated files or credentials.
    paths = {Path(__file__).resolve()}
    for name, module in tuple(sys.modules.items()):
        if name.startswith(
            (
                "evaluate_full_universe",
                "search_full_universe",
                "analyze_full_universe",
                "us_intraday_lab.fast_intraday_research",
            )
        ) and getattr(module, "__file__", None):
            paths.add(Path(module.__file__).resolve())
    return {
        "proposal_sha256": _sha(PROPOSAL),
        "code": {path.name: _sha(path) for path in sorted(paths)},
        "alpaca_manifests": prior.v12.ALPACA,
        "historical_manifests": prior.v12.HISTORICAL,
    }


def _baseline(cube: SectorCube, root: Path) -> tuple[prior.v12.ReturnStream, dict]:
    record_path = root / "artifacts/research/v1159_v1258/full-universe-intraday-v1254-exact.json"
    component_path = (
        root / "artifacts/research/v1563_v1662_sources/full-universe-intraday-v60-exact.json"
    )
    record = next(
        item
        for item in json.loads(record_path.read_text())["records"]
        if item["candidate_id"] == "lev-v1254-de6c18bd7658f359"
    )
    component = next(
        item
        for item in json.loads(component_path.read_text())["records"]
        if item["candidate_id"] == "lev-v60-b528b229cefeace2"
    )
    models = prior.v44._fit(cube, (20, 23, 26, 29), 72)
    anchor = anchored._v45_streams(cube, models)
    sleeve = anchored._component_streams(cube, component)
    definition = record["definition"]
    matrix = prior._state_matrix(cube, definition["state_clock"])
    train = cube.masks()["train_2022_2023"]
    coefficients = definition["state_coefficients"]
    means = {name: float(np.nanmean(matrix[name][train])) for name in coefficients}
    scales = {name: max(1e-8, float(np.nanstd(matrix[name][train]))) for name in coefficients}
    score = prior._state_score(matrix, coefficients, means, scales)
    weight = np.where(np.isfinite(score) & (score >= definition["state_threshold"]), 0.16, 0.0)
    streams = tuple(
        prior.v12.ReturnStream(
            (1 - weight) * left.values + weight * right.values,
            (1 - weight) * left.benchmark + weight * right.benchmark,
            left.active | ((weight > 0) & right.active),
            left.component_trades + (weight > 0) * right.component_trades,
        )
        for left, right in zip(anchor, sleeve, strict=True)
    )
    observations = {
        name: prior.v47._observe(cube, stream, True)
        for name, stream in zip(SCENARIO_NAMES, streams, strict=True)
    }
    for name in SCENARIO_NAMES:
        for period in (
            "train_2022_2023",
            "2024",
            "2025",
            "development_oos_2024_2025",
            "consumed_2026q1",
            "consumed_2026_all",
        ):
            for field in ("annualized_return", "max_drawdown", "information_ratio", "total_return"):
                if not np.isclose(
                    observations[name][period][field],
                    record[name][period][field],
                    rtol=1e-9,
                    atol=1e-10,
                ):
                    raise RuntimeError(f"V1254_BASELINE_PARITY_FAILED:{name}:{period}:{field}")
    return streams[0], {
        "candidate_id": record["candidate_id"],
        "source_sha256": _sha(record_path),
        "component_sha256": _sha(component_path),
        "parity_passed": True,
        "observations": observations,
    }


def correlation_report(cube, values: np.ndarray, baseline: np.ndarray) -> dict[str, float | None]:
    result = {}
    for name in ("2024", "2025", "development_oos_2024_2025"):
        mask = cube.masks()[name]
        left, right = values[mask], baseline[mask]
        result[name] = (
            float(np.corrcoef(left, right)[0, 1])
            if np.isfinite(left).all()
            and np.isfinite(right).all()
            and np.std(left) > 1e-12
            and np.std(right) > 1e-12
            else None
        )
    return result


def _historical_scenarios(cube, selected: dict) -> tuple:
    parameters, model = selected["parameters"], selected["model"]
    # Populate immutable factor caches before parallel scenario evaluation.
    cube.factors(parameters["decision"])
    cube.factors(parameters["decision"] - 3)

    def raw(scenario):
        cost, delay = scenario
        return prior._rule_raw(
            cube,
            parameters,
            np.asarray(model["mean"]),
            np.asarray(model["scale"]),
            parameters["score_threshold"],
            cost,
            delay,
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        streams = tuple(pool.map(raw, SCENARIOS))
    if parameters["state_mode"] != "unfiltered":
        score = template._state_score(
            cube, parameters["decision"], model["state_means"], model["state_scales"]
        )
        allowed = np.isfinite(score) & (score >= parameters["state_threshold"])
        streams = tuple(prior._mask_stream(stream, allowed) for stream in streams)
    return template._scale(streams, parameters["target_volatility"], parameters["lookback"])


def _record(development, historical, version, cells, selected, total, baseline):
    result = template._record(development, historical, version, cells, selected, total)
    result["definition"].update(
        {
            "assets": SECTORS.tolist(),
            "symbols": [prior.v12.SYMBOLS[i] for i in SECTORS],
            "anchor": None,
            "maximum_gross": 1.0,
            "rank_mode": "stress_floor",
        }
    )
    result["candidate_id"] = f"sector-v{version}-" + prior._identity(result["definition"])
    corr = correlation_report(development, selected["streams"][0].values, baseline.values)
    result["v1254_daily_return_correlation"] = corr
    result["historical_stress"] = {
        name: prior.v47._observe(historical, stream, True)["historical_2018_2020"]
        for name, stream in zip(
            SCENARIO_NAMES, _historical_scenarios(historical, selected), strict=True
        )
    }
    stress_starts, stress_folds = {}, {}
    for name, stream in zip(SCENARIO_NAMES, selected["streams"], strict=True):
        stress_starts[name] = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start)
            )
            stress_starts[name][start] = metrics(
                stream.values[mask], stream.benchmark[mask], stream.active[mask]
            )
        stress_folds[name] = [
            metrics(stream.values[index], stream.benchmark[index], stream.active[index])
            for index in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
        ]
    result["all_scenario_start_dates"] = stress_starts
    result["all_scenario_folds"] = stress_folds
    result["gates"].update(
        {
            "consumed_2026q1_total_above_5pct": result["standard"]["consumed_2026q1"][
                "total_return"
            ]
            > 0.05,
            "all_scenario_start_dates_positive": all(
                item["annualized_return"] > 0
                for group in stress_starts.values()
                for item in group.values()
            ),
            "all_scenario_four_positive_folds": all(
                sum(item["annualized_return"] > 0 for item in group) >= 4
                for group in stress_folds.values()
            ),
            "independent_from_v1254_correlation": all(
                value is not None and abs(value) <= 0.65 for value in corr.values()
            ),
        }
    )
    result["pre_factory_null_pass"] = all(
        value for key, value in result["gates"].items() if key != "cumulative_bonferroni_5pct"
    )
    result["all_reference_gates_pass"] = all(result["gates"].values())
    result["native_factory_null_status"] = (
        "REQUIRES_PREREGISTERED_VALIDATION"
        if result["pre_factory_null_pass"]
        else "NOT_RUN_PRE_NULL_FAILED"
    )
    result["admitted"] = False
    return result


def _factor_audit(cube, proposal):
    rows, baselines = [], {}
    factors = sorted({factor for _, names, _ in proposal["families"] for factor in names})
    for decision, exit_bar in proposal["schedules"]:
        entry = decision + 1
        values = cube.opens[:, exit_bar, SECTORS] / cube.opens[:, entry, SECTORS] - 1.0
        valid = (
            np.isfinite(values)
            & (cube.first[:, entry, SECTORS] <= entry * 5)
            & (cube.first[:, exit_bar, SECTORS] <= exit_bar * 5)
        )
        count = valid.sum(axis=1)
        benchmark = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
        active = (count > 0) & np.isfinite(benchmark)
        gross = np.divide(
            np.where(valid, values, 0).sum(axis=1),
            count,
            out=np.zeros(len(values)),
            where=count > 0,
        )
        stream = prior.v12.ReturnStream(
            np.where(active, gross - 0.0009, 0),
            np.where(active, benchmark, 0),
            active,
            active.astype(int),
        )
        baselines[str((decision, exit_bar))] = prior.v47._observe(cube, stream, True)
        for factor in factors:
            x = cube.factors(decision)[factor][:, SECTORS]
            for period in template.DEVELOPMENT_NAMES:
                mask = valid & np.isfinite(x) & cube.masks()[period][:, None]
                left, right = x[mask], values[mask]
                ic = (
                    float(pd.Series(left).corr(pd.Series(right), method="spearman"))
                    if len(left) > 2 and np.std(left) > 0 and np.std(right) > 0
                    else None
                )
                rows.append(
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "factor": factor,
                        "period": period,
                        "observations": int(mask.sum()),
                        "spearman_ic": ic,
                    }
                )
    return {
        "role": "development descriptive only; no family changes or pruning",
        "factors": rows,
        "equal_weight_sector_standard": baselines,
        "cash_total_return": 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    configure(proposal)
    specs = template.specifications()
    if len(specs) != 100 or proposal["planned_cells"] != 12800:
        raise RuntimeError("PREREGISTRATION_MISMATCH")
    contract = _contract()
    contract_id = prior._identity(contract)
    contract_path = args.output_dir / "contract.json"
    if contract_path.exists() and json.loads(contract_path.read_text()) != contract:
        raise RuntimeError("CHECKPOINT_IDENTITY_CHANGED")
    prior.v12._atomic(contract_path, contract)
    development = SectorCube(args.root, "alpaca", 0)
    historical = SectorCube(args.root, "historical", 0)
    baseline, baseline_report = _baseline(development, Path(__file__).resolve().parents[1])
    audit_path = args.output_dir / "baselines-factor-audit.json"
    prior.v12._atomic(
        audit_path, {"v1254": baseline_report, **_factor_audit(development, proposal)}
    )
    print(
        json.dumps(
            {"baseline_parity": True, "initialization_seconds": time.perf_counter() - started}
        ),
        flush=True,
    )
    records, versions = [], []
    for offset, (family, schedule, mode) in enumerate(specs):
        version = proposal["version_range"][0] + offset
        path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
        version_started = time.perf_counter()
        if path.exists():
            payload = json.loads(path.read_text())
            if (
                payload.get("contract_id") != contract_id
                or payload.get("version") != version
                or payload.get("status") != "COMPLETE"
            ):
                raise RuntimeError("INVALID_VERSION_CHECKPOINT")
        else:
            cells = template._cells(development, family, schedule, mode)
            for cell in cells:
                cell["rank"] = stress_rank(cell["observations"])
            cells.sort(key=lambda cell: cell["rank"], reverse=True)
            frontier = [
                _record(
                    development,
                    historical,
                    version,
                    cells,
                    cell,
                    proposal["cumulative_comparison_cells"],
                    baseline,
                )
                for cell in cells[:3]
            ]
            payload = {
                "status": "COMPLETE",
                "version": version,
                "contract_id": contract_id,
                "hypothesis": {"family": family, "schedule": schedule, "state_mode": mode},
                "scan": {
                    "evaluated_cells": len(cells),
                    "elapsed_seconds": time.perf_counter() - version_started,
                },
                "records": frontier,
            }
            prior.v12._atomic(path, payload)
        records.extend(payload["records"])
        best = payload["records"][0]
        versions.append(
            {
                "version": version,
                **payload["scan"],
                "best_candidate": best["candidate_id"],
                "stress_floor": best["development_rank"][0],
                "pre_null_hits": sum(item["pre_factory_null_pass"] for item in payload["records"]),
            }
        )
        summary = {
            "status": "COMPLETE" if len(versions) == 100 else "RUNNING",
            "contract_id": contract_id,
            "version_range": proposal["version_range"],
            "completed_versions": len(versions),
            "evaluated_cells": sum(item["evaluated_cells"] for item in versions),
            "cumulative_comparison_cells": proposal["cumulative_comparison_cells"],
            "frozen_frontier_records": len(records),
            "pre_factory_null_hits": sum(item["pre_factory_null_pass"] for item in records),
            "admitted": 0,
            "rejection_reason_counts": dict(template._failed(records)),
            "elapsed_seconds": time.perf_counter() - started,
            "versions": versions,
        }
        prior.v12._atomic(args.output_dir / "summary.json", summary)
        print(json.dumps({"progress": len(versions), **versions[-1]}), flush=True)


if __name__ == "__main__":
    main()
