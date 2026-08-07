import hashlib
import json
import random
from dataclasses import dataclass
from functools import reduce
from operator import mul
from types import MappingProxyType
from typing import Literal, cast

from us_intraday_lab.contracts.hypotheses import (
    HypothesisProposal,
    ParameterName,
    ParameterValue,
)
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.factory.feature_catalog import FEATURE_TEMPLATE_CATALOG, ParameterSpec
from us_intraday_lab.strategy.validator import validate_strategy

VARIANT_GENERATOR_VERSION = "variant-generator-1.3.0"
SelectionReason = Literal["baseline", "lower_boundary", "upper_boundary", "space_filling"]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class GeneratedVariant:
    variant_id: str
    content_sha256: str
    selection_reason: SelectionReason
    parameters: MappingProxyType[ParameterName, ParameterValue]
    definition: StrategyDefinition

    def canonical_json(self) -> str:
        return _canonical_json(self.definition.model_dump(mode="json"))


def _parameter_specs(entry_template: str) -> dict[ParameterName, ParameterSpec]:
    template = FEATURE_TEMPLATE_CATALOG.entry_templates[entry_template]
    return dict(template.parameters)


def _value_key(value: ParameterValue) -> tuple[int, float | str]:
    if type(value) in {int, float}:
        return (0, float(value))
    return (1, cast(str, value))


def _sorted_values(proposal: HypothesisProposal) -> dict[ParameterName, tuple[ParameterValue, ...]]:
    return {
        name: tuple(sorted(parameter_range.values, key=_value_key))
        for name, parameter_range in proposal.parameter_ranges.items()
    }


def _tuple_from_rank(
    rank: int,
    names: tuple[ParameterName, ...],
    values: dict[ParameterName, tuple[ParameterValue, ...]],
) -> tuple[ParameterValue, ...]:
    coordinates: list[ParameterValue] = [0] * len(names)
    remainder = rank
    for index in range(len(names) - 1, -1, -1):
        options = values[names[index]]
        remainder, option_index = divmod(remainder, len(options))
        coordinates[index] = options[option_index]
    return tuple(coordinates)


def _distance(
    left: tuple[ParameterValue, ...],
    right: tuple[ParameterValue, ...],
    names: tuple[ParameterName, ...],
    values: dict[ParameterName, tuple[ParameterValue, ...]],
    positions: dict[ParameterName, dict[ParameterValue, int]],
) -> float:
    total = 0.0
    for index, name in enumerate(names):
        options = values[name]
        if len(options) == 1:
            continue
        left_index = positions[name][left[index]]
        right_index = positions[name][right[index]]
        total += abs(left_index - right_index) / (len(options) - 1)
    return total / max(1, len(names))


def _selected_parameter_tuples(
    proposal: HypothesisProposal,
) -> tuple[tuple[tuple[ParameterValue, ...], SelectionReason], ...]:
    values = _sorted_values(proposal)
    names = tuple(values)
    specs = _parameter_specs(proposal.entry_template)
    baseline = tuple(specs[name].baseline for name in names)
    lower = tuple(values[name][0] for name in names)
    upper = tuple(values[name][-1] for name in names)
    forced: list[tuple[tuple[ParameterValue, ...], SelectionReason]] = []
    for candidate, reason in (
        (baseline, "baseline"),
        (lower, "lower_boundary"),
        (upper, "upper_boundary"),
    ):
        if candidate not in {item[0] for item in forced}:
            forced.append((candidate, cast(SelectionReason, reason)))
    total = reduce(mul, (len(values[name]) for name in names), 1)
    if total <= proposal.max_variants:
        all_candidates = [_tuple_from_rank(rank, names, values) for rank in range(total)]
        reason_by_candidate = dict(forced)
        return tuple(
            (candidate, reason_by_candidate.get(candidate, "space_filling"))
            for candidate in sorted(
                all_candidates,
                key=lambda item: (
                    0 if item == baseline else 1 if item == lower else 2 if item == upper else 3,
                    tuple(_value_key(value) for value in item),
                ),
            )
        )

    selected = forced.copy()
    selected_values = [candidate for candidate, _reason in selected]
    if len(selected) == proposal.max_variants:
        return tuple(selected)

    rng = random.Random(proposal.seed)
    pool_size = min(total, max(256, proposal.max_variants * 8))
    ranks = rng.sample(range(total), pool_size)
    pool = [_tuple_from_rank(rank, names, values) for rank in ranks]
    pool = list(dict.fromkeys(candidate for candidate in pool if candidate not in selected_values))
    rng.shuffle(pool)
    positions = {name: {value: index for index, value in enumerate(values[name])} for name in names}
    min_distances = [
        min(
            _distance(candidate, existing, names, values, positions) for existing in selected_values
        )
        for candidate in pool
    ]
    while pool and len(selected) < proposal.max_variants:
        best_index = max(range(len(pool)), key=min_distances.__getitem__)
        best = pool.pop(best_index)
        min_distances.pop(best_index)
        selected.append((best, "space_filling"))
        selected_values.append(best)
        for index, candidate in enumerate(pool):
            min_distances[index] = min(
                min_distances[index],
                _distance(candidate, best, names, values, positions),
            )
    return tuple(selected)


def _strategy_payload(
    parameters: dict[ParameterName, ParameterValue],
    *,
    entry_template: str,
    exit_template: str,
) -> dict[str, object]:
    if entry_template == "trend_dip":
        entry_conditions = [
            {"indicator": "ema_spread", "op": "gt", "value": parameters["ema_spread_min"]},
            {"indicator": "return_1", "op": "lt", "value": parameters["return_1_max"]},
            {
                "indicator": "range_position",
                "op": "lt",
                "value": parameters["range_position_max"],
            },
            {
                "indicator": "minutes_from_open",
                "op": "gt",
                "value": parameters["minutes_from_open_min"],
            },
        ]
    elif entry_template == "oversold_rebound":
        entry_conditions = [
            {"indicator": "rsi", "op": "lt", "value": parameters["rsi_entry"]},
            {
                "indicator": "vwap_distance_bps",
                "op": "lt",
                "value": parameters["vwap_distance_max"],
            },
            {"indicator": "return_1", "op": "lt", "value": parameters["return_1_max"]},
        ]
    elif entry_template == "late_dip_rebound":
        entry_conditions = [
            {
                "indicator": "vwap_distance_bps",
                "op": "lt",
                "value": parameters["vwap_distance_max"],
            },
            {"indicator": "return_1", "op": "lt", "value": parameters["return_1_max"]},
            {
                "indicator": "range_position",
                "op": "lt",
                "value": parameters["range_position_max"],
            },
            {
                "indicator": "minutes_from_open",
                "op": "gt",
                "value": parameters["minutes_from_open_min"],
            },
        ]
    else:
        rsi_operator = "gt" if entry_template == "trend_breakout" else "lt"
        entry_conditions = [
            {
                "indicator": "ema_spread",
                "op": "gt",
                "value": parameters["ema_spread_min"],
            },
            {
                "indicator": "rsi",
                "op": rsi_operator,
                "value": parameters["rsi_entry"],
            },
            {
                "indicator": "volume_ratio",
                "op": "gte",
                "value": parameters["volume_ratio_min"],
            },
        ]
    exit_condition = (
        {"indicator": "ema_spread", "op": "lt", "value": 0.0}
        if exit_template == "trend_failure"
        else {"indicator": "minutes_from_open", "op": "gte", "value": 390.0}
        if exit_template == "time_stop"
        else {"indicator": "rsi", "op": "gte", "value": 70.0}
    )
    return {
        "dsl_version": "1.0.0",
        "symbols": ["SPY", "QQQ", "IWM"],
        "signal_bar_size": "15min",
        "entry": {
            "all": entry_conditions
        },
        "exit": exit_condition,
        "risk": {
            "stop_loss_bps": parameters["stop_loss_bps"],
            "take_profit_bps": parameters["take_profit_bps"],
            "max_holding_minutes": parameters["max_holding_minutes"],
            "cooldown_minutes": parameters["cooldown_minutes"],
            "max_entries_per_session": parameters["max_entries_per_session"],
            "sizing_preset": parameters["sizing_preset"],
        },
        "order_type": parameters["order_type"],
    }


def _variant(
    searched: tuple[ParameterValue, ...],
    names: tuple[ParameterName, ...],
    reason: SelectionReason,
    *,
    entry_template: str,
    exit_template: str,
) -> GeneratedVariant:
    specs = _parameter_specs(entry_template)
    parameters: dict[ParameterName, ParameterValue] = {
        name: spec.baseline for name, spec in specs.items()
    }
    parameters.update(dict(zip(names, searched, strict=True)))
    payload = _strategy_payload(
        parameters,
        entry_template=entry_template,
        exit_template=exit_template,
    )
    definition_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    definition = StrategyDefinition.model_validate({"strategy_id": definition_hash[:16], **payload})
    validation = validate_strategy(definition)
    if not validation.passed:
        codes = ",".join(issue.code for issue in validation.issues)
        raise ValueError(f"generated strategy failed Plan 2 validation: {codes}")
    canonical = _canonical_json(definition.model_dump(mode="json"))
    return GeneratedVariant(
        variant_id=definition.strategy_id,
        content_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        selection_reason=reason,
        parameters=MappingProxyType(dict(sorted(parameters.items()))),
        definition=definition,
    )


def deduplicate_variants(variants: tuple[GeneratedVariant, ...]) -> tuple[GeneratedVariant, ...]:
    unique: dict[str, GeneratedVariant] = {}
    for variant in variants:
        if type(variant) is not GeneratedVariant:
            raise TypeError("variants must contain exact GeneratedVariant instances")
        unique.setdefault(variant.content_sha256, variant)
    return tuple(unique.values())


def generate_strategy_variants(
    proposal: HypothesisProposal,
) -> tuple[GeneratedVariant, ...]:
    if type(proposal) is not HypothesisProposal:
        raise TypeError("proposal must be an exact HypothesisProposal")
    reparsed = HypothesisProposal.model_validate(proposal)
    names = tuple(reparsed.parameter_ranges)
    selected = _selected_parameter_tuples(reparsed)
    variants = tuple(
        _variant(
            values,
            names,
            reason,
            entry_template=reparsed.entry_template,
            exit_template=reparsed.exit_template,
        )
        for values, reason in selected
    )
    return deduplicate_variants(variants)[: reparsed.max_variants]
