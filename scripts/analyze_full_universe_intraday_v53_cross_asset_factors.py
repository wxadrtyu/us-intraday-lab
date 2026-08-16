"""Development-only audit of cross-asset state factors for leveraged ETFs."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import numpy as np
import search_full_universe_intraday_v12_robustness as v12

PERIODS = ("train_2022_2023", "2024", "2025")
DECISIONS = (17, 20, 23, 26, 29, 35, 41, 47)
HOLDING_BARS = (30, 42)
ASSETS = (3, 4)
NEW_FACTORS = (
    "spy_current",
    "qqq_current",
    "iwm_current",
    "qqq_minus_iwm",
    "sector_breadth",
    "sector_dispersion",
    "cyclical_minus_defensive",
    "tech_minus_market",
    "leverage_residual",
    "risk_asset_agreement",
)


class Cube(v34.Cube):
    """Extend the causal factor cube with cross-asset state variables."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "qqq_minus_iwm" in output:
            return output
        current = self._features(decision)["current"]
        sectors = current[:, v12.SECTORS]
        breadth = np.nanmean(sectors > 0.0, axis=1)
        sector_count = np.isfinite(sectors).sum(axis=1)
        sector_mean = np.divide(
            np.nansum(sectors, axis=1),
            sector_count,
            out=np.full(len(current), np.nan),
            where=sector_count > 0,
        )
        dispersion = np.sqrt(
            np.divide(
                np.nansum((sectors - sector_mean[:, None]) ** 2, axis=1),
                sector_count,
                out=np.full(len(current), np.nan),
                where=sector_count > 0,
            )
        )

        def safe_mean(indices: tuple[int, ...]) -> np.ndarray:
            values = current[:, indices]
            count = np.isfinite(values).sum(axis=1)
            return np.divide(
                np.nansum(values, axis=1),
                count,
                out=np.full(len(current), np.nan),
                where=count > 0,
            )

        cyclical = safe_mean((6, 7, 8, 9, 10, 15))
        defensive = safe_mean((11, 13, 14))
        agreement = np.nanmean(current[:, (0, 1, 2)] > 0.0, axis=1)
        repeated = {
            "spy_current": current[:, 0],
            "qqq_current": current[:, 1],
            "iwm_current": current[:, 2],
            "qqq_minus_iwm": current[:, 1] - current[:, 2],
            "sector_breadth": breadth,
            "sector_dispersion": dispersion,
            "cyclical_minus_defensive": cyclical - defensive,
            "tech_minus_market": current[:, 10] - current[:, 0],
            "risk_asset_agreement": agreement,
        }
        for name, values in repeated.items():
            output[name] = np.repeat(values[:, None], len(v12.SYMBOLS), axis=1)
        leverage_residual = np.full_like(current, np.nan)
        leverage_residual[:, 3] = current[:, 3] - 3.0 * current[:, 1]
        leverage_residual[:, 4] = current[:, 4] - 3.0 * current[:, 10]
        output["leverage_residual"] = leverage_residual
        return output


def _audit(values: np.ndarray, label: np.ndarray, finite: np.ndarray, mask: np.ndarray) -> dict:
    selected = mask[:, None] & finite & np.isfinite(values)
    return {
        "ic": v35._spearman(values[selected], label[selected]),
        "observations": int(selected.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    cube = Cube(args.root, "alpaca", 0)
    masks = cube.masks()
    records = []
    for decision in DECISIONS:
        for holding in HOLDING_BARS:
            exit_bar = decision + 1 + holding
            if exit_bar >= cube.opens.shape[1]:
                continue
            specification = {
                "name": "cross_asset_audit",
                "decision": decision,
                "exit": exit_bar,
                "assets": ASSETS,
            }
            matrix, label, finite = v34._matrix(cube, specification, NEW_FACTORS)
            results = {}
            stable = []
            for index, factor in enumerate(NEW_FACTORS):
                period_results = {
                    period: _audit(matrix[:, :, index], label, finite, masks[period])
                    for period in PERIODS
                }
                results[factor] = period_results
                ics = [float(period_results[period]["ic"]) for period in PERIODS]
                if all(np.isfinite(ics)) and min(ics) > 0.0:
                    stable.append({"factor": factor, "direction": 1, "minimum_abs_ic": min(ics)})
                elif all(np.isfinite(ics)) and max(ics) < 0.0:
                    stable.append(
                        {
                            "factor": factor,
                            "direction": -1,
                            "minimum_abs_ic": min(abs(value) for value in ics),
                        }
                    )
            stable.sort(key=lambda item: float(item["minimum_abs_ic"]), reverse=True)
            records.append(
                {
                    "decision": decision,
                    "holding_bars": holding,
                    "exit": exit_bar,
                    "factors": results,
                    "stable_all_periods": stable,
                }
            )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "factor signs use 2022-2025 only; 2026 is not read",
        "periods": PERIODS,
        "factors": NEW_FACTORS,
        "scan": {
            "planned_audits": sum(
                decision + 1 + holding < cube.opens.shape[1]
                for decision in DECISIONS
                for holding in HOLDING_BARS
            ),
            "evaluated_audits": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "stable": [
                    {
                        "decision": record["decision"],
                        "holding_bars": record["holding_bars"],
                        "factors": record["stable_all_periods"],
                    }
                    for record in records
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
