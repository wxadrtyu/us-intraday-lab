"""Deterministic event-driven minute backtest engine."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import floor, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

import pandas as pd

from us_intraday_lab.backtest.clock import BacktestClock
from us_intraday_lab.backtest.costs import COST_SCENARIOS, CostModel
from us_intraday_lab.backtest.fills import Fill, FillSimulator, MinuteBar
from us_intraday_lab.backtest.metrics import (
    EquityPoint,
    TradeRecord,
    compute_metrics,
)
from us_intraday_lab.backtest.portfolio import Portfolio, Position
from us_intraday_lab.contracts.backtests import (
    BacktestFailure,
    BacktestJob,
    BacktestResult,
    CostScenario,
)
from us_intraday_lab.contracts.orders import OrderIntent, OrderReasonCode
from us_intraday_lab.strategy.features import compute_feature_frame
from us_intraday_lab.strategy.operators import (
    AllOperator,
    AnyOperator,
    ComparisonOperator,
    CompiledStrategy,
    FeatureRow,
    RuleOperator,
)
from us_intraday_lab.strategy.runtime import (
    RuntimeKey,
    RuntimePhase,
    StrategyRuntime,
)

ENGINE_ID = "event-engine-1.0.0"
MAX_POSITIONS = 3
RISK_BUDGET_FRACTION = 0.005
_SCENARIO_ORDER: tuple[CostScenario, ...] = ("optimistic", "base", "stress")
_REQUIRED_MINUTE_COLUMNS = frozenset(
    {"symbol", "timestamp", "open", "high", "low", "close", "session_date"}
)
_REQUIRED_SIGNAL_BAR_COLUMNS = frozenset(
    {"symbol", "available_at", "open", "high", "low", "close", "volume", "session_date"}
)
EventType = Literal[
    "BAR_CLOSED_15M",
    "SIGNAL_ENTER_LONG",
    "SIGNAL_EXIT_LONG",
    "ORDER_INTENT_CREATED",
    "ORDER_ELIGIBLE",
    "ORDER_FILLED",
    "ORDER_CANCELLED",
    "ORDER_REJECTED",
    "POSITION_OPENED",
    "POSITION_CLOSED",
    "SESSION_FINALIZED",
]
JsonScalar = str | int | float | bool | None


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def run_id_for_job(job: BacktestJob) -> str:
    """Return a stable identifier from the complete canonical job JSON."""
    return "run-" + hashlib.sha256(job.canonical_json().encode("utf-8")).hexdigest()


def _session_date(value: object) -> date:
    if type(value) is date:
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    raise ValueError("session_date must contain date values")


def _utc_datetime(value: object, *, name: str) -> datetime:
    timestamp = pd.Timestamp(cast(str | int | float | date | datetime, value))
    if timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return timestamp.tz_convert("UTC").to_pydatetime()


def _as_float(value: object, *, name: str) -> float:
    normalized = float(cast(Any, value))
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class BacktestEvent:
    sequence: int
    event_type: EventType
    event_time: datetime
    scenario: CostScenario
    session: date
    symbol: str | None
    details: MappingProxyType[str, JsonScalar]

    def to_dict(self) -> dict[str, object]:
        return {
            "details": dict(sorted(self.details.items())),
            "event_time": _iso_utc(self.event_time),
            "event_type": self.event_type,
            "scenario": self.scenario,
            "sequence": self.sequence,
            "session": self.session.isoformat(),
            "symbol": self.symbol,
        }


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    cost_scenario: CostScenario
    events: tuple[BacktestEvent, ...]
    intents: tuple[OrderIntent, ...]
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[EquityPoint, ...]
    initial_cash: float
    final_cash: float
    final_positions: tuple[Position, ...]

    @property
    def metrics(self) -> MappingProxyType[str, float]:
        return MappingProxyType(
            compute_metrics(
                self.trades,
                self.equity_curve,
                initial_cash=self.initial_cash,
            )
        )

    def events_jsonl(self) -> str:
        return "".join(_canonical_json(event.to_dict()) + "\n" for event in self.events)

    def trades_jsonl(self) -> str:
        rows = []
        for trade in self.trades:
            rows.append(
                {
                    "cost_paid": trade.cost_paid,
                    "entry_price": trade.entry_price,
                    "entry_time": _iso_utc(trade.entry_time),
                    "exit_price": trade.exit_price,
                    "exit_time": _iso_utc(trade.exit_time),
                    "forced": trade.forced,
                    "gross_pnl": trade.gross_pnl,
                    "net_pnl": trade.net_pnl,
                    "quantity": trade.quantity,
                    "scenario": self.cost_scenario,
                    "session": trade.session.isoformat(),
                    "symbol": trade.symbol,
                }
            )
        return "".join(_canonical_json(row) + "\n" for row in rows)


@dataclass(frozen=True, slots=True)
class EngineRun:
    job: BacktestJob
    run_id: str
    scenarios: MappingProxyType[CostScenario, ScenarioRun]


class BacktestArtifactError(RuntimeError):
    """Artifact publication failed closed with a typed public failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.failure = BacktestFailure(failure_type="artifact_write", message=message)


def _is_reparse_path(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction()) or bool(attributes & reparse_flag)


def _artifact_parent(root: Path) -> Path:
    root_absolute = root.absolute()
    if not root_absolute.is_dir():
        raise BacktestArtifactError("artifact root must be an existing directory")
    if _is_reparse_path(root_absolute):
        raise BacktestArtifactError("artifact root must not be a symlink or reparse point")
    resolved_root = root_absolute.resolve(strict=True)
    artifacts = root_absolute / "artifacts"
    backtests = artifacts / "backtests"
    for candidate in (artifacts, backtests):
        if candidate.exists() and _is_reparse_path(candidate):
            raise BacktestArtifactError(
                f"artifact path contains a symlink or reparse point: {candidate.name}"
            )
    backtests.mkdir(parents=True, exist_ok=True)
    resolved_parent = backtests.resolve(strict=True)
    if not resolved_parent.is_relative_to(resolved_root):
        raise BacktestArtifactError("artifact path escapes the requested root")
    return resolved_parent


def _identical_complete_directory(directory: Path, expected: dict[str, bytes]) -> bool:
    if not directory.is_dir() or _is_reparse_path(directory):
        return False
    entries = tuple(directory.iterdir())
    if any(_is_reparse_path(path) for path in entries):
        return False
    actual_names = {path.name for path in entries}
    if actual_names != set(expected):
        return False
    return all(
        (directory / relative).is_file() and (directory / relative).read_bytes() == content
        for relative, content in expected.items()
    )


def _artifact_contents(run: EngineRun) -> dict[str, bytes]:
    events_content = "".join(run.scenarios[scenario].events_jsonl() for scenario in _SCENARIO_ORDER)
    trades_content = "".join(run.scenarios[scenario].trades_jsonl() for scenario in _SCENARIO_ORDER)
    metrics = {scenario: dict(run.scenarios[scenario].metrics) for scenario in _SCENARIO_ORDER}
    deterministic_identity = {
        "events_sha256": hashlib.sha256(events_content.encode("utf-8")).hexdigest(),
        "job": run.job.model_dump(mode="json"),
        "metrics_by_cost_scenario": metrics,
        "run_id": run.run_id,
        "trades_sha256": hashlib.sha256(trades_content.encode("utf-8")).hexdigest(),
    }
    content_sha256 = _sha256_json(deterministic_identity)
    relative_root = Path("artifacts") / "backtests" / run.run_id
    result = BacktestResult(
        schema_version="1.0.0",
        run_id=run.run_id,
        job_id=run.job.job_id,
        status="succeeded",
        failure=None,
        metrics_by_cost_scenario=metrics,
        trades_uri=(relative_root / "trades.jsonl").as_posix(),
        events_uri=(relative_root / "events.jsonl").as_posix(),
        content_sha256=content_sha256,
    )
    return {
        "events.jsonl": events_content.encode("utf-8"),
        "job.json": (run.job.canonical_json() + "\n").encode("utf-8"),
        "result.json": (_canonical_json(result.model_dump(mode="json")) + "\n").encode("utf-8"),
        "trades.jsonl": trades_content.encode("utf-8"),
    }


def write_backtest_artifacts(run: EngineRun, *, root: Path) -> Path:
    """Atomically publish deterministic artifacts and return ``result.json``."""
    if type(run) is not EngineRun:
        raise TypeError("run must be an exact EngineRun")
    if run.run_id != run_id_for_job(run.job):
        raise BacktestArtifactError("run_id does not match the canonical BacktestJob")
    temporary: Path | None = None
    try:
        expected = _artifact_contents(run)
        parent = _artifact_parent(root)
        final = parent / run.run_id
        if final.exists():
            if _identical_complete_directory(final, expected):
                return final / "result.json"
            raise BacktestArtifactError(
                f"artifact run directory already exists with different content: {run.run_id}"
            )
        temporary = Path(tempfile.mkdtemp(prefix=f".{run.run_id}-", dir=parent)).resolve(
            strict=True
        )
        if temporary.parent != parent or not temporary.name.startswith(f".{run.run_id}-"):
            raise BacktestArtifactError("temporary artifact directory escaped its parent")
        for relative, content in expected.items():
            (temporary / relative).write_text(
                content.decode("utf-8"),
                encoding="utf-8",
                newline="\n",
            )
        try:
            temporary.rename(final)
            temporary = None
        except OSError:
            if final.exists():
                if _identical_complete_directory(final, expected):
                    return final / "result.json"
                raise BacktestArtifactError(
                    f"artifact run directory already exists with different content: {run.run_id}"
                ) from None
            raise
        return final / "result.json"
    except BacktestArtifactError:
        raise
    except Exception as error:
        raise BacktestArtifactError(f"failed to publish backtest artifacts: {error}") from error
    finally:
        if temporary is not None and temporary.exists():
            try:
                shutil.rmtree(temporary)
            except Exception as error:
                raise BacktestArtifactError(
                    f"failed to clean temporary backtest artifacts: {error}"
                ) from error


@dataclass(slots=True)
class _PendingOrder:
    intent: OrderIntent
    reference_price: float
    forced: bool
    eligibility_emitted: bool = False


@dataclass(frozen=True, slots=True)
class _OpenTrade:
    symbol: str
    session: date
    quantity: int
    entry_time: datetime
    entry_price: float
    entry_cost: float


def _rule_matches(rule: RuleOperator, features: FeatureRow) -> bool:
    if type(rule) is ComparisonOperator:
        value = rule.indicator_fn(features)
        if value is None or pd.isna(value):
            return False
        normalized = float(value)
        if not isfinite(normalized):
            return False
        return rule.comparison_fn(normalized, rule.threshold)
    if type(rule) is AllOperator:
        return all(_rule_matches(child, features) for child in rule.children)
    if type(rule) is AnyOperator:
        return any(_rule_matches(child, features) for child in rule.children)
    raise TypeError("engine received an unsupported compiled rule")


class BacktestEngine:
    """Replay completed features and eligible orders against official minutes."""

    def __init__(self, *, job: BacktestJob, strategy: CompiledStrategy) -> None:
        if type(job) is not BacktestJob:
            raise TypeError("job must be an exact BacktestJob")
        if type(strategy) is not CompiledStrategy:
            raise TypeError("strategy must be an exact CompiledStrategy")
        if job.engine_id != ENGINE_ID:
            raise ValueError(f"unsupported engine_id: {job.engine_id}")
        if job.strategy_id != strategy.definition_fingerprint:
            raise ValueError(
                "BacktestJob strategy identity does not match compiled strategy definition"
            )
        expected_cost_ids = {
            scenario: COST_SCENARIOS[scenario].model_id for scenario in _SCENARIO_ORDER
        }
        if job.cost_model_ids.model_dump() != expected_cost_ids:
            raise ValueError("BacktestJob cost identities do not match configured v1 scenarios")
        self.job = job
        self.strategy = strategy
        self.run_id = run_id_for_job(job)

    def run(
        self,
        *,
        minute_bars: pd.DataFrame,
        signal_bars: pd.DataFrame,
    ) -> EngineRun:
        scenarios = {
            scenario: self.run_scenario(
                minute_bars=minute_bars,
                signal_bars=signal_bars,
                cost_scenario=scenario,
            )
            for scenario in _SCENARIO_ORDER
        }
        return EngineRun(
            job=self.job,
            run_id=self.run_id,
            scenarios=MappingProxyType(scenarios),
        )

    def run_scenario(
        self,
        *,
        minute_bars: pd.DataFrame,
        signal_bars: pd.DataFrame,
        cost_scenario: CostScenario,
    ) -> ScenarioRun:
        if cost_scenario not in _SCENARIO_ORDER:
            raise ValueError(f"unsupported cost scenario: {cost_scenario!r}")
        minute_frame = self._normalize_minute_bars(minute_bars)
        signal_frame = self._normalize_signal_bars(signal_bars)
        features = compute_feature_frame(signal_frame)
        portfolio = Portfolio(self.job.initial_cash, max_positions=MAX_POSITIONS)
        runtime = StrategyRuntime()
        simulator = FillSimulator(COST_SCENARIOS[cost_scenario])
        events: list[BacktestEvent] = []
        intents: list[OrderIntent] = []
        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []
        pending: dict[str, _PendingOrder] = {}
        open_trades: dict[str, _OpenTrade] = {}
        intent_keys: set[str] = set()

        def emit(
            event_type: EventType,
            event_time: datetime,
            session: date,
            *,
            symbol: str | None = None,
            **details: JsonScalar,
        ) -> None:
            events.append(
                BacktestEvent(
                    sequence=len(events) + 1,
                    event_type=event_type,
                    event_time=event_time,
                    scenario=cost_scenario,
                    session=session,
                    symbol=symbol,
                    details=MappingProxyType(dict(sorted(details.items()))),
                )
            )

        feature_rows = self._feature_rows(features, signal_frame)
        session_dates = tuple(
            sorted({_session_date(value) for value in minute_frame["session_date"]})
        )
        for session in session_dates:
            clock = BacktestClock(
                session_date=session,
                closeout_buffer_minutes=self.job.closeout_buffer_minutes,
            )
            minute_lookup = self._minute_lookup(
                minute_frame,
                session=session,
                clock=clock,
            )
            runtime_keys = {
                symbol: RuntimeKey(
                    strategy_id=self.strategy.strategy_id,
                    symbol=symbol,
                    session_date=session,
                )
                for symbol in self.strategy.symbols
            }

            for clock_time in clock.minutes:
                bars_now = {
                    symbol: minute_lookup[(symbol, clock_time)] for symbol in self.strategy.symbols
                }
                if clock_time < clock.closeout_signal_time:
                    for feature_row, reference_price in feature_rows.get(
                        (session, clock_time),
                        (),
                    ):
                        symbol = cast(str, feature_row["symbol"])
                        if symbol not in runtime_keys:
                            continue
                        emit(
                            "BAR_CLOSED_15M",
                            clock_time,
                            session,
                            symbol=symbol,
                            feature_set_version=cast(
                                str,
                                feature_row["feature_set_version"],
                            ),
                        )
                        key = runtime_keys[symbol]
                        state = runtime.state_for(key)
                        if state.phase is RuntimePhase.COOLDOWN and not runtime.cooldown_active(
                            key, clock_time=clock_time
                        ):
                            runtime.complete_cooldown(key, event_time=clock_time)
                            state = runtime.state_for(key)
                        if (
                            state.phase is RuntimePhase.FLAT
                            and state.entries < self.strategy.risk.max_entries_per_session
                            and _rule_matches(self.strategy.entry, feature_row)
                        ):
                            quantity = self._entry_quantity(
                                portfolio=portfolio,
                                reference_price=reference_price,
                                cost_model=COST_SCENARIOS[cost_scenario],
                            )
                            if quantity > 0:
                                self._submit_order(
                                    side="buy",
                                    reason_code="entry_signal",
                                    signal_time=clock_time,
                                    reference_price=reference_price,
                                    quantity=quantity,
                                    forced=False,
                                    session=session,
                                    symbol=symbol,
                                    runtime=runtime,
                                    runtime_key=key,
                                    portfolio=portfolio,
                                    pending=pending,
                                    intents=intents,
                                    intent_keys=intent_keys,
                                    cost_model=COST_SCENARIOS[cost_scenario],
                                    emit=emit,
                                )
                        elif state.phase is RuntimePhase.LONG and _rule_matches(
                            self.strategy.exit, feature_row
                        ):
                            position = next(
                                item for item in portfolio.positions if item.symbol == symbol
                            )
                            self._submit_order(
                                side="sell",
                                reason_code="exit_signal",
                                signal_time=clock_time,
                                reference_price=reference_price,
                                quantity=position.quantity,
                                forced=False,
                                session=session,
                                symbol=symbol,
                                runtime=runtime,
                                runtime_key=key,
                                portfolio=portfolio,
                                pending=pending,
                                intents=intents,
                                intent_keys=intent_keys,
                                cost_model=COST_SCENARIOS[cost_scenario],
                                emit=emit,
                            )

                self._process_orders(
                    pending,
                    clock_time=clock_time,
                    bars_now=bars_now,
                    session=session,
                    runtime=runtime,
                    runtime_keys=runtime_keys,
                    portfolio=portfolio,
                    simulator=simulator,
                    open_trades=open_trades,
                    trades=trades,
                    emit=emit,
                )
                if clock_time == clock.closeout_signal_time:
                    self._cancel_working_orders(
                        pending,
                        runtime=runtime,
                        runtime_keys=runtime_keys,
                        event_time=clock_time,
                        session=session,
                        portfolio=portfolio,
                        emit=emit,
                        side="buy",
                        reason="session_closeout_opening",
                    )
                    self._cancel_working_orders(
                        pending,
                        runtime=runtime,
                        runtime_keys=runtime_keys,
                        event_time=clock_time,
                        session=session,
                        portfolio=portfolio,
                        emit=emit,
                        side="sell",
                        reason="session_closeout_replaced",
                    )
                    for position in portfolio.positions:
                        bar = bars_now[position.symbol]
                        self._submit_order(
                            side="sell",
                            reason_code="session_close",
                            signal_time=clock_time,
                            reference_price=bar.open,
                            quantity=position.quantity,
                            forced=True,
                            session=session,
                            symbol=position.symbol,
                            runtime=runtime,
                            runtime_key=runtime_keys[position.symbol],
                            portfolio=portfolio,
                            pending=pending,
                            intents=intents,
                            intent_keys=intent_keys,
                            cost_model=COST_SCENARIOS[cost_scenario],
                            emit=emit,
                        )
                for position in portfolio.positions:
                    portfolio.mark_to_market(
                        position.symbol,
                        bars_now[position.symbol].close,
                    )
                equity_curve.append(
                    EquityPoint(
                        event_time=clock_time,
                        session=session,
                        equity=portfolio.equity,
                        gross_exposure=sum(
                            position.market_value for position in portfolio.positions
                        ),
                    )
                )
                if clock_time < clock.closeout_signal_time:
                    self._submit_risk_exits(
                        clock_time=clock_time,
                        bars_now=bars_now,
                        session=session,
                        runtime=runtime,
                        runtime_keys=runtime_keys,
                        portfolio=portfolio,
                        pending=pending,
                        intents=intents,
                        intent_keys=intent_keys,
                        cost_model=COST_SCENARIOS[cost_scenario],
                        emit=emit,
                    )

            if pending:
                self._cancel_working_orders(
                    pending,
                    runtime=runtime,
                    runtime_keys=runtime_keys,
                    event_time=clock.session_close,
                    session=session,
                    portfolio=portfolio,
                    emit=emit,
                    reason="session_closeout",
                )
            if portfolio.positions:
                raise RuntimeError("positions remained after deterministic closeout")
            for key in runtime_keys.values():
                runtime.close_session(key, event_time=clock.session_close)
            emit(
                "SESSION_FINALIZED",
                clock.session_close,
                session,
                cash=portfolio.cash,
                equity=portfolio.equity,
                order_count=len(portfolio.reservations),
                position_count=len(portfolio.positions),
            )
            if portfolio.positions or portfolio.reservations:
                raise RuntimeError("session finalization must be flat with no working orders")

        return ScenarioRun(
            cost_scenario=cost_scenario,
            events=tuple(events),
            intents=tuple(intents),
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            initial_cash=self.job.initial_cash,
            final_cash=portfolio.cash,
            final_positions=portfolio.positions,
        )

    def _normalize_minute_bars(self, bars: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(_REQUIRED_MINUTE_COLUMNS.difference(bars.columns))
        if missing:
            raise ValueError("minute bars lack required columns: " + ",".join(missing))
        if bars.empty:
            raise ValueError("minute bars must not be empty")
        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        frame["session_date"] = frame["session_date"].map(_session_date)
        if frame.duplicated(["symbol", "session_date", "timestamp"]).any():
            raise ValueError("minute bars must be unique by symbol, session, and timestamp")
        return frame.sort_values(
            ["session_date", "timestamp", "symbol"],
            kind="stable",
            ignore_index=True,
        )

    def _normalize_signal_bars(self, bars: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(_REQUIRED_SIGNAL_BAR_COLUMNS.difference(bars.columns))
        if missing:
            raise ValueError("signal bars lack required columns: " + ",".join(missing))
        frame = bars.copy()
        frame["available_at"] = pd.to_datetime(
            frame["available_at"],
            utc=True,
            errors="raise",
        )
        frame["session_date"] = frame["session_date"].map(_session_date)
        if frame.duplicated(["symbol", "session_date", "available_at"]).any():
            raise ValueError("signal bars must be unique by symbol, session, and boundary")
        return frame.sort_values(
            ["session_date", "available_at", "symbol"],
            kind="stable",
            ignore_index=True,
        )

    def _minute_lookup(
        self,
        frame: pd.DataFrame,
        *,
        session: date,
        clock: BacktestClock,
    ) -> dict[tuple[str, datetime], MinuteBar]:
        session_frame = frame.loc[frame["session_date"] == session]
        lookup: dict[tuple[str, datetime], MinuteBar] = {}
        for symbol in self.strategy.symbols:
            symbol_frame = session_frame.loc[session_frame["symbol"] == symbol]
            actual_minutes = tuple(
                _utc_datetime(value, name="timestamp") for value in symbol_frame["timestamp"]
            )
            if actual_minutes != clock.minutes:
                raise ValueError(
                    f"minute bars for {symbol}/{session} must exactly cover the official session"
                )
            for row in symbol_frame.itertuples(index=False):
                timestamp = _utc_datetime(row.timestamp, name="timestamp")
                lookup[(symbol, timestamp)] = MinuteBar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=_as_float(row.open, name="open"),
                    high=_as_float(row.high, name="high"),
                    low=_as_float(row.low, name="low"),
                    close=_as_float(row.close, name="close"),
                )
        return lookup

    @staticmethod
    def _feature_rows(
        features: pd.DataFrame,
        signal_bars: pd.DataFrame,
    ) -> dict[tuple[date, datetime], tuple[tuple[dict[str, Any], float], ...]]:
        close_by_key = {
            (
                _session_date(row.session_date),
                str(row.symbol),
                _utc_datetime(row.available_at, name="available_at"),
            ): _as_float(row.close, name="close")
            for row in signal_bars.itertuples(index=False)
        }
        grouped: dict[tuple[date, datetime], list[tuple[dict[str, Any], float]]] = {}
        for raw_row in features.to_dict(orient="records"):
            row = cast(dict[str, Any], raw_row)
            session = _session_date(row["session_date"])
            available_at = _utc_datetime(row["available_at"], name="available_at")
            symbol = cast(str, row["symbol"])
            grouped.setdefault((session, available_at), []).append(
                (
                    row,
                    close_by_key[(session, symbol, available_at)],
                )
            )
        return {
            key: tuple(sorted(rows, key=lambda item: cast(str, item[0]["symbol"])))
            for key, rows in grouped.items()
        }

    def _entry_quantity(
        self,
        *,
        portfolio: Portfolio,
        reference_price: float,
        cost_model: CostModel,
    ) -> int:
        occupied = len(portfolio.positions) + sum(
            reservation.side == "buy" for reservation in portfolio.reservations
        )
        free_slots = max(1, MAX_POSITIONS - occupied)
        adverse_price = reference_price * (1.0 + cost_model.price_impact_bps / 10_000)
        cash_quantity = floor((portfolio.available_cash / free_slots) / adverse_price)
        if self.strategy.risk.sizing_preset == "equal_cash_conservative":
            return max(0, cash_quantity)
        risk_per_share = reference_price * self.strategy.risk.stop_loss_bps / 10_000
        risk_quantity = floor(portfolio.equity * RISK_BUDGET_FRACTION / risk_per_share)
        return max(0, min(cash_quantity, risk_quantity))

    def _submit_order(
        self,
        *,
        side: Literal["buy", "sell"],
        reason_code: OrderReasonCode,
        signal_time: datetime,
        reference_price: float,
        quantity: int,
        forced: bool,
        session: date,
        symbol: str,
        runtime: StrategyRuntime,
        runtime_key: RuntimeKey,
        portfolio: Portfolio,
        pending: dict[str, _PendingOrder],
        intents: list[OrderIntent],
        intent_keys: set[str],
        cost_model: CostModel,
        emit: Any,
    ) -> None:
        signal: Literal["ENTER_LONG", "EXIT_LONG"] = "ENTER_LONG" if side == "buy" else "EXIT_LONG"
        runtime.record_signal(runtime_key, signal=signal, event_time=signal_time)
        runtime.transition(
            runtime_key,
            RuntimePhase.ENTRY_PENDING if side == "buy" else RuntimePhase.EXIT_PENDING,
            event_time=signal_time,
            reason=reason_code,
        )
        emit(
            "SIGNAL_ENTER_LONG" if side == "buy" else "SIGNAL_EXIT_LONG",
            signal_time,
            session,
            symbol=symbol,
            reason_code=reason_code,
        )
        eligible_time = signal_time + timedelta(minutes=1)
        order_type = "market" if forced else self.strategy.order_type
        limit_price = None
        if order_type == "limit":
            direction = 1.0 if side == "buy" else -1.0
            limit_price = reference_price * (1.0 + direction * cost_model.price_impact_bps / 10_000)
        identity = {
            "reason_code": reason_code,
            "run_id": self.run_id,
            "scenario": cost_model.model_id,
            "session": session.isoformat(),
            "side": side,
            "signal_time": _iso_utc(signal_time),
            "strategy_id": self.strategy.strategy_id,
            "symbol": symbol,
        }
        order_id = "order-" + _sha256_json(identity)
        if order_id in intent_keys:
            return
        intent = OrderIntent(
            schema_version="1.0.0",
            run_id=self.run_id,
            strategy_id=self.strategy.strategy_id,
            symbol=symbol,
            session=session,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            signal_time=signal_time,
            eligible_time=eligible_time,
            reason_code=reason_code,
            idempotency_key=order_id,
        )
        estimated_price = (
            limit_price
            if limit_price is not None
            else reference_price
            * (1.0 + (1.0 if side == "buy" else -1.0) * cost_model.price_impact_bps / 10_000)
        )
        try:
            portfolio.reserve_order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                estimated_price=estimated_price,
                estimated_fees=quantity * cost_model.commission_per_share_usd,
            )
        except ValueError as error:
            runtime.record_order_rejected(runtime_key, event_time=signal_time)
            emit(
                "ORDER_REJECTED",
                signal_time,
                session,
                symbol=symbol,
                order_id=order_id,
                reason=str(error),
                side=side,
            )
            return
        intent_keys.add(order_id)
        intents.append(intent)
        pending[order_id] = _PendingOrder(
            intent=intent,
            reference_price=reference_price,
            forced=forced,
        )
        emit(
            "ORDER_INTENT_CREATED",
            signal_time,
            session,
            symbol=symbol,
            order_id=order_id,
            reason_code=reason_code,
            side=side,
        )

    def _process_orders(
        self,
        pending: dict[str, _PendingOrder],
        *,
        clock_time: datetime,
        bars_now: dict[str, MinuteBar],
        session: date,
        runtime: StrategyRuntime,
        runtime_keys: dict[str, RuntimeKey],
        portfolio: Portfolio,
        simulator: FillSimulator,
        open_trades: dict[str, _OpenTrade],
        trades: list[TradeRecord],
        emit: Any,
    ) -> None:
        for order_id in sorted(pending):
            order = pending[order_id]
            if clock_time < order.intent.eligible_time:
                continue
            if not order.forced and not order.eligibility_emitted:
                emit(
                    "ORDER_ELIGIBLE",
                    clock_time,
                    session,
                    symbol=order.intent.symbol,
                    order_id=order_id,
                    side=order.intent.side,
                )
                order.eligibility_emitted = True
            bar = bars_now[order.intent.symbol]
            fill = simulator.try_fill(order.intent, bar)
            if fill is None:
                continue
            self._apply_fill(
                order,
                fill=fill,
                session=session,
                runtime=runtime,
                runtime_key=runtime_keys[order.intent.symbol],
                portfolio=portfolio,
                open_trades=open_trades,
                trades=trades,
                emit=emit,
                reference_bar=bar,
            )
            del pending[order_id]

    def _apply_fill(
        self,
        order: _PendingOrder,
        *,
        fill: Fill,
        session: date,
        runtime: StrategyRuntime,
        runtime_key: RuntimeKey,
        portfolio: Portfolio,
        open_trades: dict[str, _OpenTrade],
        trades: list[TradeRecord],
        emit: Any,
        reference_bar: MinuteBar,
    ) -> None:
        if order.intent.order_type == "market":
            reference_price = reference_bar.open
        else:
            reference_price = order.reference_price
        adverse_impact = (
            max(0.0, fill.price - reference_price)
            if fill.side == "buy"
            else max(0.0, reference_price - fill.price)
        )
        fill_cost = adverse_impact * fill.quantity + fill.fees
        closing_position = (
            next(
                (position for position in portfolio.positions if position.symbol == fill.symbol),
                None,
            )
            if fill.side == "sell"
            else None
        )
        try:
            portfolio.apply_fill(
                order_id=order.intent.idempotency_key,
                quantity=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                exit_reason=(
                    "end_of_day"
                    if order.intent.reason_code == "session_close"
                    else "strategy"
                    if fill.side == "sell"
                    else None
                ),
            )
        except ValueError as error:
            portfolio.cancel_order(order.intent.idempotency_key)
            runtime.record_order_rejected(runtime_key, event_time=fill.fill_time)
            emit(
                "ORDER_REJECTED",
                fill.fill_time,
                session,
                symbol=fill.symbol,
                order_id=order.intent.idempotency_key,
                reason=str(error),
                side=fill.side,
            )
            return
        emit(
            "ORDER_FILLED",
            fill.fill_time,
            session,
            symbol=fill.symbol,
            cost_paid=fill_cost,
            fees=fill.fees,
            order_id=order.intent.idempotency_key,
            price=fill.price,
            quantity=fill.quantity,
            side=fill.side,
        )
        if fill.side == "buy":
            runtime.mark_entry_filled(runtime_key, event_time=fill.fill_time)
            open_trades[fill.symbol] = _OpenTrade(
                symbol=fill.symbol,
                session=session,
                quantity=fill.quantity,
                entry_time=fill.fill_time,
                entry_price=fill.price,
                entry_cost=fill_cost,
            )
            emit(
                "POSITION_OPENED",
                fill.fill_time,
                session,
                symbol=fill.symbol,
                price=fill.price,
                quantity=fill.quantity,
            )
            return

        if closing_position is None:
            raise RuntimeError("sell fill completed without a tracked position")
        runtime.mark_exit_filled(
            runtime_key,
            event_time=fill.fill_time,
            cooldown_minutes=self.strategy.risk.cooldown_minutes,
        )
        opened = open_trades.pop(fill.symbol)
        net_pnl = fill.quantity * (fill.price - closing_position.average_cost) - fill.fees
        total_cost = opened.entry_cost + fill_cost
        trades.append(
            TradeRecord(
                symbol=fill.symbol,
                session=session,
                quantity=fill.quantity,
                entry_time=opened.entry_time,
                exit_time=fill.fill_time,
                entry_price=opened.entry_price,
                exit_price=fill.price,
                gross_pnl=net_pnl + total_cost,
                net_pnl=net_pnl,
                cost_paid=total_cost,
                forced=order.forced,
            )
        )
        emit(
            "POSITION_CLOSED",
            fill.fill_time,
            session,
            symbol=fill.symbol,
            forced=order.forced,
            net_pnl=net_pnl,
            price=fill.price,
            quantity=fill.quantity,
        )

    def _submit_risk_exits(
        self,
        *,
        clock_time: datetime,
        bars_now: dict[str, MinuteBar],
        session: date,
        runtime: StrategyRuntime,
        runtime_keys: dict[str, RuntimeKey],
        portfolio: Portfolio,
        pending: dict[str, _PendingOrder],
        intents: list[OrderIntent],
        intent_keys: set[str],
        cost_model: CostModel,
        emit: Any,
    ) -> None:
        signal_time = clock_time + timedelta(minutes=1)
        for position in portfolio.positions:
            key = runtime_keys[position.symbol]
            if runtime.state_for(key).phase is not RuntimePhase.LONG:
                continue
            bar = bars_now[position.symbol]
            return_bps = (bar.close / position.average_cost - 1.0) * 10_000
            holding_minutes = runtime.holding_minutes(key, clock_time=signal_time)
            reason: OrderReasonCode | None = None
            if return_bps <= -self.strategy.risk.stop_loss_bps:
                reason = "stop_loss"
            elif return_bps >= self.strategy.risk.take_profit_bps:
                reason = "take_profit"
            elif (
                holding_minutes is not None
                and holding_minutes >= self.strategy.risk.max_holding_minutes
            ):
                reason = "max_holding"
            if reason is None:
                continue
            self._submit_order(
                side="sell",
                reason_code=reason,
                signal_time=signal_time,
                reference_price=bar.close,
                quantity=position.quantity,
                forced=False,
                session=session,
                symbol=position.symbol,
                runtime=runtime,
                runtime_key=key,
                portfolio=portfolio,
                pending=pending,
                intents=intents,
                intent_keys=intent_keys,
                cost_model=cost_model,
                emit=emit,
            )

    @staticmethod
    def _cancel_working_orders(
        pending: dict[str, _PendingOrder],
        *,
        runtime: StrategyRuntime,
        runtime_keys: dict[str, RuntimeKey],
        event_time: datetime,
        session: date,
        portfolio: Portfolio,
        emit: Any,
        reason: str,
        side: Literal["buy", "sell"] | None = None,
    ) -> None:
        selected = (
            order_id
            for order_id, order in pending.items()
            if side is None or order.intent.side == side
        )
        for order_id in sorted(selected):
            order = pending.pop(order_id)
            portfolio.cancel_order(order_id)
            runtime.record_order_rejected(
                runtime_keys[order.intent.symbol],
                event_time=event_time,
            )
            emit(
                "ORDER_CANCELLED",
                event_time,
                session,
                symbol=order.intent.symbol,
                order_id=order_id,
                reason=reason,
                side=order.intent.side,
            )
