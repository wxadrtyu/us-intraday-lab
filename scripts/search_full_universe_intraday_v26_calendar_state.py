"""Low-turnover fixed-asset calendar and overnight-state search."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import search_full_universe_intraday_v17_fixed_asset_state as v17
import search_full_universe_intraday_v23_beta_residual as v23

ASSETS = (0, 1, 2, 3, 4, 7, 8, 10, 13, 14, 15)
WEEKDAYS = {
    "all": (0, 1, 2, 3, 4),
    "mon_thu": (0, 1, 2, 3),
    "tue_fri": (1, 2, 3, 4),
    "mon_wed_fri": (0, 2, 4),
    "tue_thu": (1, 3),
    "early_week": (0, 1),
    "late_week": (3, 4),
}
SLOTS = {
    "full_day": ((1, 5, 11), (59, 71, 77)),
    "morning": ((5, 11, 17), (35, 47)),
    "afternoon": ((41, 47), (71, 77)),
}


class Cube(v17.Cube):
    """Exact cube with prior-session 20-day state and calendar known before entry."""

    def __init__(self, root, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        self.prior20 = np.full_like(daily, np.nan)
        for index in range(20, len(self.sessions)):
            window = daily[index - 20 : index]
            valid = np.isfinite(window).all(axis=0)
            self.prior20[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
        self.weekday = self.dates.dayofweek.to_numpy()

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        asset = int(p["asset"])
        feature = self._features(int(p["decision"]))
        current = feature["current"][:, asset]
        recent = feature["recent"][:, asset]
        common = (
            np.isin(self.weekday, WEEKDAYS[str(p["weekday_group"])])
            & np.isfinite(current)
            & np.isfinite(recent)
            & np.isfinite(self.gap[:, asset])
            & np.isfinite(self.prior1[:, asset])
            & np.isfinite(self.prior20[:, asset])
            & (self.prior20[:, asset] >= float(p["prior20_floor"]))
            & (feature["spy"] >= float(p["spy_floor"]))
        )
        if family == "calendar_trend":
            eligible = (
                common
                & (self.prior1[:, asset] >= float(p["prior1_floor"]))
                & (self.gap[:, asset] >= float(p["gap_floor"]))
                & (current >= float(p["current_floor"]))
                & (recent >= float(p["recent_floor"]))
            )
        elif family == "calendar_recovery":
            eligible = (
                common
                & (self.prior1[:, asset] <= float(p["prior1_ceiling"]))
                & (self.gap[:, asset] <= float(p["gap_ceiling"]))
                & (current >= float(p["current_floor"]))
                & (recent >= float(p["recent_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, asset, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for asset, weekday, prior20, prior1, gap, current, recent, spy in itertools.product(
            ASSETS,
            WEEKDAYS,
            (-0.05, 0.03),
            (-0.02, 0.0),
            (-0.01, 0.0),
            (-0.003, 0.002),
            (-0.003, 0.002),
            (-0.01, 0.0),
        ):
            yield {
                "family": "calendar_trend",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "universe": str(asset),
                    "weekday_group": weekday,
                    "prior20_floor": prior20,
                    "prior1_floor": prior1,
                    "gap_floor": gap,
                    "current_floor": current,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }
        for asset, weekday, prior20, prior1, gap, current, recent, spy in itertools.product(
            ASSETS,
            WEEKDAYS,
            (-0.05, 0.03),
            (-0.01, -0.03),
            (0.0, 0.015),
            (-0.006, 0.0),
            (-0.003, 0.002),
            (-0.01, 0.0),
        ):
            yield {
                "family": "calendar_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "universe": str(asset),
                    "weekday_group": weekday,
                    "prior20_floor": prior20,
                    "prior1_ceiling": prior1,
                    "gap_ceiling": gap,
                    "current_floor": current,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }


if __name__ == "__main__":
    v23.SLOTS = SLOTS
    v23.CUBE_CLASS = Cube
    v23.CANDIDATE_PREFIX = "lev-v26p-"
    v23._specifications = _specifications
    v23.main()
