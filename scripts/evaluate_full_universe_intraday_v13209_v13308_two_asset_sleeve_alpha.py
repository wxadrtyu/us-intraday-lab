"""Disjoint cross-sleeve factor triples with one- or two-asset sleeves."""

from __future__ import annotations

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import evaluate_full_universe_intraday_v13109_v13208_cross_sleeve_factor_alpha as prior

FIRST_VERSION = 13209
LAST_VERSION = 13308
PRIOR_COMPARISON_CELLS = 325_183
FAMILIES = prior.FAMILIES
VARIANTS = prior.VARIANTS


def _family_triple(first_family, variant):
    first = FAMILIES.index(first_family)
    return (
        FAMILIES[first],
        FAMILIES[variant],
        FAMILIES[(first + 3 * variant + 2) % len(FAMILIES)],
    )


def _definition_extra(model):
    value = prior._definition_extra(model)
    value["factor_design"] = "second_disjoint_latin_cross_sleeve_combinations"
    value["asset_diversification"] = "ranked_top_one_or_equal_weight_top_two"
    return value


def _configure() -> None:
    prior._family_triple = _family_triple
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = prior.ASSETS
    base.FACTOR_SETS = base.residual.FACTOR_SETS
    base.SCHEDULES = VARIANTS
    base.TOP_K = (1, 2)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "joint_gated_cross_sleeve_two_asset_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = prior._fit
    base._scores = prior._scores
    base._streams = prior._streams


if __name__ == "__main__":
    _configure()
    base.main()
