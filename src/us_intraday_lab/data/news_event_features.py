"""Pure point-in-time features from canonical Alpaca News metadata."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

LOOKBACKS = (
    ("30m", pd.Timedelta(minutes=30)),
    ("2h", pd.Timedelta(hours=2)),
    ("1d", pd.Timedelta(days=1)),
    ("5d", pd.Timedelta(days=5)),
)
LEXICAL_CATEGORIES = (
    "positive",
    "negative",
    "uncertainty",
    "earnings",
    "guidance",
    "financing",
    "litigation",
    "regulatory",
    "merger",
    "product",
)
_NEGATIONS = frozenset({"no", "not", "never", "without"})
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class NewsLexicon:
    categories: tuple[tuple[str, frozenset[str]], ...]

    def terms(self, category: str) -> frozenset[str]:
        for name, values in self.categories:
            if name == category:
                return values
        raise KeyError(category)


FROZEN_NEWS_LEXICON = NewsLexicon(
    categories=(
        ("positive", frozenset({"beat", "beats", "growth", "improve", "improves", "raise", "raises", "record", "strong"})),
        ("negative", frozenset({"cut", "cuts", "decline", "declines", "loss", "miss", "misses", "weak"})),
        ("uncertainty", frozenset({"could", "may", "risk", "uncertain", "uncertainty"})),
        ("earnings", frozenset({"earnings", "eps", "profit", "revenue"})),
        ("guidance", frozenset({"forecast", "guidance", "outlook"})),
        ("financing", frozenset({"debt", "financing", "offering", "placement"})),
        ("litigation", frozenset({"court", "lawsuit", "litigation", "settlement"})),
        ("regulatory", frozenset({"approval", "doj", "fda", "regulator", "sec"})),
        ("merger", frozenset({"acquire", "acquisition", "merger", "takeover"})),
        ("product", frozenset({"launch", "product", "release", "shipment"})),
    )
)


def _normalize(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).lower()


def _tokens(value: object) -> tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(_normalize(value)))


def _lexical_counts(tokens: tuple[str, ...], lexicon: NewsLexicon) -> dict[str, int]:
    result = {name: 0 for name in LEXICAL_CATEGORIES}
    for index, token in enumerate(tokens):
        negated = index > 0 and tokens[index - 1] in _NEGATIONS
        for name in LEXICAL_CATEGORIES:
            if token not in lexicon.terms(name):
                continue
            if negated and name == "positive":
                result["negative"] += 1
            elif negated and name == "negative":
                result["positive"] += 1
            else:
                result[name] += 1
    return result


def _story_hash(headline: object, summary: object) -> str:
    normalized = " ".join((*_tokens(headline), *_tokens(summary)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _article_features(articles: pd.DataFrame, lexicon: NewsLexicon) -> pd.DataFrame:
    prepared = articles.copy()
    lexical = []
    disagreement = []
    story_hashes = []
    for row in prepared.itertuples(index=False):
        headline_tokens = _tokens(row.headline)
        summary_tokens = _tokens(row.summary)
        headline_counts = _lexical_counts(headline_tokens, lexicon)
        summary_counts = _lexical_counts(summary_tokens, lexicon)
        lexical.append(
            {
                name: headline_counts[name] + summary_counts[name]
                for name in LEXICAL_CATEGORIES
            }
        )
        headline_sign = int(headline_counts["positive"] > headline_counts["negative"]) - int(
            headline_counts["negative"] > headline_counts["positive"]
        )
        summary_sign = int(summary_counts["positive"] > summary_counts["negative"]) - int(
            summary_counts["negative"] > summary_counts["positive"]
        )
        disagreement.append(
            float(headline_sign != 0 and summary_sign != 0 and headline_sign != summary_sign)
        )
        story_hashes.append(_story_hash(row.headline, row.summary))
    lexical_frame = pd.DataFrame.from_records(lexical, index=prepared.index)
    for name in LEXICAL_CATEGORIES:
        prepared[name] = lexical_frame.get(name, pd.Series(0, index=prepared.index))
    prepared["headline_summary_disagreement"] = disagreement
    prepared["story_hash"] = story_hashes
    prepared["multi_symbol"] = prepared["symbols"].map(len).gt(1).astype(float)
    prepared["symbol_breadth"] = prepared["symbols"].map(len).astype(float)
    return prepared


def _empty_features(result: pd.DataFrame) -> pd.DataFrame:
    for label, _ in LOOKBACKS:
        result[f"news_available_{label}"] = False
        result[f"article_count_{label}"] = 0
        result[f"decayed_article_count_{label}"] = 0.0
        result[f"unique_source_count_{label}"] = 0
        result[f"source_concentration_{label}"] = 0.0
        result[f"latest_news_age_seconds_{label}"] = np.nan
        result[f"multi_symbol_share_{label}"] = 0.0
        result[f"mean_symbol_breadth_{label}"] = 0.0
        result[f"headline_summary_disagreement_{label}"] = 0.0
        result[f"repeated_story_intensity_{label}"] = 0.0
        for name in LEXICAL_CATEGORIES:
            result[f"{name}_count_{label}"] = 0
    return result


def build_news_features(
    events: pd.DataFrame,
    articles: pd.DataFrame,
    lexicon: NewsLexicon,
    *,
    training_only: bool = True,
) -> pd.DataFrame:
    """Build deterministic features while preserving every input event row."""
    event_required = {"event_key", "symbol", "decision_timestamp"}
    article_required = {
        "news_id",
        "available_at",
        "source",
        "symbols",
        "headline",
        "summary",
    }
    if missing := event_required.difference(events.columns):
        raise ValueError(f"NEWS_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    if missing := article_required.difference(articles.columns):
        raise ValueError(f"NEWS_ARTICLE_COLUMNS_MISSING:{sorted(missing)}")
    if events["event_key"].duplicated().any():
        raise ValueError("NEWS_EVENT_KEY_DUPLICATE")
    result = events.copy().reset_index(drop=True)
    result["symbol"] = result["symbol"].astype("string").str.upper()
    result["decision_timestamp"] = pd.to_datetime(
        result["decision_timestamp"], utc=True, errors="raise"
    )
    if training_only and not result["decision_timestamp"].dt.year.between(2021, 2023).all():
        raise ValueError("NEWS_FEATURE_BUILD_TRAINING_ONLY")
    result = _empty_features(result)
    if result.empty or articles.empty:
        return result

    prepared = articles.copy()
    prepared["available_at"] = pd.to_datetime(
        prepared["available_at"], utc=True, errors="raise"
    )
    if prepared["news_id"].astype(str).duplicated().any():
        raise ValueError("NEWS_ARTICLE_ID_DUPLICATE")
    if not prepared["symbols"].map(lambda value: isinstance(value, (list, tuple))).all():
        raise TypeError("NEWS_ARTICLE_SYMBOLS_INVALID")
    prepared = _article_features(prepared, lexicon)
    exploded = prepared.explode("symbols", ignore_index=True).rename(
        columns={"symbols": "event_symbol"}
    )
    exploded["event_symbol"] = exploded["event_symbol"].astype("string").str.upper()
    grouped = {
        str(symbol): group.sort_values(
            ["available_at", "news_id"], kind="stable"
        ).reset_index(drop=True)
        for symbol, group in exploded.groupby("event_symbol", observed=True, sort=False)
    }

    for event_index, event in result.iterrows():
        symbol_articles = grouped.get(str(event["symbol"]))
        if symbol_articles is None:
            continue
        cutoff = cast(pd.Timestamp, event["decision_timestamp"])
        eligible = symbol_articles.loc[symbol_articles["available_at"].lt(cutoff)]
        for label, delta in LOOKBACKS:
            window = eligible.loc[eligible["available_at"].ge(cutoff - delta)]
            count = len(window)
            if count == 0:
                continue
            ages = (cutoff - window["available_at"]).dt.total_seconds()
            source_shares = window["source"].astype(str).value_counts(normalize=True)
            result.at[event_index, f"news_available_{label}"] = True
            result.at[event_index, f"article_count_{label}"] = count
            result.at[event_index, f"decayed_article_count_{label}"] = float(
                np.exp(-math.log(2.0) * ages / delta.total_seconds()).sum()
            )
            result.at[event_index, f"unique_source_count_{label}"] = int(
                window["source"].astype(str).nunique()
            )
            result.at[event_index, f"source_concentration_{label}"] = float(
                source_shares.max()
            )
            result.at[event_index, f"latest_news_age_seconds_{label}"] = float(
                ages.min()
            )
            result.at[event_index, f"multi_symbol_share_{label}"] = float(
                window["multi_symbol"].mean()
            )
            result.at[event_index, f"mean_symbol_breadth_{label}"] = float(
                window["symbol_breadth"].mean()
            )
            result.at[
                event_index, f"headline_summary_disagreement_{label}"
            ] = float(window["headline_summary_disagreement"].mean())
            result.at[event_index, f"repeated_story_intensity_{label}"] = float(
                1.0 - window["story_hash"].nunique() / count
            )
            for name in LEXICAL_CATEGORIES:
                result.at[event_index, f"{name}_count_{label}"] = int(
                    window[name].sum()
                )
    return result
