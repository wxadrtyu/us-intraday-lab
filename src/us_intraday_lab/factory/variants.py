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

VARIANT_GENERATOR_VERSION = "variant-generator-1.0.0"
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


def _parameter_specs() -> dict[ParameterName, ParameterSpec]:
    template = FEATURE_TEMPLATE_CATALOG.entry_templates["momentum_pullback"]
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
) -> float:
    total = 0.0
    for index, name in enumerate(names):
        options = values[name]
        if len(options) == 1:
            continue
        left_index = options.index(left[index])
        right_index = options.index(right[index])
        total += abs(left_index - right_index) / (len(options) - 1)
    return total / max(1, len(names))


def _selected_parameter_tuples(
    proposal: HypothesisProposal,
) -> tuple[tuple[tuple[ParameterValue, ...], SelectionReason], ...]:
    values = _sorted_values(proposal)
    names = tuple(values)
    specs = _parameter_specs()
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

    selected = forced[: proposal.max_variants]
    selected_values = [candidate for candidate, _reason in selected]
    if len(selected) == proposal.max_variants:
        return tuple(selected)

    rng = random.Random(proposal.seed)
    pool_size = min(total, max(256, proposal.max_variants * 32))
    ranks = rng.sample(range(total), pool_size)
    pool = [_tuple_from_rank(rank, names, values) for rank in ranks]
    pool = list(dict.fromkeys(candidate for candidate in pool if candidate not in selected_values))
    rng.shuffle(pool)
    while pool and len(selected) < proposal.max_variants:
        best = max(
            pool,
            key=lambda candidate: min(
                _distance(candidate, existing, names, values) for existing in selected_values
            ),
        )
        selected.append((best, "space_filling"))
        selected_values.append(best)
        pool.remove(best)
    return tuple(selected)


def _strategy_payload(parameters: dict[ParameterName, ParameterValue]) -> dict[str, object]:
    return {
        "dsl_version": "1.0.0",
        "symbols": ["SPY", "QQQ", "IWM"],
        "signal_bar_size": "15min",
        "entry": {
            "all": [
                {
                    "indicator": "ema_spread",
                    "op": "gt",
                    "value": parameters["ema_spread_min"],
                },
                {"indicator": "rsi", "op": "lt", "value": parameters["rsi_entry"]},
                {
                    "indicator": "volume_ratio",
                    "op": "gte",
                    "value": parameters["volume_ratio_min"],
                },
            ]
        },
        "exit": {"indicator": "rsi", "op": "gte", "value": 70.0},
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
) -> GeneratedVariant:
    specs = _parameter_specs()
    parameters: dict[ParameterName, ParameterValue] = {
        name: spec.baseline for name, spec in specs.items()
    }
    parameters.update(dict(zip(names, searched, strict=True)))
    payload = _strategy_payload(parameters)
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
    reparsed = HypothesisProposal.model_validate(proposal.model_dump(mode="json"))
    names = tuple(reparsed.parameter_ranges)
    selected = _selected_parameter_tuples(reparsed)
    variants = tuple(_variant(values, names, reason) for values, reason in selected)
    return deduplicate_variants(variants)[: reparsed.max_variants]
