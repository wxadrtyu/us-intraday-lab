"""Sector-breadth and cross-sectional dispersion rotation search."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import search_full_universe_intraday_v23_beta_residual as v23

UNIVERSES = v23.UNIVERSES
SLOTS = v23.SLOTS
SECTORS = UNIVERSES["sectors"]


class Cube(v23.Cube):
    """Exact cube with causal sector breadth and dispersion features."""

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        feature = self._features(int(p["decision"]))
        current = feature["current"]
        recent = feature["recent"]
        sector = current[:, SECTORS]
        valid = np.isfinite(sector)
        valid_count = valid.sum(axis=1)
        breadth = np.divide(
            ((sector > 0) & valid).sum(axis=1),
            valid_count,
            out=np.full(len(self.sessions), np.nan),
            where=valid_count >= 7,
        )
        sector_sum = np.where(valid, sector, 0.0).sum(axis=1)
        sector_mean = np.divide(
            sector_sum,
            valid_count,
            out=np.zeros(len(self.sessions)),
            where=valid_count > 0,
        )
        dispersion = np.sqrt(
            np.divide(
                np.where(valid, (sector - sector_mean[:, None]) ** 2, 0.0).sum(axis=1),
                valid_count,
                out=np.full(len(self.sessions), np.nan),
                where=valid_count > 0,
            )
        )
        selected = SECTORS[np.argmax(np.where(valid, sector, -np.inf), axis=1)]
        leader = current[self.rows, selected]
        leader_recent = recent[self.rows, selected]
        ordered = np.sort(np.where(valid, sector, np.inf), axis=1)
        median = ordered[self.rows, np.maximum(valid_count - 1, 0) // 2]
        median[valid_count == 0] = np.nan
        eligible = valid_count >= 7
        if family == "broad_risk_on":
            eligible &= (
                (breadth >= float(p["breadth_floor"]))
                & (median >= float(p["median_floor"]))
                & (dispersion <= float(p["dispersion_ceiling"]))
                & (leader >= float(p["leader_floor"]))
                & (leader_recent >= float(p["recent_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "narrow_leadership":
            eligible &= (
                (breadth >= float(p["breadth_floor"]))
                & (breadth <= float(p["breadth_ceiling"]))
                & (dispersion >= float(p["dispersion_floor"]))
                & ((leader - median) >= float(p["spread_floor"]))
                & (leader_recent >= float(p["recent_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "breadth_recovery":
            recent_sector = recent[:, SECTORS]
            recent_valid = np.isfinite(recent_sector)
            recent_count = recent_valid.sum(axis=1)
            recent_breadth = np.divide(
                ((recent_sector > 0) & recent_valid).sum(axis=1),
                recent_count,
                out=np.full(len(self.sessions), np.nan),
                where=recent_count >= 7,
            )
            eligible &= (
                (breadth >= float(p["breadth_floor"]))
                & (recent_breadth >= float(p["recent_breadth_floor"]))
                & ((breadth - recent_breadth) >= float(p["breadth_change_floor"]))
                & (leader >= float(p["leader_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, selected, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for breadth, median, dispersion, leader, recent, spy in itertools.product(
            (0.55, 0.7, 0.85),
            (-0.002, 0.0, 0.002),
            (0.004, 0.008, 0.015),
            (0.002, 0.005, 0.01),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            yield {
                "family": "broad_risk_on",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": "sectors",
                    "breadth_floor": breadth,
                    "median_floor": median,
                    "dispersion_ceiling": dispersion,
                    "leader_floor": leader,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }
        for breadth_floor, breadth_ceiling, dispersion, spread, recent, spy in itertools.product(
            (0.2, 0.35, 0.5),
            (0.5, 0.65, 0.8),
            (0.004, 0.008, 0.012),
            (0.004, 0.008, 0.015),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            if breadth_floor >= breadth_ceiling:
                continue
            yield {
                "family": "narrow_leadership",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": "sectors",
                    "breadth_floor": breadth_floor,
                    "breadth_ceiling": breadth_ceiling,
                    "dispersion_floor": dispersion,
                    "spread_floor": spread,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }
        for breadth, recent_breadth, change, leader, spy in itertools.product(
            (0.45, 0.6, 0.75),
            (0.2, 0.35, 0.5),
            (0.1, 0.2, 0.35),
            (0.0, 0.003, 0.006),
            (-0.015, -0.005, 0.0),
        ):
            yield {
                "family": "breadth_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": "sectors",
                    "breadth_floor": breadth,
                    "recent_breadth_floor": recent_breadth,
                    "breadth_change_floor": change,
                    "leader_floor": leader,
                    "spy_floor": spy,
                },
            }


if __name__ == "__main__":
    v23.CUBE_CLASS = Cube
    v23.CANDIDATE_PREFIX = "lev-v24p-"
    v23._specifications = _specifications
    v23.main()
