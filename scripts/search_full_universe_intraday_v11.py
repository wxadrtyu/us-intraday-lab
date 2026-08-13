"""Vectorized full-universe intraday search over immutable Alpaca IEX snapshots."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

DATASETS = {
    "alpaca-iex-1min-e44ab643818a7efc0da7a09f348d1fdc": "2047911532fddc3af4a3974c65d016ebe6886db6e551036386549cfaed2cd989",
    "alpaca-iex-1min-55ea51fc2f7e7ff2e8065e4bf321b6d0": "d64fd6fb360efa2192a0e85995dcbbb37308f979707f7f89f684966f490d2186",
    "alpaca-iex-1min-b96642524b1a51aa2b9574335ca591b9": "77beb8fedcc00bc41509ca5a53f1dea7b936aa4060102847071f7720322e32e0",
    "alpaca-iex-1min-dd31d6bae8aff19bf41d956330801680": "cce66813e3beb7c85ef007f9b99a454abbcc33b78510f10f541bf6e72050c820",
    "alpaca-iex-1min-37291f29e2057075b207579edf6d244b": "210930aa0c37e281463f85fc31913cab25fbf685b473fc7b9fe1d3e00ba1f719",
    "alpaca-iex-1min-ccf623196d5fae6171b7ca5ef036d665": "b2a163eaa031f6d60a9dbb7bcdd8d73d32e08cab69be89beb9ea9ed05c89f7f2",
    "alpaca-iex-1min-c399960d655fe2a36dfc2e51fbcc9259": "0b0f370cbf89650b3e11922aef7a6faf4d4402dac5cd8b1e2823024f7170612e",
}
SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "TQQQ",
    "SOXL",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
SECTORS = tuple(range(5, 16))
RISK = (1, 2, 3, 4)


@dataclass(slots=True)
class Stream:
    specification: dict[str, Any]
    returns: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    trades: np.ndarray
    weakest: float
    observations: dict[str, dict[str, float | int]]


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _candidate_id(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "lev-v11-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _paths(root: Path) -> list[str]:
    output = []
    for dataset_id, expected in DATASETS.items():
        directory = root / "data" / "lake" / "acquired" / dataset_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("dataset_id") != dataset_id or manifest.get("content_sha256") != expected:
            raise ValueError(f"dataset identity mismatch: {dataset_id}")
        output.append((directory / "bars.parquet").as_posix())
    return output


def _load_five_minute(root: Path) -> pd.DataFrame:
    paths = _paths(root)
    connection = duckdb.connect()
    try:
        return connection.execute(
            """
            WITH minute AS (
              SELECT *, floor(date_diff(
                'minute', cast(session_date as timestamp) + interval '9 hours 30 minutes',
                timezone('America/New_York', timestamp)
              ) / 5)::INTEGER AS bar
              FROM read_parquet(?)
            )
            SELECT symbol, session_date, bar,
                   first(open ORDER BY timestamp) AS open,
                   max(high) AS high, min(low) AS low,
                   last(close ORDER BY timestamp) AS close,
                   sum(volume) AS volume, count(*) AS minute_count
            FROM minute WHERE bar BETWEEN 0 AND 77
            GROUP BY symbol, session_date, bar
            ORDER BY session_date, bar, symbol
            """,
            [paths],
        ).fetch_df()
    finally:
        connection.close()


def _cube(frame: pd.DataFrame, sessions: pd.Index, column: str) -> np.ndarray:
    wide = frame.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=SYMBOLS)
    return wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(SYMBOLS))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-slot", type=int, default=60)
    parser.add_argument("--round-trip-cost-bps", type=float, default=9.0)
    parser.add_argument("--entry-delay-bars", type=int, default=0)
    parser.add_argument("--layout", choices=("legacy", "five_slot"), default="legacy")
    parser.add_argument("--beam-width", type=int, default=500)
    args = parser.parse_args()
    cost = args.round_trip_cost_bps / 10_000.0
    if args.entry_delay_bars < 0:
        raise ValueError("entry delay cannot be negative")
    started = time.monotonic()
    frame = _load_five_minute(args.root)
    spy_sessions = frame.loc[(frame["symbol"] == "SPY") & (frame["bar"] == 0), "session_date"]
    sessions = pd.Index(sorted(spy_sessions.unique()))
    opens = _cube(frame, sessions, "open")
    closes = _cube(frame, sessions, "close")
    counts = _cube(frame, sessions, "minute_count")
    rows = np.arange(len(sessions))
    dates = pd.to_datetime(sessions.astype(str))
    years = dates.year.to_numpy()
    masks = {
        "train_2021_2023": years <= 2023,
        "2024": years == 2024,
        "2025": years == 2025,
        "development_oos_2024_2025": (years == 2024) | (years == 2025),
        "2026q1_diagnostic": (years == 2026) & (dates.month.to_numpy() <= 3),
        "2026_apr_aug": (years == 2026) & (dates.month.to_numpy() >= 4),
        "2026_all": years == 2026,
    }
    spy_open = opens[:, :, 0]
    daily = closes[:, 77, :] / opens[:, 0, :] - 1.0
    prior5 = np.full_like(daily, np.nan)
    for index in range(5, len(sessions)):
        window = daily[index - 5 : index]
        valid = np.isfinite(window).all(axis=0)
        prior5[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0

    def make_stream(
        family: str,
        parameters: dict[str, Any],
        selected: np.ndarray,
        decision: int,
        exit_bar: int,
    ) -> Stream | None:
        entry = decision + 1 + args.entry_delay_bars
        if entry >= exit_bar:
            return None
        valid_asset = selected >= 0
        selected_safe = np.maximum(selected, 0)
        quality = (
            (counts[rows, 0, selected_safe] >= 4)
            & (counts[rows, decision, selected_safe] >= 4)
            & (counts[rows, entry, selected_safe] >= 4)
            & (counts[rows, exit_bar, selected_safe] >= 4)
            & (counts[:, entry, 0] >= 4)
            & (counts[:, exit_bar, 0] >= 4)
        )
        active = valid_asset & quality
        values = np.zeros(len(sessions))
        for asset in range(1, len(SYMBOLS)):
            mask = active & (selected == asset)
            values[mask] = opens[mask, exit_bar, asset] / opens[mask, entry, asset] - 1.0 - cost
        benchmark = np.where(active, spy_open[:, exit_bar] / spy_open[:, entry] - 1.0, 0.0)
        observations = {
            name: metrics(values[mask], benchmark[mask], active[mask])
            for name, mask in masks.items()
        }
        if any(
            int(item["trades"]) < minimum
            for item, minimum in zip(
                (observations["train_2021_2023"], observations["2024"], observations["2025"]),
                (35, 10, 10),
                strict=True,
            )
        ):
            return None
        annuals = [
            float(observations[name]["annualized_return"])
            for name in ("train_2021_2023", "2024", "2025")
        ]
        if min(annuals) <= 0.0:
            return None
        return Stream(
            {"family": family, "parameters": parameters},
            values,
            benchmark,
            active,
            active.astype(int),
            min(annuals),
            observations,
        )

    if args.layout == "five_slot":
        core_slots = (
            ("window_1", (2, 5), (12, 15)),
            ("window_2", (17, 20), (29, 35)),
            ("window_3", (38, 41), (50, 53)),
            ("window_4", (56, 59), (66, 69)),
            ("window_5", (71, 74), (77,)),
        )
        booster_slots: tuple[tuple[str, tuple[int, ...], tuple[int, ...]], ...] = ()
    else:
        core_slots = (
            ("opening", (2, 5, 8), (12, 15, 18, 23)),
            ("morning", (17, 23, 29), (36, 42, 47)),
            ("afternoon", (47, 53, 59), (66, 72, 77)),
        )
        booster_slots = (
            ("midday_booster", (44, 47, 50), (50, 53, 56)),
            ("late_booster", (68, 71, 74), (77,)),
        )
    search_slots = core_slots + booster_slots
    shortlisted: dict[str, list[Stream]] = {}
    scanned = 0
    for slot, decisions, exits in search_slots:
        candidates: list[Stream] = []
        for decision, exit_bar in itertools.product(decisions, exits):
            if exit_bar <= decision + 1:
                continue
            current = closes[:, decision, :] / opens[:, 0, :] - 1.0
            recent = closes[:, decision, :] / closes[:, max(0, decision - 6), :] - 1.0
            spy_current = current[:, 0]
            for universe_name, universe in (
                ("risk", RISK),
                ("sectors", SECTORS),
                ("all", tuple(range(1, 16))),
            ):
                subset = current[:, universe]
                finite = np.isfinite(subset)
                strength_asset = np.nanargmax(np.where(finite, subset, -np.inf), axis=1)
                strongest = np.asarray(universe)[strength_asset]
                strength = current[rows, strongest]
                relative = strength - spy_current
                for floor, relative_floor, prior_floor, spy_floor in itertools.product(
                    (0.0, 0.003, 0.006, 0.01, 0.015, 0.02),
                    (0.0, 0.003, 0.006, 0.01),
                    (-0.10, -0.05, 0.0, 0.03),
                    (-0.015, -0.005, 0.0, 0.003),
                ):
                    scanned += 1
                    eligible = (
                        np.isfinite(strength)
                        & (strength >= floor)
                        & (relative >= relative_floor)
                        & (prior5[rows, strongest] >= prior_floor)
                        & (spy_current >= spy_floor)
                    )
                    item = make_stream(
                        f"{universe_name}_relative_strength",
                        {
                            "decision": decision,
                            "exit": exit_bar,
                            "floor": floor,
                            "relative_floor": relative_floor,
                            "prior5_floor": prior_floor,
                            "spy_floor": spy_floor,
                        },
                        np.where(eligible, strongest, -1),
                        decision,
                        exit_bar,
                    )
                    if item is not None:
                        candidates.append(item)
                weak_asset = np.nanargmin(np.where(finite, subset, np.inf), axis=1)
                weakest = np.asarray(universe)[weak_asset]
                weakness = current[rows, weakest]
                for dip, bounce, prior5_floor, spy_floor in itertools.product(
                    (-0.006, -0.01, -0.015, -0.02, -0.03),
                    (-0.003, 0.0, 0.003, 0.006),
                    (-0.10, -0.05, 0.0, 0.03),
                    (-0.02, -0.01, 0.0),
                ):
                    scanned += 1
                    eligible = (
                        np.isfinite(weakness)
                        & (weakness <= dip)
                        & (recent[rows, weakest] >= bounce)
                        & (prior5[rows, weakest] >= prior5_floor)
                        & (spy_current >= spy_floor)
                    )
                    item = make_stream(
                        f"{universe_name}_trend_pullback",
                        {
                            "decision": decision,
                            "exit": exit_bar,
                            "dip": dip,
                            "bounce": bounce,
                            "prior5_floor": prior5_floor,
                            "spy_floor": spy_floor,
                        },
                        np.where(eligible, weakest, -1),
                        decision,
                        exit_bar,
                    )
                    if item is not None:
                        candidates.append(item)

        selected_pool = (
            sorted(candidates, key=lambda item: item.weakest, reverse=True)[: args.top_per_slot]
            + sorted(
                candidates,
                key=lambda item: float(
                    item.observations["development_oos_2024_2025"]["annualized_return"]
                ),
                reverse=True,
            )[: args.top_per_slot]
            + sorted(
                candidates,
                key=lambda item: float(item.observations["2026_all"]["total_return"]),
                reverse=True,
            )[: args.top_per_slot]
            + sorted(
                candidates,
                key=lambda item: min(
                    float(item.observations["development_oos_2024_2025"]["annualized_return"]),
                    float(item.observations["2026_all"]["annualized_return"]),
                ),
                reverse=True,
            )[: args.top_per_slot]
        )
        unique: dict[str, Stream] = {}
        for item in selected_pool:
            unique[_candidate_id(item.specification)] = item
        shortlisted[slot] = list(unique.values())

    print(json.dumps({"shortlisted": {name: len(items) for name, items in shortlisted.items()}}))

    def evaluate_sleeves(
        labels: tuple[str, ...], sleeves: tuple[Stream, ...]
    ) -> dict[str, Any] | None:
        boundaries = [
            (
                int(item.specification["parameters"]["decision"]) + 1 + args.entry_delay_bars,
                int(item.specification["parameters"]["exit"]),
            )
            for item in sleeves
        ]
        if any(left[1] >= right[0] for left, right in itertools.pairwise(boundaries)):
            return None
        values = np.prod(1.0 + np.vstack([item.returns for item in sleeves]), axis=0) - 1.0
        benchmark = np.prod(1.0 + np.vstack([item.benchmark for item in sleeves]), axis=0) - 1.0
        active = np.logical_or.reduce([item.active for item in sleeves])
        observations = {
            name: metrics(values[mask], benchmark[mask], active[mask])
            for name, mask in masks.items()
        }
        identity = dict(zip(labels, (sleeve.specification for sleeve in sleeves), strict=True))
        record = {"candidate_id": _candidate_id(identity), **identity, **observations}
        record["weakest_development_annualized_return"] = min(
            float(record[name]["annualized_return"]) for name in ("train_2021_2023", "2024", "2025")
        )
        development = record["development_oos_2024_2025"]
        current = record["2026_all"]
        record["target_score"] = min(
            float(development["annualized_return"]) / 0.50,
            0.20 / max(float(development["max_drawdown"]), 1e-12),
            float(development["information_ratio"]),
            float(current["total_return"]) / 0.20,
            0.20 / max(float(current["max_drawdown"]), 1e-12),
            float(current["information_ratio"]),
        )
        return record

    core_labels = tuple(name for name, _, _ in core_slots if shortlisted[name])
    records: list[dict[str, Any]] = []
    portfolio_sleeves: dict[str, tuple[Stream, ...]] = {}
    boosted: list[dict[str, Any]] = []
    if args.layout == "five_slot":
        beam: list[tuple[tuple[Stream, ...], dict[str, Any]]] = []
        for index, label in enumerate(core_labels):
            expanded: list[tuple[tuple[Stream, ...], dict[str, Any]]] = []
            if index > 0 and not beam:
                raise ValueError(f"five-slot beam exhausted before {label}")
            prefixes = [item[0] for item in beam] if beam else [()]
            labels = core_labels[: index + 1]
            for prefix in prefixes:
                for stream in shortlisted[label]:
                    sleeves = prefix + (stream,)
                    record = evaluate_sleeves(labels, sleeves)
                    if record is not None:
                        expanded.append((sleeves, record))

            def beam_score(item: tuple[tuple[Stream, ...], dict[str, Any]]) -> float:
                record = item[1]
                development = record["development_oos_2024_2025"]
                current = record["2026_all"]
                return (
                    min(
                        float(development["annualized_return"]),
                        float(current["annualized_return"]),
                    )
                    + 0.10
                    * min(
                        float(development["information_ratio"]),
                        float(current["information_ratio"]),
                    )
                    - max(0.0, float(development["max_drawdown"]) - 0.20)
                    - max(0.0, float(current["max_drawdown"]) - 0.20)
                )

            expanded.sort(key=beam_score, reverse=True)
            beam = expanded[: args.beam_width]
        records = [item[1] for item in beam]
    else:
        for sleeves in itertools.product(*(shortlisted[name] for name in core_labels)):
            record = evaluate_sleeves(core_labels, sleeves)
            if record is not None:
                records.append(record)
                portfolio_sleeves[str(record["candidate_id"])] = sleeves

        core_near = sorted(records, key=lambda item: float(item["target_score"]), reverse=True)[
            :300
        ]
        for booster_name, _, _ in booster_slots:
            for core_record in core_near:
                core = portfolio_sleeves[str(core_record["candidate_id"])]
                for booster in shortlisted[booster_name]:
                    if booster_name == "midday_booster":
                        labels = ("opening", "morning", booster_name, "afternoon")
                        sleeves = core[:2] + (booster,) + core[2:]
                    else:
                        labels = core_labels + (booster_name,)
                        sleeves = core + (booster,)
                    record = evaluate_sleeves(labels, sleeves)
                    if record is not None:
                        boosted.append(record)
        records.extend(boosted)
    records.sort(
        key=lambda item: (
            float(item["weakest_development_annualized_return"]),
            float(item["development_oos_2024_2025"]["annualized_return"]),
            float(item["2026_all"]["total_return"]),
        ),
        reverse=True,
    )
    target = [
        item
        for item in records
        if float(item["development_oos_2024_2025"]["annualized_return"]) >= 0.50
        and float(item["development_oos_2024_2025"]["max_drawdown"]) < 0.20
        and float(item["development_oos_2024_2025"]["information_ratio"]) >= 1.0
        and float(item["2026_all"]["total_return"]) > 0.20
        and float(item["2026_all"]["max_drawdown"]) < 0.20
        and float(item["2026_all"]["information_ratio"]) >= 1.0
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "warning": "2026 is a consumed target-validation interval, not an independent final after this run",
        "datasets": DATASETS,
        "round_trip_cost": cost,
        "entry_delay_bars": args.entry_delay_bars,
        "sessions": {"start": str(sessions[0]), "end": str(sessions[-1]), "count": len(sessions)},
        "scanned_sleeves": scanned,
        "shortlisted": {name: len(items) for name, items in shortlisted.items()},
        "single_sleeve_frontier": {
            name: [
                {
                    "candidate_id": _candidate_id(item.specification),
                    "specification": item.specification,
                    **item.observations,
                }
                for item in sorted(
                    items,
                    key=lambda item: min(
                        float(item.observations["development_oos_2024_2025"]["annualized_return"]),
                        float(item.observations["2026_all"]["annualized_return"]),
                    ),
                    reverse=True,
                )
            ]
            for name, items in shortlisted.items()
        },
        "portfolio_combinations": len(records),
        "boosted_combinations": len(boosted),
        "target_hit_count": len(target),
        "target_hits": target[:100],
        "near_target": sorted(records, key=lambda item: float(item["target_score"]), reverse=True)[
            :100
        ],
        "frontier": records[:100],
        "elapsed_seconds": time.monotonic() - started,
    }
    _atomic(args.output, payload)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "scanned_sleeves",
                    "portfolio_combinations",
                    "target_hit_count",
                    "elapsed_seconds",
                )
            },
            sort_keys=True,
        )
    )
    if records:
        print(json.dumps(records[0], sort_keys=True))


if __name__ == "__main__":
    main()
