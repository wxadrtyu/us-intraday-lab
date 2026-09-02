"""Build the v11098 causal feature cube directly from an Alpaca bars frame."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12

from us_intraday_lab.research_shadow_alpaca import NEW_YORK


@dataclass(frozen=True, slots=True)
class LiveLeg:
    sleeve: str
    parent_id: str
    symbol: str
    decision_bar: int
    entry_bar: int
    exit_bar: int
    weight: float
    exposure: float


def load_contract(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("contract_sha256", None)
    observed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected != observed or payload.get("candidate_id") != "lev-v11098-2ddc1d07c9cfe31e":
        raise ValueError("V11098_FORWARD_CONTRACT_INVALID")
    payload["contract_sha256"] = expected
    return payload


def _cube(frame: pd.DataFrame, sessions: pd.Index, column: str) -> np.ndarray:
    wide = frame.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=v12.SYMBOLS)
    return wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(v12.SYMBOLS))


def _bucket(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"V11098_LIVE_BARS_COLUMNS_MISSING:{sorted(missing)}")
    frame = bars.loc[:, sorted(required)].copy()
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    local = timestamp.dt.tz_convert(NEW_YORK)
    frame["session_date"] = local.dt.date
    frame["minute"] = (local.dt.hour - 9) * 60 + local.dt.minute - 30
    frame = frame.loc[frame["minute"].between(0, 389)].copy()
    frame["bar"] = (frame["minute"] // 5).astype(int)
    frame["close_dollar_volume"] = frame["close"] * frame["volume"]
    frame["_timestamp"] = timestamp.loc[frame.index]
    frame = frame.sort_values(["symbol", "session_date", "_timestamp"])
    return (
        frame.groupby(["symbol", "session_date", "bar"], sort=True, observed=True)
        .agg(
            open=("open", "first"),
            close=("close", "last"),
            high=("high", "max"),
            low=("low", "min"),
            close_dollar_volume=("close_dollar_volume", "sum"),
            volume=("volume", "sum"),
            first_minute=("minute", "min"),
            last_minute=("minute", "max"),
        )
        .reset_index()
    )


def feature_cube_from_bars(bars: pd.DataFrame):
    """Return the exact research feature class without reading or fitting data."""

    frame = _bucket(bars)
    sessions = pd.Index(
        sorted(frame.loc[(frame["symbol"] == "SPY") & (frame["bar"] == 0), "session_date"].unique())
    )
    if len(sessions) < 61:
        raise ValueError("V11098_REQUIRES_61_SESSIONS")
    cube = sector.SectorFlowLeadershipCube.__new__(sector.SectorFlowLeadershipCube)
    cube.sessions = sessions
    cube.dates = pd.to_datetime(sessions.astype(str))
    cube.opens = _cube(frame, sessions, "open")
    cube.closes = _cube(frame, sessions, "close")
    cube.first = _cube(frame, sessions, "first_minute")
    cube.last = _cube(frame, sessions, "last_minute")
    cube.rows = np.arange(len(sessions))
    cube.source = "forward"
    cube.boundary_tolerance = 0
    cube._feature_cache = {}

    exact = (cube.first[:, 0, :] <= 0) & (cube.last[:, 77, :] >= 389)
    daily = np.where(exact, cube.closes[:, 77, :] / cube.opens[:, 0, :] - 1.0, np.nan)
    cube.prior_asset = np.full_like(daily, np.nan)
    for index in range(5, len(sessions)):
        window = daily[index - 5 : index]
        valid = np.isfinite(window).all(axis=0)
        cube.prior_asset[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
    cube.prior_spy = cube.prior_asset[:, 0]

    high = _cube(frame, sessions, "high")
    low = _cube(frame, sessions, "low")
    dollar = _cube(frame, sessions, "close_dollar_volume")
    volume = _cube(frame, sessions, "volume")
    valid_high = np.isfinite(high).any(axis=1)
    valid_low = np.isfinite(low).any(axis=1)
    cube.session_high = np.where(
        valid_high[:, None, :],
        np.maximum.accumulate(np.where(np.isfinite(high), high, -np.inf), axis=1),
        np.nan,
    )
    cube.session_low = np.where(
        valid_low[:, None, :],
        np.minimum.accumulate(np.where(np.isfinite(low), low, np.inf), axis=1),
        np.nan,
    )
    cube.cumulative_dollar = np.nancumsum(dollar, axis=1)
    cube.cumulative_volume = np.nancumsum(volume, axis=1)
    cube.vwap = np.divide(
        cube.cumulative_dollar,
        cube.cumulative_volume,
        out=np.full_like(cube.cumulative_dollar, np.nan),
        where=cube.cumulative_volume > 0,
    )
    cube._micro_cache = {}

    cube.prior1 = np.full_like(daily, np.nan)
    cube.prior20 = np.full_like(daily, np.nan)
    prior_close = np.full_like(daily, np.nan)
    cube.prior1[1:] = daily[:-1]
    prior_close[1:] = np.where(exact[:-1], cube.closes[:-1, 77, :], np.nan)
    cube.gap = cube.opens[:, 0, :] / prior_close - 1.0
    for index in range(20, len(sessions)):
        window = daily[index - 20 : index]
        valid = np.isfinite(window).all(axis=0)
        cube.prior20[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
    cube.bar_return = cube.closes / cube.opens - 1.0
    zero = np.zeros((len(sessions), 1, len(v12.SYMBOLS)))
    cube.bar_volume = np.diff(cube.cumulative_volume, axis=1, prepend=zero)
    cube._factor_cache = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        cube.factors(2)
    parent_cube = v34.Cube.__new__(v34.Cube)
    parent_cube.__dict__.update(cube.__dict__)
    parent_cube._feature_cache = {}
    parent_cube._micro_cache = {}
    parent_cube._factor_cache = {}
    cube._v11098_parent_cube = parent_cube
    return cube


def _factor_matrix(cube, factors, decision, assets):
    available = cube.factors(int(decision))
    return np.stack([available[name][:, assets] for name in factors], axis=2)


def _adapter_cache(cube) -> dict:
    if not hasattr(cube, "_v11098_adapter_cache"):
        cube._v11098_adapter_cache = {}
    return cube._v11098_adapter_cache


def _parent_signal(cube, parent: dict):
    key = ("parent_signal", id(parent))
    cache = _adapter_cache(cube)
    if key in cache:
        return cache[key]
    model = parent["fitted_signal_model"]
    specification = model["specification"]
    assets = np.asarray(specification["assets"], dtype=int)
    matrix = _factor_matrix(cube, model["factors"], specification["decision"], assets)
    score = np.einsum(
        "saf,f,f->sa",
        (matrix - np.asarray(model["mean"])) / np.asarray(model["scale"]),
        np.asarray(model["direction"]),
        np.asarray(model["weights"]),
    )
    score = np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)
    local = np.argmax(score, axis=1)
    selected = assets[local]
    active = np.isfinite(score[cube.rows, local]) & (
        score[cube.rows, local] >= float(model["threshold"])
    )
    cache[key] = (selected, active)
    return cache[key]


def _parent_exposure(cube, parent: dict, minimum_entry: int) -> np.ndarray:
    key = ("parent_exposure", id(parent), minimum_entry)
    cache = _adapter_cache(cube)
    if key in cache:
        return cache[key]
    selected, active = _parent_signal(cube, parent)
    model = parent["fitted_signal_model"]
    decision = int(model["specification"]["decision"])
    exit_bar = int(model["specification"]["exit"])
    entry = max(decision + 1, minimum_entry)
    active = active & (entry < exit_bar)
    active &= cube.first[cube.rows, entry, selected] <= entry * 5
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    raw = np.zeros(len(cube.sessions))
    raw[active] = (
        cube.opens[cube.rows[active], exit_bar, selected[active]]
        / cube.opens[cube.rows[active], entry, selected[active]]
        - 1.0
        - 0.0009
    )
    definition = parent["definition"]
    lookback = int(definition["lookback"])
    target = float(definition["target_volatility"])
    minimum = float(definition["minimum_exposure"])
    exposure = np.ones(len(raw))
    for index in range(lookback, len(raw)):
        realized = float(np.std(raw[index - lookback : index], ddof=1) * np.sqrt(252.0))
        if np.isfinite(realized) and realized > 1e-8:
            exposure[index] = np.clip(target / realized, minimum, 1.0)
    cache[key] = exposure
    return exposure


def _prior_state_score(cube, model: dict) -> np.ndarray:
    key = ("prior_state", id(model))
    cache = _adapter_cache(cube)
    if key in cache:
        return cache[key]
    factors = cube.factors(77)
    columns = []
    for name in model["names"]:
        current = np.asarray(factors[name][:, 0], dtype=float)
        columns.append(np.concatenate((np.asarray([np.nan]), current[:-1])))
    values = np.stack(columns, axis=1)
    score = np.mean(
        (values - np.asarray(model["mean"]))
        / np.asarray(model["scale"])
        * np.asarray(model["direction"]),
        axis=1,
    )
    cache[key] = score
    return score


def _daily_gate_score(cube, model: dict, decision: int) -> np.ndarray:
    key = ("daily_gate", id(model), decision)
    cache = _adapter_cache(cube)
    if key in cache:
        return cache[key]
    matrix = _factor_matrix(cube, model["factors"], decision, np.asarray((3, 4)))
    finite = np.isfinite(matrix)
    count = finite.sum(axis=1)
    daily = np.divide(
        np.where(finite, matrix, 0.0).sum(axis=1),
        count,
        out=np.full(count.shape, np.nan, dtype=float),
        where=count > 0,
    )
    score = np.einsum(
        "sf,f->s",
        (daily - np.asarray(model["mean"])) / np.asarray(model["scale"]),
        np.asarray(model["coefficients"]),
    )
    cache[key] = score
    return score


def _realized_quality(cube, index: int, selected: int, entry: int, exit_bar: int) -> bool:
    return bool(
        cube.first[index, entry, selected] <= entry * 5
        and cube.first[index, exit_bar, selected] <= exit_bar * 5
        and np.isfinite(cube.opens[index, entry, selected])
        and np.isfinite(cube.opens[index, exit_bar, selected])
        and np.isfinite(cube.opens[index, entry, 0])
        and np.isfinite(cube.opens[index, exit_bar, 0])
        and cube.opens[index, entry, selected] > 0
        and cube.opens[index, entry, 0] > 0
    )


def _opening_leg(
    cube, contract, index: int, modern: bool, require_realized_quality: bool
) -> LiveLeg | None:
    model = contract["opening_model"]
    assets = np.asarray((3, 4), dtype=int)
    matrix = _factor_matrix(cube, model["factors"], model["decision"], assets)
    score = np.einsum(
        "saf,f->sa",
        (matrix - np.asarray(model["mean"])) / np.asarray(model["scale"]),
        np.asarray(model["coefficients"]),
    )
    local = int(np.argmax(np.where(np.isfinite(matrix[index]).all(axis=1), score[index], -np.inf)))
    entry = int(model["decision"]) + 1
    exit_bar = int(model["exit_bar"])
    quality = not require_realized_quality or _realized_quality(
        cube, index, int(assets[local]), entry, exit_bar
    )
    if (
        not modern
        or not quality
        or not np.isfinite(score[index, local])
        or score[index, local] < model["threshold"]
    ):
        return None
    return LiveLeg(
        "opening",
        "opening_model",
        v12.SYMBOLS[int(assets[local])],
        int(model["decision"]),
        entry,
        exit_bar,
        1.0,
        1.0,
    )


def signals_for_session(
    cube,
    contract: dict,
    session_date: date,
    *,
    require_realized_quality: bool = False,
) -> tuple[LiveLeg, ...]:
    """Create the full causal leg schedule for one session without a broker."""

    dates = [pd.Timestamp(item).date() for item in cube.sessions]
    if session_date not in dates:
        raise ValueError("V11098_TARGET_SESSION_ABSENT")
    index = dates.index(session_date)
    if index < 60:
        raise ValueError("V11098_REQUIRES_60_PRIOR_SESSIONS")
    routing = contract["routing"]
    parent_cube = getattr(cube, "_v11098_parent_cube", cube)
    core_score = _prior_state_score(cube, routing["core_state_model"])
    override_score = _prior_state_score(cube, routing["override_state_model"])
    core_high = np.isfinite(core_score[index]) and (
        core_score[index] >= routing["core_state_model"]["threshold"]
    )
    override_low = np.isfinite(override_score[index]) and (
        override_score[index] < routing["override_state_model"]["threshold"]
    )
    modern = bool(core_high or ((not core_high) and override_low))
    transfer_score = _daily_gate_score(parent_cube, routing["transfer_gate_model"], 2)
    transfer_allowed = np.isfinite(transfer_score[index]) and (
        transfer_score[index] >= routing["transfer_gate_model"]["threshold"]
    )
    transfer_branch = (not modern) and bool(transfer_allowed)
    parent_id = (
        routing["modern_parent"]
        if modern
        else routing["transfer_parent"]
        if transfer_branch
        else routing["fallback_parent"]
    )
    minimum_entry = 11 if transfer_branch else 24
    outer = contract["outer_gate_model"]
    left = _daily_gate_score(cube, outer["left"], 5)
    right = _daily_gate_score(cube, outer["right"], 5)
    outer_allowed = (
        np.isfinite(left[index])
        and left[index] >= outer["left"]["threshold"]
        and np.isfinite(right[index])
        and right[index] >= outer["right"]["threshold"]
    )
    outer_exposure = (
        1.0 if outer_allowed else float(contract["execution"]["outer_gate_low_exposure"])
    )
    legs = []
    opening = _opening_leg(parent_cube, contract, index, modern, require_realized_quality)
    if opening is not None:
        legs.append(opening)
    parent = contract["parents"][parent_id]
    selected, active = _parent_signal(parent_cube, parent)
    exposure = _parent_exposure(parent_cube, parent, minimum_entry)[index]
    model = parent["fitted_signal_model"]
    entry = max(int(model["specification"]["decision"]) + 1, minimum_entry)
    exit_bar = int(model["specification"]["exit"])
    anchor_quality = not require_realized_quality or _realized_quality(
        parent_cube, index, int(selected[index]), entry, exit_bar
    )
    if active[index] and anchor_quality and exposure > 0:
        legs.append(
            LiveLeg(
                "anchor",
                parent_id,
                v12.SYMBOLS[int(selected[index])],
                int(model["specification"]["decision"]),
                entry,
                exit_bar,
                1.0,
                float(exposure) * outer_exposure,
            )
        )
        return tuple(legs)
    fill_score = _prior_state_score(cube, routing["fill_state_model"])
    fill_allowed = np.isfinite(fill_score[index]) and (
        fill_score[index] < routing["fill_state_model"]["threshold"]
    )
    if not fill_allowed:
        return tuple(legs)
    for fill_id, weight in zip(routing["fill_parents"], routing["fill_weights"], strict=True):
        fill_parent = contract["parents"][fill_id]
        selected, active = _parent_signal(parent_cube, fill_parent)
        exposure = _parent_exposure(parent_cube, fill_parent, minimum_entry)[index]
        model = fill_parent["fitted_signal_model"]
        entry = max(int(model["specification"]["decision"]) + 1, minimum_entry)
        exit_bar = int(model["specification"]["exit"])
        quality = not require_realized_quality or _realized_quality(
            parent_cube, index, int(selected[index]), entry, exit_bar
        )
        if not active[index] or not quality or exposure <= 0:
            continue
        legs.append(
            LiveLeg(
                "fill",
                fill_id,
                v12.SYMBOLS[int(selected[index])],
                int(model["specification"]["decision"]),
                entry,
                exit_bar,
                float(weight),
                float(exposure) * outer_exposure,
            )
        )
    return tuple(legs)


def leg_payloads(legs: tuple[LiveLeg, ...]) -> list[dict]:
    return [dataclasses.asdict(item) for item in legs]
