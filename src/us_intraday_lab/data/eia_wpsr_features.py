"""Training-only, strictly lagged EIA release states and XLE opening-return exposure."""

from bisect import bisect_right
from datetime import date
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.data.eia_wpsr_archive import ROWS

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
FAMILIES = {
    "crude": ROWS[0],
    "gasoline": ROWS[1],
    "distillate": ROWS[2],
    "total": ROWS[3],
}


def load_training_event_cube(path: Path, expected_sha256: str) -> pd.DataFrame:
    """Verify the cube and push down the 2021-23 filter before reading values."""
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("event cube hash mismatch")
    return pd.read_parquet(
        path,
        columns=["symbol", "session_date", "bar_idx", "session_return"],
        filters=[[("session_date", ">=", TRAIN_START), ("session_date", "<=", TRAIN_END)]],
    )


def _states(releases: pd.DataFrame, sessions: list[date]) -> pd.DataFrame:
    needed = {"release_date", "row_name", "difference"}
    if missing := needed.difference(releases.columns):
        raise ValueError(f"EIA release columns missing: {sorted(missing)}")
    source = releases.copy()
    source["release_date"] = pd.to_datetime(source["release_date"]).dt.date
    if not source["release_date"].between(TRAIN_START, TRAIN_END).all():
        raise ValueError("release outside training period")
    if source.duplicated(["release_date", "row_name"]).any():
        raise ValueError("duplicate release row")
    if not set(source.row_name).issubset(ROWS):
        raise ValueError("unexpected Table 4 row")
    source["difference"] = pd.to_numeric(source["difference"], errors="coerce")
    if not np.isfinite(source["difference"]).all():
        raise ValueError("nonfinite Difference")
    wide = source.pivot(index="release_date", columns="row_name", values="difference")
    if wide.isna().any().any() or set(wide.columns) != set(ROWS):
        raise ValueError("incomplete release rows")
    wide = wide.sort_index().reset_index()
    for family, row_name in FAMILIES.items():
        prior_median = wide[row_name].shift(1).rolling(12, min_periods=12).median()
        wide[f"{family}_innovation"] = prior_median - wide[row_name]
        wide[f"{family}_draw"] = wide[f"{family}_innovation"].gt(0)
    wide["concordant_draw"] = wide[
        ["crude_draw", "gasoline_draw", "distillate_draw"]
    ].sum(axis=1).ge(2)
    wide["available_date"] = [
        sessions[position] if (position := bisect_right(sessions, release)) < len(sessions)
        else None
        for release in wide.release_date
    ]
    return wide


def _rolling_beta(paired: pd.DataFrame) -> pd.DataFrame:
    output = paired.sort_values("session_date").copy()
    x = output["xle_return"]
    y = output["session_return"]
    mean_x = x.rolling(60, min_periods=60).mean()
    mean_y = y.rolling(60, min_periods=60).mean()
    variance_x = x.mul(x).rolling(60, min_periods=60).mean() - mean_x.mul(mean_x)
    covariance = x.mul(y).rolling(60, min_periods=60).mean() - mean_x.mul(mean_y)
    output["beta"] = covariance.div(variance_x.where(variance_x.gt(0)))
    output["paired_count"] = np.minimum(np.arange(1, len(output) + 1), 60)
    output["xle_variance_zero"] = variance_x.notna() & variance_x.le(0)
    return output


def build_release_features(
    events: pd.DataFrame, releases: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build release states and prior-60-pair symbol betas without future returns."""
    required = {"symbol", "session_date", "bar_idx", "session_return"}
    if missing := required.difference(events.columns):
        raise ValueError(f"EIA event columns missing: {sorted(missing)}")
    training = events.copy()
    training["session_date"] = pd.to_datetime(training["session_date"]).dt.date
    training = training.loc[training.session_date.between(TRAIN_START, TRAIN_END)]
    if training.empty:
        raise ValueError("no training events")
    symbols = sorted(set(training.symbol) - {"XLE"})
    sessions = sorted(training.session_date.unique())
    states = _states(releases, sessions)
    opening = training.loc[training.bar_idx.eq(5),
                           ["symbol", "session_date", "session_return"]].copy()
    duplicate = opening.duplicated(["symbol", "session_date"], keep=False)
    states["duplicate_bar5_keys"] = int(
        opening.loc[duplicate, ["symbol", "session_date"]].drop_duplicates().shape[0]
    )
    opening = opening.loc[~duplicate]
    opening["session_return"] = pd.to_numeric(opening.session_return, errors="coerce")
    opening = opening.loc[np.isfinite(opening.session_return)]
    reference = opening.loc[opening.symbol.eq("XLE"), ["session_date", "session_return"]]
    if reference.empty:
        raise ValueError("missing XLE bar-5 reference")
    reference = reference.rename(columns={"session_return": "xle_return"})
    records: list[dict[str, object]] = []
    for symbol in symbols:
        observed = opening.loc[opening.symbol.eq(symbol), ["session_date", "session_return"]]
        paired = _rolling_beta(observed.merge(reference, on="session_date", how="inner"))
        dates = paired.session_date.tolist()
        for state in states.itertuples(index=False):
            if state.available_date is None:
                continue
            idx = bisect_right(dates, state.available_date) - 1
            if idx >= 0 and dates[idx] == state.available_date:
                idx -= 1
            prior = paired.iloc[idx] if idx >= 0 else None
            count = int(prior.paired_count) if prior is not None else 0
            beta = float(prior.beta) if prior is not None and pd.notna(prior.beta) else np.nan
            if count < 60:
                reason = "insufficient_pairs"
            elif bool(prior.xle_variance_zero):
                reason = "zero_reference_variance"
            elif not np.isfinite(beta):
                reason = "invalid_beta"
            elif beta <= 0:
                reason = "nonpositive_beta"
            else:
                reason = ""
            records.append({"release_date": state.release_date,
                            "available_date": state.available_date,
                            "symbol": symbol, "beta": beta,
                            "paired_count": count, "exclusion_reason": reason})
    exposures = pd.DataFrame.from_records(records)
    if exposures.empty:
        return states, exposures
    exposures["rank"] = pd.Series(pd.NA, index=exposures.index, dtype="Int64")
    eligible = exposures.loc[exposures.exclusion_reason.eq("")]
    for indices in eligible.groupby("release_date").groups.values():
        ordered = exposures.loc[indices].sort_values(["beta", "symbol"], ascending=[False, True])
        exposures.loc[ordered.index, "rank"] = range(1, len(ordered) + 1)
    return states, exposures.sort_values(["release_date", "symbol"]).reset_index(drop=True)
