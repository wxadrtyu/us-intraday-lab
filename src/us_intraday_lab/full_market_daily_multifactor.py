"""Frozen full-market long-horizon daily technical multifactor contract."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FAMILIES = (
    "residual_momentum",
    "trend_quality",
    "low_vol_trend",
    "liquidity_confirmed_breakout",
    "trend_conditioned_reversal",
)
REBALANCE_SESSIONS = (5, 10, 20, 21)
HOLDING_SESSIONS = (5, 10, 20, 42)
TOP_COUNTS = (10, 20, 40, 80, 120)

_DAILY_COLUMNS = {
    "symbol",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
}
_UNIVERSE_COLUMNS = {"symbol", "month", "information_cutoff", "eligible"}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    rebalance_sessions: int
    holding_sessions: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell discovery grid."""
    result = tuple(
        Specification(family, rebalance, holding, top_count)
        for family in FAMILIES
        for rebalance in REBALANCE_SESSIONS
        for holding in HOLDING_SESSIONS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_DAILY_GRID_INVALID")
    return result


def _month_start(values: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(values, errors="raise")
    return timestamps.dt.to_period("M").dt.to_timestamp()


def validate_monthly_universe(universe: pd.DataFrame) -> pd.DataFrame:
    """Validate one causal point-in-time decision for every symbol-month."""
    missing = _UNIVERSE_COLUMNS.difference(universe.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_UNIVERSE_SCHEMA_MISSING:{sorted(missing)}")
    result = universe.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    if result["symbol"].eq("").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_SYMBOL_INVALID")
    parsed_month = pd.to_datetime(result["month"], errors="raise")
    result["month"] = _month_start(result["month"])
    if not parsed_month.eq(result["month"]).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_MONTH_NOT_FIRST")
    result["information_cutoff"] = pd.to_datetime(
        result["information_cutoff"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "month"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_KEY_DUPLICATE")
    if result["information_cutoff"].ge(result["month"]).any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_CUTOFF_NOT_PRIOR")
    if not result["eligible"].map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_ELIGIBLE_NOT_BOOLEAN")
    return result.sort_values(["month", "symbol"], kind="stable", ignore_index=True)


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    missing = _DAILY_COLUMNS.difference(daily_bars.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_SCHEMA_MISSING:{sorted(missing)}")
    extras = set(daily_bars.columns).difference(_DAILY_COLUMNS)
    if extras:
        raise ValueError(f"FULL_MARKET_DAILY_FORBIDDEN_INPUT_COLUMN:{sorted(extras)}")
    result = daily_bars.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "session_date"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_KEY_DUPLICATE")
    numeric = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    finite = np.isfinite(result[numeric]).all(axis=1)
    positive = result[["open", "high", "low", "close", "vwap"]].gt(0).all(axis=1)
    nonnegative = result[["volume", "trade_count"]].ge(0).all(axis=1)
    if not finite.all() or not positive.all() or not nonnegative.all():
        raise ValueError("FULL_MARKET_DAILY_VALUES_INVALID")
    return result.sort_values(["session_date", "symbol"], kind="stable", ignore_index=True)


def attach_point_in_time_eligibility(
    daily_bars: pd.DataFrame, universe: pd.DataFrame
) -> pd.DataFrame:
    """Attach only the same-month frozen decision and return eligible rows.

    A missing symbol-month decision is a source-contract failure, not an
    opportunity to infer membership or silently remove a bar.
    """
    bars = _validate_daily_bars(daily_bars)
    decisions = validate_monthly_universe(universe)
    bars["universe_month"] = _month_start(bars["session_date"])
    membership = decisions.loc[
        :, ["symbol", "month", "information_cutoff", "eligible"]
    ].rename(columns={"month": "universe_month"})
    attached = bars.merge(
        membership,
        on=["symbol", "universe_month"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if attached["_merge"].ne("both").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_DECISION_MISSING")
    attached = attached.drop(columns="_merge")
    return attached.loc[attached["eligible"]].sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )


def _rolling_trend(values: pd.Series, window: int) -> tuple[np.ndarray, np.ndarray]:
    array = values.to_numpy(dtype=float)
    slopes = np.full(len(array), np.nan)
    residual_volatility = np.full(len(array), np.nan)
    if len(array) < window:
        return slopes, residual_volatility
    x = np.arange(window, dtype=float)
    centered_x = x - x.mean()
    sum_x_squared = float(np.square(centered_x).sum())
    valid_slopes = np.correlate(array, centered_x, mode="valid") / sum_x_squared
    rolling_sum = np.convolve(array, np.ones(window), mode="valid")
    rolling_square_sum = np.convolve(np.square(array), np.ones(window), mode="valid")
    centered_sum_squares = rolling_square_sum - np.square(rolling_sum) / window
    residual_sum_squares = np.maximum(
        centered_sum_squares - np.square(valid_slopes) * sum_x_squared, 0.0
    )
    slopes[window - 1 :] = valid_slopes
    residual_volatility[window - 1 :] = np.sqrt(
        residual_sum_squares / (window - 2)
    )
    return slopes, residual_volatility


def build_daily_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Build causal completed-bar primitives before applying eligibility."""
    frame = _validate_daily_bars(daily_bars)
    frame = frame.sort_values(["symbol", "session_date"], kind="stable", ignore_index=True)
    frame["log_close"] = np.log(frame["close"])
    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["log_return"] = grouped["log_close"].diff()
    frame["market_return"] = frame.groupby("session_date", observed=True)[
        "log_return"
    ].transform("median")

    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["return_5"] = frame["log_close"] - grouped["log_close"].shift(5)
    frame["return_126"] = frame["log_close"] - grouped["log_close"].shift(126)
    frame["return_252_21"] = grouped["log_close"].shift(21) - grouped[
        "log_close"
    ].shift(252)
    market_by_date = (
        frame.loc[:, ["session_date", "market_return"]]
        .drop_duplicates("session_date")
        .sort_values("session_date", kind="stable")
    )
    market_by_date["market_return_252_21"] = (
        market_by_date["market_return"].shift(21).rolling(231, min_periods=231).sum()
    )
    frame = frame.merge(
        market_by_date.loc[:, ["session_date", "market_return_252_21"]],
        on="session_date",
        how="left",
        validate="many_to_one",
    )
    grouped = frame.groupby("symbol", sort=False, observed=True)
    rolling_covariance = grouped.apply(
        lambda group: group["log_return"].rolling(60, min_periods=60).cov(
            group["market_return"]
        ),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    rolling_market_variance = grouped["market_return"].transform(
        lambda values: values.rolling(60, min_periods=60).var(ddof=1)
    )
    frame["beta_60"] = (rolling_covariance / rolling_market_variance).where(
        rolling_market_variance.gt(0)
    )
    frame["realized_volatility_60"] = grouped["log_return"].transform(
        lambda values: values.rolling(60, min_periods=60).std(ddof=1)
    ) * np.sqrt(252.0)
    frame["residual_momentum_252_21"] = (
        frame["return_252_21"]
        - frame["beta_60"] * frame["market_return_252_21"]
    ) / frame["realized_volatility_60"].where(frame["realized_volatility_60"].gt(0))

    slope = np.full(len(frame), np.nan)
    residual_volatility = np.full(len(frame), np.nan)
    for positions in grouped.indices.values():
        ordered_positions = np.asarray(positions, dtype=int)
        symbol_slope, symbol_residual = _rolling_trend(
            frame.loc[ordered_positions, "log_close"], 126
        )
        slope[ordered_positions] = symbol_slope
        residual_volatility[ordered_positions] = symbol_residual
    frame["trend_slope_126"] = slope
    frame["trend_residual_volatility_126"] = residual_volatility
    moving_average_63 = grouped["close"].transform(
        lambda values: values.rolling(63, min_periods=63).mean()
    )
    above_average = frame["close"].gt(moving_average_63).astype(float)
    frame["above_average_fraction_63"] = above_average.groupby(
        frame["symbol"], sort=False, observed=True
    ).transform(lambda values: values.rolling(63, min_periods=63).mean())
    frame["trend_quality_126"] = (
        frame["trend_slope_126"]
        / frame["trend_residual_volatility_126"].where(
            frame["trend_residual_volatility_126"].gt(0)
        )
        * frame["above_average_fraction_63"]
    )
    frame["moving_average_126"] = grouped["close"].transform(
        lambda values: values.rolling(126, min_periods=126).mean()
    )
    prior_high = grouped["close"].transform(
        lambda values: values.shift(1).rolling(126, min_periods=126).max()
    )
    frame["breakout_126"] = frame["close"] / prior_high - 1.0
    dollar_volume = frame["close"] * frame["volume"]
    frame["dollar_volume_ratio_20_126"] = (
        dollar_volume.groupby(frame["symbol"], sort=False, observed=True).transform(
            lambda values: values.rolling(20, min_periods=20).mean()
        )
        / dollar_volume.groupby(frame["symbol"], sort=False, observed=True).transform(
            lambda values: values.rolling(126, min_periods=126).median()
        )
    )
    rolling_vwap = grouped["vwap"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    frame["vwap_displacement_20"] = frame["close"] / rolling_vwap - 1.0
    output_columns = [
        "symbol",
        "session_date",
        "residual_momentum_252_21",
        "trend_quality_126",
        "return_126",
        "realized_volatility_60",
        "breakout_126",
        "dollar_volume_ratio_20_126",
        "vwap_displacement_20",
        "return_5",
        "moving_average_126",
        "close",
    ]
    return frame.loc[:, output_columns].sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )


def _winsorized_rank(values: pd.Series, dates: pd.Series) -> pd.Series:
    lower = values.groupby(dates, observed=True).transform(lambda group: group.quantile(0.01))
    upper = values.groupby(dates, observed=True).transform(lambda group: group.quantile(0.99))
    clipped = values.clip(lower=lower, upper=upper)
    return clipped.groupby(dates, observed=True).rank(method="average", pct=True)


def score_families(features: pd.DataFrame) -> pd.DataFrame:
    """Create the five preregistered cross-sectional family scores."""
    required = {
        "symbol",
        "session_date",
        "residual_momentum_252_21",
        "trend_quality_126",
        "return_126",
        "realized_volatility_60",
        "breakout_126",
        "dollar_volume_ratio_20_126",
        "vwap_displacement_20",
        "return_5",
        "moving_average_126",
        "close",
    }
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_FEATURE_SCHEMA_MISSING:{sorted(missing)}")
    result = features.copy()
    dates = pd.to_datetime(result["session_date"], errors="raise").dt.normalize()
    result["session_date"] = dates
    result["residual_momentum"] = _winsorized_rank(
        result["residual_momentum_252_21"], dates
    )
    result["trend_quality"] = _winsorized_rank(result["trend_quality_126"], dates)
    positive_trend = result["return_126"].gt(0)
    trend_rank = _winsorized_rank(result["return_126"], dates)
    quiet_rank = _winsorized_rank(-result["realized_volatility_60"], dates)
    result["low_vol_trend"] = ((trend_rank + quiet_rank) / 2.0).where(positive_trend)
    volume_confirmed = result["dollar_volume_ratio_20_126"].gt(1.0)
    vwap_confirmed = result["vwap_displacement_20"].gt(0.0)
    result["liquidity_confirmed_breakout"] = (
        (
            _winsorized_rank(result["breakout_126"], dates)
            + _winsorized_rank(result["dollar_volume_ratio_20_126"], dates)
            + _winsorized_rank(result["vwap_displacement_20"], dates)
        )
        / 3.0
    ).where(volume_confirmed & vwap_confirmed)
    reversal_gate = positive_trend & result["close"].gt(result["moving_average_126"])
    result["trend_conditioned_reversal"] = _winsorized_rank(
        -result["return_5"], dates
    ).where(reversal_gate)
    return result
