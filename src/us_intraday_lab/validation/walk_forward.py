import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime

from us_intraday_lab.contracts.validation import WalkForwardWindowResult
from us_intraday_lab.validation.splits import _validated_sessions

MAX_WALK_FORWARD_WINDOWS = 10_000


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    window_id: str
    train_sessions: tuple[date, ...]
    evaluation_sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        if type(self.window_id) is not str or not self.window_id:
            raise ValueError("window_id must be a non-empty string")
        for sessions in (self.train_sessions, self.evaluation_sessions):
            if type(sessions) is not tuple or not sessions:
                raise ValueError("window sessions must be non-empty exact tuples")
            if any(
                type(session) is not date or isinstance(session, datetime) for session in sessions
            ):
                raise TypeError("window sessions must contain exact date values")
            if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
                raise ValueError("window sessions must be sorted and unique")
        if self.train_sessions[-1] >= self.evaluation_sessions[0]:
            raise ValueError(
                "window train and evaluation sessions must be chronological and disjoint"
            )


def _positive_exact_int(value: int, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an exact integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _window_id(
    *,
    index: int,
    train: tuple[date, ...],
    evaluation: tuple[date, ...],
) -> str:
    payload = {
        "evaluation_sessions": [session.isoformat() for session in evaluation],
        "index": index,
        "train_sessions": [session.isoformat() for session in train],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "wf-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_walk_forward_windows(
    sessions: tuple[date, ...],
    *,
    train_size: int,
    evaluation_size: int,
    step_size: int,
) -> tuple[WalkForwardWindow, ...]:
    train_count = _positive_exact_int(train_size, "train_size")
    evaluation_count = _positive_exact_int(evaluation_size, "evaluation_size")
    step_count = _positive_exact_int(step_size, "step_size")
    ordered = _validated_sessions(sessions, minimum=train_count + evaluation_count)
    possible = 1 + (len(ordered) - train_count - evaluation_count) // step_count
    if possible > MAX_WALK_FORWARD_WINDOWS:
        raise ValueError("walk-forward configuration exceeds the window budget")
    windows: list[WalkForwardWindow] = []
    for index in range(possible):
        start = index * step_count
        train = ordered[start : start + train_count]
        evaluation = ordered[start + train_count : start + train_count + evaluation_count]
        windows.append(
            WalkForwardWindow(
                window_id=_window_id(index=index, train=train, evaluation=evaluation),
                train_sessions=train,
                evaluation_sessions=evaluation,
            )
        )
    return tuple(windows)


def record_walk_forward_result(
    window: WalkForwardWindow,
    *,
    strategy_id: str,
    base_net_return: float,
) -> WalkForwardWindowResult:
    if type(window) is not WalkForwardWindow:
        raise TypeError("window must be an exact WalkForwardWindow")
    if type(strategy_id) is not str or not strategy_id:
        raise ValueError("strategy_id must be a non-empty string")
    if type(base_net_return) not in {int, float} or not math.isfinite(base_net_return):
        raise ValueError("base_net_return must be a finite number")
    return WalkForwardWindowResult(
        window_id=window.window_id,
        strategy_id=strategy_id,
        train_start=window.train_sessions[0],
        train_end=window.train_sessions[-1],
        validation_start=window.evaluation_sessions[0],
        validation_end=window.evaluation_sessions[-1],
        metrics_by_cost_scenario={"base": {"net_return": float(base_net_return)}},
    )
