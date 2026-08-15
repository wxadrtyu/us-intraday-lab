"""Low-frequency prior-20-session cross-sectional ETF rotation search."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import search_full_universe_intraday_v23_beta_residual as v23
import search_full_universe_intraday_v26_calendar_state as v26

UNIVERSES = v23.UNIVERSES
WEEKDAYS = {key: v26.WEEKDAYS[key] for key in ("all", "mon_thu", "tue_fri", "tue_thu")}
SLOTS = v26.SLOTS


class Cube(v26.Cube):
    """Exact cube selecting assets from prior-session-only cross-sectional state."""

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        universe = UNIVERSES[str(p["universe"])]
        feature = self._features(int(p["decision"]))
        state = self.prior20[:, universe]
        finite = np.isfinite(state)
        available = finite.sum(axis=1) >= max(2, len(universe) // 2)
        if family == "prior20_strength":
            selected = universe[np.argmax(np.where(finite, state, -np.inf), axis=1)]
            eligible = (
                available
                & (self.prior20[self.rows, selected] >= float(p["prior20_floor"]))
                & (self.prior1[self.rows, selected] >= float(p["prior1_floor"]))
                & (self.gap[self.rows, selected] >= float(p["gap_floor"]))
                & (feature["current"][self.rows, selected] >= float(p["current_floor"]))
                & (
                    feature["current"][self.rows, selected] - feature["spy"]
                    >= float(p["relative_floor"])
                )
            )
        elif family == "prior20_reversal":
            selected = universe[np.argmin(np.where(finite, state, np.inf), axis=1)]
            eligible = (
                available
                & (self.prior20[self.rows, selected] <= float(p["prior20_ceiling"]))
                & (self.prior1[self.rows, selected] >= float(p["prior1_floor"]))
                & (self.gap[self.rows, selected] <= float(p["gap_ceiling"]))
                & (feature["current"][self.rows, selected] >= float(p["current_floor"]))
                & (feature["recent"][self.rows, selected] >= float(p["recent_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        eligible &= np.isin(self.weekday, WEEKDAYS[str(p["weekday_group"])]) & (
            feature["spy"] >= float(p["spy_floor"])
        )
        return np.where(eligible, selected, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for universe, weekday, prior20, prior1, gap, current, relative, spy in itertools.product(
            UNIVERSES,
            WEEKDAYS,
            (0.02, 0.06, 0.12),
            (-0.02, 0.0),
            (-0.01, 0.0),
            (-0.003, 0.0, 0.003),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            yield {
                "family": "prior20_strength",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "weekday_group": weekday,
                    "prior20_floor": prior20,
                    "prior1_floor": prior1,
                    "gap_floor": gap,
                    "current_floor": current,
                    "relative_floor": relative,
                    "spy_floor": spy,
                },
            }
        for universe, weekday, prior20, prior1, gap, current, recent, spy in itertools.product(
            UNIVERSES,
            WEEKDAYS,
            (-0.02, -0.06, -0.12),
            (-0.02, 0.0),
            (0.0, 0.01),
            (-0.006, 0.0),
            (-0.003, 0.002),
            (-0.01, 0.0),
        ):
            yield {
                "family": "prior20_reversal",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "weekday_group": weekday,
                    "prior20_ceiling": prior20,
                    "prior1_floor": prior1,
                    "gap_ceiling": gap,
                    "current_floor": current,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }


if __name__ == "__main__":
    v23.SLOTS = SLOTS
    v23.CUBE_CLASS = Cube
    v23.CANDIDATE_PREFIX = "lev-v27p-"
    v23._specifications = _specifications
    v23.main()
