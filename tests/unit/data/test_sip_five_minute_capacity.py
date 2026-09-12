import pandas as pd

from us_intraday_lab.data.sip_five_minute_capacity import (
    estimate_capacity,
    resolve_pilot_elapsed_seconds,
    select_liquidity_decile_sample,
)


def test_capacity_estimate_scales_observed_symbol_sessions() -> None:
    result = estimate_capacity(
        sampled_rows=7_800,
        sampled_bytes=780_000,
        sampled_symbols=10,
        sampled_sessions=10,
        expected_symbol_sessions=1_000_000,
        free_bytes=200_000_000,
        sampled_elapsed_seconds=1.0,
        parallel_workers=4,
        maximum_completion_seconds=100_000.0,
    )

    assert result["estimated_rows"] == 78_000_000
    assert result["rows_per_symbol_session"] == 78
    assert result["estimated_bytes"] == 7_800_000_000
    assert result["worst_case_bytes"] == 7_800_000_000
    assert result["safe_to_launch"] is False


def test_capacity_requires_nonempty_representative_sample() -> None:
    try:
        estimate_capacity(
            sampled_rows=0,
            sampled_bytes=0,
            sampled_symbols=10,
            sampled_sessions=1,
            expected_symbol_sessions=100,
            free_bytes=1_000_000,
            sampled_elapsed_seconds=1.0,
            parallel_workers=1,
            maximum_completion_seconds=100.0,
        )
    except ValueError as error:
        assert "sampled_rows" in str(error)
    else:
        raise AssertionError("empty capacity sample must fail closed")


def test_capacity_fails_closed_when_completion_estimate_exceeds_limit() -> None:
    result = estimate_capacity(
        sampled_rows=100,
        sampled_bytes=1_000,
        sampled_symbols=10,
        sampled_sessions=1,
        expected_symbol_sessions=10_000,
        free_bytes=1_000_000_000,
        sampled_elapsed_seconds=10.0,
        parallel_workers=2,
        maximum_completion_seconds=100.0,
    )

    assert result["disk_safe"] is True
    assert result["time_safe"] is False
    assert result["safe_to_launch"] is False


def test_liquidity_sample_covers_every_decile_deterministically() -> None:
    scores = pd.Series(
        {f"S{index:03d}": float(index) for index in range(100)}, name="dollar_volume"
    )

    first = select_liquidity_decile_sample(scores=scores, per_decile=2)
    second = select_liquidity_decile_sample(scores=scores, per_decile=2)

    assert first == second
    assert len(first) == 20
    selected_scores = scores.loc[list(first)].sort_values()
    assert sum(selected_scores < 10) == 2
    assert sum(selected_scores >= 90) == 2


def test_reused_pilot_without_matching_acquisition_timing_fails_closed() -> None:
    identity = {
        "pilot_root": "E:/pilot",
        "pilot_session": "2025-12-30",
        "sample_symbols_sha256": "sample",
        "pilot_partition_set_sha256": "partition",
    }

    try:
        resolve_pilot_elapsed_seconds(
            reused_existing_partitions=True,
            validation_elapsed_seconds=0.2,
            pilot_identity=identity,
            previous_report={},
        )
    except ValueError as error:
        assert "original acquisition timing" in str(error)
    else:
        raise AssertionError("reused pilot must not use validation time")

    previous = dict(identity, pilot_elapsed_seconds=2.5)
    assert (
        resolve_pilot_elapsed_seconds(
            reused_existing_partitions=True,
            validation_elapsed_seconds=0.2,
            pilot_identity=identity,
            previous_report=previous,
        )
        == 2.5
    )
