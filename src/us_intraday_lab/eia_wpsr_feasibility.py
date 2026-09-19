"""Frozen coverage gate and grid for EIA WPSR training feasibility."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import (
    DECISION_BARS,
    HOLDING_BARS,
    TOP_COUNTS,
    Specification,
)

FAMILIES = (
    "crude_draw",
    "gasoline_draw",
    "distillate_draw",
    "total_draw",
    "concordant_draw",
)


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, decision, holding, top_count)
        for family in FAMILIES
        for decision in DECISION_BARS
        for holding in HOLDING_BARS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("EIA WPSR grid must have 400 unique cells")
    return result


def coverage_gate(
    source_manifest: dict[str, object],
    release_features: pd.DataFrame,
    exposures: pd.DataFrame,
) -> dict[str, object]:
    """Check every source, release, family and beta floor before outcome loading."""
    required_states = {"release_date", "available_date", *FAMILIES}
    required_exposures = {"release_date", "available_date", "symbol", "beta",
                          "exclusion_reason"}
    if missing := required_states.difference(release_features.columns):
        raise ValueError(f"release feature columns missing: {sorted(missing)}")
    if missing := required_exposures.difference(exposures.columns):
        raise ValueError(f"exposure columns missing: {sorted(missing)}")
    states = release_features.copy()
    states["release_date"] = pd.to_datetime(states.release_date).dt.date
    states["available_date"] = pd.to_datetime(states.available_date).dt.date
    if states.duplicated("release_date").any():
        raise ValueError("duplicate release date")
    observed_years = states.release_date.map(lambda day: str(day.year)).value_counts().to_dict()
    observed_years = {year: int(observed_years.get(year, 0)) for year in ("2021", "2022", "2023")}
    hash_ok = bool(
        source_manifest.get("source_hashes_verified") is True
        and all(
            isinstance(source_manifest.get(key), str)
            and re.fullmatch(r"[0-9a-f]{64}", source_manifest[key])
            for key in ("source_manifest_sha256", "csv_manifest_sha256")
        )
    )
    source_complete = bool(
        hash_ok
        and source_manifest.get("release_count") == len(states)
        and source_manifest.get("release_counts_by_year") == observed_years
        and set(states.release_date.map(lambda day: day.year)) == {2021, 2022, 2023}
    )
    year_floor = all(observed_years[year] >= 48 for year in observed_years)
    total_floor = len(states) >= 150

    exposure = exposures.copy()
    exposure["release_date"] = pd.to_datetime(exposure.release_date).dt.date
    exposure["available_date"] = pd.to_datetime(exposure.available_date).dt.date
    if exposure.duplicated(["release_date", "symbol"]).any():
        raise ValueError("duplicate symbol-release exposure")
    valid_dates = states.set_index("release_date")["available_date"]
    if not exposure.release_date.isin(valid_dates.index).all():
        raise ValueError("exposure references unknown release")
    if not exposure.available_date.eq(exposure.release_date.map(valid_dates)).all():
        raise ValueError("exposure availability mismatch")
    beta = pd.to_numeric(exposure.beta, errors="coerce")
    eligible = exposure.loc[
        exposure.exclusion_reason.eq("") & exposure.symbol.ne("XLE")
        & np.isfinite(beta) & beta.gt(0)
    ]
    pair_count = len(eligible)
    available_symbols = eligible.groupby("available_date")["symbol"].nunique()
    sessions_with_150 = int(available_symbols.ge(150).sum())
    unique_symbols = int(eligible.symbol.nunique())

    available_states = states.loc[states.available_date.notna()]
    family_counts: dict[str, int] = {}
    family_years: dict[str, dict[str, int]] = {}
    family_floor = True
    for family in FAMILIES:
        active = available_states.loc[available_states[family].eq(True)]
        family_counts[family] = len(active)
        counts = active.release_date.map(lambda day: str(day.year)).value_counts().to_dict()
        family_years[family] = {year: int(counts.get(year, 0)) for year in observed_years}
        family_floor &= len(active) >= 40 and all(value >= 10 for value in family_years[family].values())
    passed = bool(
        source_complete and year_floor and total_floor and unique_symbols >= 150
        and sessions_with_150 >= 100 and pair_count >= 20_000 and family_floor
    )
    return {
        "passed": passed,
        "source_complete": source_complete,
        "release_count": len(states),
        "release_counts_by_year": observed_years,
        "release_year_floor_passed": year_floor,
        "release_total_floor_passed": total_floor,
        "unique_positive_beta_symbols": unique_symbols,
        "sessions_with_150_beta_symbols": sessions_with_150,
        "eligible_symbol_release_pairs": pair_count,
        "active_releases_by_family": family_counts,
        "active_releases_by_family_year": family_years,
        "family_floor_passed": bool(family_floor),
        "post_availability_outcomes_loaded": False,
    }
