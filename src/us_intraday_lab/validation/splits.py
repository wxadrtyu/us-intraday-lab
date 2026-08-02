from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from us_intraday_lab.contracts.validation import ChronologicalSplit, chronological_split_counts

MAX_SPLIT_SESSIONS = 100_000


class FinalTestIsolationError(RuntimeError):
    """Raised when a caller crosses a sealed chronological phase boundary."""


def _validated_sessions(
    sessions: tuple[date, ...],
    *,
    minimum: int,
) -> tuple[date, ...]:
    if type(sessions) is not tuple:
        raise TypeError("sessions must be an exact tuple")
    if not minimum <= len(sessions) <= MAX_SPLIT_SESSIONS:
        raise ValueError(f"sessions must contain between {minimum} and {MAX_SPLIT_SESSIONS} items")
    if any(type(session) is not date or isinstance(session, datetime) for session in sessions):
        raise TypeError("sessions must contain exact date values")
    if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
        raise ValueError("sessions must be sorted and unique")
    return sessions


def create_chronological_split(
    sessions: tuple[date, ...],
    *,
    split_id: str,
) -> ChronologicalSplit:
    ordered = _validated_sessions(sessions, minimum=10)
    if type(split_id) is not str or not split_id:
        raise ValueError("split_id must be a non-empty string")
    train_count, validation_count, _final_count = chronological_split_counts(len(ordered))
    validation_end = train_count + validation_count
    return ChronologicalSplit(
        split_id=split_id,
        allocation_method="largest_remainder_70_20_10",
        train_sessions=ordered[:train_count],
        validation_sessions=ordered[train_count:validation_end],
        final_test_sessions=ordered[validation_end:],
    )


class IsolatedChronologicalViews:
    """Own phase-labelled data access and expose final test through a one-use capability."""

    def __init__(self, frame: pd.DataFrame, split: ChronologicalSplit) -> None:
        if type(frame) is not pd.DataFrame:
            raise TypeError("frame must be an exact pandas DataFrame")
        if type(split) is not ChronologicalSplit:
            raise TypeError("split must be an exact ChronologicalSplit")
        reparsed = ChronologicalSplit.model_validate(split)
        if "session_date" not in frame.columns:
            raise ValueError("frame must contain session_date")
        observed = frame["session_date"].tolist()
        if any(type(session) is not date or isinstance(session, datetime) for session in observed):
            raise ValueError("session_date must contain exact date values")
        declared = {
            *reparsed.train_sessions,
            *reparsed.validation_sessions,
            *reparsed.final_test_sessions,
        }
        observed_sessions = set(observed)
        if not observed_sessions <= declared:
            raise ValueError("frame contains sessions outside the chronological split")
        if observed_sessions != declared:
            raise ValueError("frame must exactly cover every declared split session")
        self._frame = frame.copy(deep=True)
        self._split = reparsed
        self._access_log: list[str] = []
        self._selection_sealed = False
        self._sealed_survivor_ids: tuple[str, ...] | None = None
        self._selection_manifest_sha256: str | None = None
        self._final_consumed = False

    @property
    def access_log(self) -> tuple[str, ...]:
        return tuple(self._access_log)

    def _search_view(self, phase: str, sessions: tuple[date, ...]) -> pd.DataFrame:
        if self._final_consumed:
            raise FinalTestIsolationError("FINAL_TEST_ALREADY_CONSUMED")
        if self._selection_sealed:
            raise FinalTestIsolationError("SELECTION_ALREADY_SEALED")
        self._access_log.append(phase)
        return self._frame.loc[self._frame["session_date"].isin(sessions)].copy(deep=True)

    def training_view(self) -> pd.DataFrame:
        return self._search_view("train", self._split.train_sessions)

    def validation_view(self) -> pd.DataFrame:
        return self._search_view("validation", self._split.validation_sessions)

    def seal_selection(
        self,
        *,
        survivor_ids: tuple[str, ...],
        selection_manifest_sha256: str,
    ) -> FinalTestEvaluator:
        if type(survivor_ids) is not tuple or not 1 <= len(survivor_ids) <= 200:
            raise ValueError("survivor_ids must contain between 1 and 200 strategy IDs")
        if any(type(strategy_id) is not str or not strategy_id for strategy_id in survivor_ids):
            raise ValueError("survivor_ids must contain non-empty strings")
        if tuple(sorted(survivor_ids)) != survivor_ids or len(set(survivor_ids)) != len(
            survivor_ids
        ):
            raise ValueError("survivor_ids must be sorted and unique")
        if (
            type(selection_manifest_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", selection_manifest_sha256) is None
        ):
            raise ValueError("selection_manifest_sha256 must be a lowercase SHA-256 digest")
        if self._final_consumed:
            raise FinalTestIsolationError("FINAL_TEST_ALREADY_CONSUMED")
        if self._selection_sealed:
            raise FinalTestIsolationError("SELECTION_ALREADY_SEALED")
        if not {"train", "validation"} <= set(self._access_log):
            raise FinalTestIsolationError("SELECTION_EVIDENCE_NOT_READ")
        self._sealed_survivor_ids = survivor_ids
        self._selection_manifest_sha256 = selection_manifest_sha256
        self._selection_sealed = True
        return FinalTestEvaluator(self)

    def _sealed_identity(self) -> tuple[tuple[str, ...], str]:
        if (
            not self._selection_sealed
            or self._sealed_survivor_ids is None
            or self._selection_manifest_sha256 is None
        ):
            raise FinalTestIsolationError("SELECTION_NOT_SEALED")
        return self._sealed_survivor_ids, self._selection_manifest_sha256

    def _consume_final_test(self, *, strategy_ids: tuple[str, ...]) -> pd.DataFrame:
        if not self._selection_sealed:
            raise FinalTestIsolationError("SELECTION_NOT_SEALED")
        if self._final_consumed:
            raise FinalTestIsolationError("FINAL_TEST_ALREADY_CONSUMED")
        sealed_survivor_ids, _manifest_hash = self._sealed_identity()
        if type(strategy_ids) is not tuple or strategy_ids != sealed_survivor_ids:
            raise FinalTestIsolationError("UNSEALED_STRATEGY_REQUEST")
        self._final_consumed = True
        self._access_log.append("final_test")
        return self._frame.loc[
            self._frame["session_date"].isin(self._split.final_test_sessions)
        ].copy(deep=True)


class FinalTestEvaluator:
    """Capability granted only when strategy selection has been sealed."""

    def __init__(
        self,
        owner: IsolatedChronologicalViews,
    ) -> None:
        if type(owner) is not IsolatedChronologicalViews:
            raise TypeError("owner must be an exact IsolatedChronologicalViews")
        self._owner = owner

    @property
    def survivor_ids(self) -> tuple[str, ...]:
        survivor_ids, _manifest_hash = self._owner._sealed_identity()
        return survivor_ids

    @property
    def selection_manifest_sha256(self) -> str:
        _survivor_ids, manifest_hash = self._owner._sealed_identity()
        return manifest_hash

    def final_test_view(self, *, strategy_ids: tuple[str, ...]) -> pd.DataFrame:
        return self._owner._consume_final_test(strategy_ids=strategy_ids)
