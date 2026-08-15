"""Unlevered-proxy signals with long-only leveraged ETF execution."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import search_full_universe_intraday_v21_vwap_structure as v21
import search_full_universe_intraday_v23_beta_residual as v23
import search_full_universe_intraday_v26_calendar_state as v26

PAIRS = ((3, 1), (4, 10))  # TQQQ <- QQQ; SOXL <- XLK
WEEKDAYS = {key: v26.WEEKDAYS[key] for key in ("all", "mon_thu", "tue_fri")}
SLOTS = v21.SLOTS


class Cube(v26.Cube):
    """Exact cube whose signal and execution assets are explicitly separated."""

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        asset = int(p["asset"])
        proxy = int(p["proxy"])
        feature = self._features(int(p["decision"]))
        proxy_current = feature["current"][:, proxy]
        asset_current = feature["current"][:, asset]
        common = (
            np.isin(self.weekday, WEEKDAYS[str(p["weekday_group"])])
            & np.isfinite(proxy_current)
            & np.isfinite(asset_current)
            & np.isfinite(self.prior20[:, proxy])
            & np.isfinite(self.prior1[:, proxy])
            & np.isfinite(self.gap[:, asset])
            & (self.prior20[:, proxy] >= float(p["prior20_floor"]))
            & (feature["spy"] >= float(p["spy_floor"]))
        )
        if family == "proxy_trend":
            eligible = (
                common
                & (self.prior1[:, proxy] >= float(p["prior1_floor"]))
                & (self.gap[:, asset] >= float(p["gap_floor"]))
                & (proxy_current >= float(p["proxy_current_floor"]))
                & (asset_current >= float(p["asset_current_floor"]))
                & (proxy_current - feature["spy"] >= float(p["relative_floor"]))
            )
        elif family == "proxy_recovery":
            eligible = (
                common
                & (self.prior1[:, proxy] <= float(p["prior1_ceiling"]))
                & (self.gap[:, asset] <= float(p["gap_ceiling"]))
                & (proxy_current >= float(p["proxy_current_floor"]))
                & (asset_current >= float(p["asset_current_floor"]))
                & (feature["recent"][:, proxy] >= float(p["proxy_recent_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, asset, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for (
            pair,
            weekday,
            prior20,
            prior1,
            gap,
            proxy_current,
            asset_current,
            relative,
            spy,
        ) in itertools.product(
            PAIRS,
            WEEKDAYS,
            (-0.05, 0.03, 0.08),
            (-0.02, 0.0),
            (-0.015, 0.0),
            (0.0, 0.003, 0.006),
            (-0.005, 0.0, 0.003),
            (0.0, 0.003),
            (-0.01, 0.0),
        ):
            asset, proxy = pair
            yield {
                "family": "proxy_trend",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "proxy": proxy,
                    "universe": str(asset),
                    "weekday_group": weekday,
                    "prior20_floor": prior20,
                    "prior1_floor": prior1,
                    "gap_floor": gap,
                    "proxy_current_floor": proxy_current,
                    "asset_current_floor": asset_current,
                    "relative_floor": relative,
                    "spy_floor": spy,
                },
            }
        for (
            pair,
            weekday,
            prior20,
            prior1,
            gap,
            proxy_current,
            asset_current,
            recent,
            spy,
        ) in itertools.product(
            PAIRS,
            WEEKDAYS,
            (-0.05, 0.03),
            (-0.01, -0.03),
            (0.0, 0.015),
            (-0.003, 0.0, 0.003),
            (-0.006, 0.0, 0.003),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            asset, proxy = pair
            yield {
                "family": "proxy_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "proxy": proxy,
                    "universe": str(asset),
                    "weekday_group": weekday,
                    "prior20_floor": prior20,
                    "prior1_ceiling": prior1,
                    "gap_ceiling": gap,
                    "proxy_current_floor": proxy_current,
                    "asset_current_floor": asset_current,
                    "proxy_recent_floor": recent,
                    "spy_floor": spy,
                },
            }


if __name__ == "__main__":
    v23.SLOTS = SLOTS
    v23.CUBE_CLASS = Cube
    v23.CANDIDATE_PREFIX = "lev-v28p-"
    v23._specifications = _specifications
    v23.main()
