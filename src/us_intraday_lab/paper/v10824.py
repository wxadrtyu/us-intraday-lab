"""Brokerless forward-plan assembly for the frozen v10824 candidate."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CANDIDATE_ID = "lev-v10824-dc64eea19fd64bd8"
LOW_EXPOSURE = 0.25


@dataclass(frozen=True, slots=True)
class ForwardPlan:
    """Daily return-equivalent plan assembled only from causal sleeve decisions."""

    values: np.ndarray
    active: np.ndarray
    late_source: np.ndarray
    late_exposure: np.ndarray


def routed_anchor(
    *,
    modern_state: np.ndarray,
    transfer_allowed: np.ndarray,
    modern_values: np.ndarray,
    modern_active: np.ndarray,
    transfer_values: np.ndarray,
    transfer_active: np.ndarray,
    fallback_values: np.ndarray,
    fallback_active: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Select the frozen modern, transfer, or fallback parent before fill."""

    arrays = (
        transfer_allowed,
        modern_values,
        modern_active,
        transfer_values,
        transfer_active,
        fallback_values,
        fallback_active,
    )
    if any(np.shape(item) != np.shape(modern_state) for item in arrays):
        raise ValueError("V10824_ROUTE_SHAPE_MISMATCH")
    use_transfer = (~modern_state) & transfer_allowed
    values = np.where(
        modern_state,
        modern_values,
        np.where(use_transfer, transfer_values, fallback_values),
    )
    active = np.where(
        modern_state,
        modern_active,
        np.where(use_transfer, transfer_active, fallback_active),
    )
    return values, active.astype(bool)


def assemble_forward_plan(
    *,
    opening_values: np.ndarray,
    opening_active: np.ndarray,
    anchor_values: np.ndarray,
    anchor_active: np.ndarray,
    fill_values: np.ndarray,
    fill_active: np.ndarray,
    fill_allowed: np.ndarray,
    outer_allowed: np.ndarray,
    low_exposure: float = LOW_EXPOSURE,
) -> ForwardPlan:
    """Apply disjoint cash fill and the causal bar-5 soft gate.

    All inputs are daily arrays computed at or before their declared decision
    clock.  Opening exits exactly when the late sleeve may enter, so gross
    exposure cannot overlap across the two sleeves.
    """

    shape = np.shape(opening_values)
    arrays = (
        opening_active,
        anchor_values,
        anchor_active,
        fill_values,
        fill_active,
        fill_allowed,
        outer_allowed,
    )
    if any(np.shape(item) != shape for item in arrays):
        raise ValueError("V10824_PLAN_SHAPE_MISMATCH")
    if not 0.0 <= low_exposure <= 1.0:
        raise ValueError("V10824_LOW_EXPOSURE_OUT_OF_RANGE")

    use_fill = (~anchor_active) & fill_active & fill_allowed
    late_values = np.where(anchor_active, anchor_values, np.where(use_fill, fill_values, 0.0))
    late_active = anchor_active | use_fill
    exposure = np.where(outer_allowed, 1.0, low_exposure)
    values = opening_values + late_values * exposure
    active = opening_active | late_active
    source = np.where(anchor_active, 1, np.where(use_fill, 2, 0)).astype(np.int8)
    return ForwardPlan(values, active, source, exposure)
