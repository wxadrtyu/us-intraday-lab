"""Prospective admission gates effective from strategy version v7795."""

from __future__ import annotations

from typing import Any

EFFECTIVE_FIRST_VERSION = 7795
ANNUALIZED_RETURN_FLOOR = 0.40
MAX_DRAWDOWN_CEILING = 0.20
INFORMATION_RATIO_FLOOR = 1.0
GLOBAL_EVIDENCE_Z_FLOOR = 3.0


def passes_primary(observation: dict[str, Any]) -> bool:
    """Apply the user-authorized primary gate without changing older campaigns."""
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) > ANNUALIZED_RETURN_FLOOR
        and float(oos["max_drawdown"]) < MAX_DRAWDOWN_CEILING
        and float(oos["information_ratio"]) >= INFORMATION_RATIO_FLOOR
        and all(
            float(observation[name]["annualized_return"]) > 0
            for name in ("train_2022_2023", "2024", "2025")
        )
    )


def passes_global_evidence(z_score: float) -> bool:
    """Screen global evidence before the mandatory architecture-native null."""
    return float(z_score) >= GLOBAL_EVIDENCE_Z_FLOOR
