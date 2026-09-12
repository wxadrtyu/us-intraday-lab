"""Pure capacity estimates for full-market SIP five-minute acquisition."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping

import pandas as pd


def resolve_pilot_elapsed_seconds(
    *,
    reused_existing_partitions: bool,
    validation_elapsed_seconds: float,
    pilot_identity: Mapping[str, object],
    previous_report: Mapping[str, object],
) -> float:
    """Never substitute fast local validation time for original acquisition time."""
    if not reused_existing_partitions:
        return validation_elapsed_seconds
    identity_matches = all(
        previous_report.get(key) == value for key, value in pilot_identity.items()
    )
    previous_elapsed = previous_report.get("pilot_elapsed_seconds")
    if (
        not identity_matches
        or not isinstance(previous_elapsed, (int, float))
        or previous_elapsed <= 0
    ):
        raise ValueError(
            "reused pilot has no matching original acquisition timing; fail closed"
        )
    return float(previous_elapsed)


def select_liquidity_decile_sample(
    *, scores: pd.Series, per_decile: int
) -> tuple[str, ...]:
    """Choose a stable hash-ordered sample from every empirical liquidity decile."""
    if per_decile < 1 or len(scores) < 10 * per_decile:
        raise ValueError("insufficient scores for requested liquidity-decile sample")
    if not scores.index.is_unique:
        raise ValueError("liquidity score symbols must be unique")
    frame = (
        scores.rename("score")
        .fillna(0.0)
        .rename_axis("symbol")
        .reset_index()
        .sort_values("symbol", kind="stable")
        .reset_index(drop=True)
    )
    frame["decile"] = pd.qcut(
        frame["score"].rank(method="first"), q=10, labels=False
    ).astype(int)
    frame["sample_order"] = frame["symbol"].map(
        lambda symbol: hashlib.sha256(str(symbol).encode()).hexdigest()
    )
    selected = (
        frame.sort_values(["decile", "sample_order"], kind="stable")
        .groupby("decile", sort=True)
        .head(per_decile)
    )
    if selected["decile"].nunique() != 10 or len(selected) != 10 * per_decile:
        raise ValueError("liquidity-decile sample is incomplete")
    return tuple(sorted(selected["symbol"].astype(str)))


def estimate_capacity(
    *,
    sampled_rows: int,
    sampled_bytes: int,
    sampled_symbols: int,
    sampled_sessions: int,
    expected_symbol_sessions: int,
    free_bytes: int,
    sampled_elapsed_seconds: float,
    parallel_workers: int,
    maximum_completion_seconds: float,
    maximum_free_space_fraction: float = 0.70,
    maximum_regular_session_bars: int = 78,
    time_safety_factor: float = 2.0,
) -> dict[str, float | int | bool]:
    """Scale an observed pilot and fail closed on empty or invalid inputs."""
    if sampled_rows <= 0:
        raise ValueError("sampled_rows must be positive")
    if sampled_bytes <= 0:
        raise ValueError("sampled_bytes must be positive")
    if sampled_symbols <= 0 or sampled_sessions <= 0:
        raise ValueError("sampled_symbols and sampled_sessions must be positive")
    if expected_symbol_sessions <= 0 or free_bytes <= 0:
        raise ValueError("expected_symbol_sessions and free_bytes must be positive")
    if sampled_elapsed_seconds <= 0 or maximum_completion_seconds <= 0:
        raise ValueError("elapsed and maximum completion seconds must be positive")
    if parallel_workers < 1 or time_safety_factor < 1:
        raise ValueError("parallel_workers and time_safety_factor are invalid")
    if not 0 < maximum_free_space_fraction < 1:
        raise ValueError("maximum_free_space_fraction must be between zero and one")
    if maximum_regular_session_bars < 1:
        raise ValueError("maximum_regular_session_bars must be positive")

    sampled_symbol_sessions = sampled_symbols * sampled_sessions
    rows_per_symbol_session = sampled_rows / sampled_symbol_sessions
    bytes_per_row = sampled_bytes / sampled_rows
    estimated_rows = round(rows_per_symbol_session * expected_symbol_sessions)
    estimated_bytes = math.ceil(bytes_per_row * estimated_rows)
    worst_case_rows = expected_symbol_sessions * maximum_regular_session_bars
    worst_case_bytes = math.ceil(bytes_per_row * worst_case_rows)
    seconds_per_row = sampled_elapsed_seconds / sampled_rows
    estimated_completion_seconds = (
        seconds_per_row * estimated_rows * time_safety_factor / parallel_workers
    )
    worst_case_completion_seconds = (
        seconds_per_row * worst_case_rows * time_safety_factor / parallel_workers
    )
    launch_limit_bytes = math.floor(free_bytes * maximum_free_space_fraction)
    disk_safe = worst_case_bytes <= launch_limit_bytes
    time_safe = estimated_completion_seconds <= maximum_completion_seconds
    return {
        "sampled_symbol_sessions": sampled_symbol_sessions,
        "rows_per_symbol_session": rows_per_symbol_session,
        "bytes_per_row": bytes_per_row,
        "estimated_rows": estimated_rows,
        "estimated_bytes": estimated_bytes,
        "worst_case_rows": worst_case_rows,
        "worst_case_bytes": worst_case_bytes,
        "sampled_elapsed_seconds": sampled_elapsed_seconds,
        "seconds_per_row": seconds_per_row,
        "parallel_workers": parallel_workers,
        "time_safety_factor": time_safety_factor,
        "estimated_completion_seconds": estimated_completion_seconds,
        "worst_case_completion_seconds": worst_case_completion_seconds,
        "maximum_completion_seconds": maximum_completion_seconds,
        "free_bytes": free_bytes,
        "launch_limit_bytes": launch_limit_bytes,
        "maximum_free_space_fraction": maximum_free_space_fraction,
        "disk_safe": disk_safe,
        "time_safe": time_safe,
        "safe_to_launch": disk_safe and time_safe,
    }
