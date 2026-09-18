"""Official SEC Form 4 insider-flow training data contract."""

from __future__ import annotations

from io import BytesIO, TextIOWrapper
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd

BASE_URL = (
    "https://www.sec.gov/files/structureddata/data/"
    "insider-transactions-data-sets/{year}q{quarter}_form345.zip"
)
_TABLE_FILES = {
    "submission": "SUBMISSION.tsv",
    "reportingowner": "REPORTINGOWNER.tsv",
    "nonderiv_trans": "NONDERIV_TRANS.tsv",
}
_REQUIRED_COLUMNS = {
    "submission": {
        "ACCESSION_NUMBER",
        "FILING_DATE",
        "PERIOD_OF_REPORT",
        "DOCUMENT_TYPE",
        "ISSUERCIK",
        "ISSUERNAME",
        "ISSUERTRADINGSYMBOL",
    },
    "reportingowner": {
        "ACCESSION_NUMBER",
        "RPTOWNERCIK",
        "RPTOWNERNAME",
        "RPTOWNER_RELATIONSHIP",
        "RPTOWNER_TITLE",
    },
    "nonderiv_trans": {
        "ACCESSION_NUMBER",
        "NONDERIV_TRANS_SK",
        "TRANS_DATE",
        "TRANS_CODE",
        "EQUITY_SWAP_INVOLVED",
        "TRANS_TIMELINESS",
        "TRANS_SHARES",
        "TRANS_PRICEPERSHARE",
        "TRANS_ACQUIRED_DISP_CD",
        "SHRS_OWND_FOLWNG_TRANS",
        "DIRECT_INDIRECT_OWNERSHIP",
    },
}
TRAIN_START = pd.Timestamp("2021-01-01").date()
TRAIN_END = pd.Timestamp("2023-12-31").date()
FEATURE_COLUMNS = (
    "insider_purchase_notional",
    "insider_purchase_holding_fraction",
    "insider_purchase_owner_cluster",
    "insider_officer_director_purchase",
    "insider_net_purchase_balance",
)


def quarter_urls() -> tuple[str, ...]:
    """Return the frozen official 2021-2023 quarterly bulk-file URLs."""
    return tuple(
        BASE_URL.format(year=year, quarter=quarter)
        for year in range(2021, 2024)
        for quarter in range(1, 5)
    )


def parse_quarter_zip(body: bytes, source: str) -> dict[str, pd.DataFrame]:
    """Parse and validate the three documented tables required by the contract."""
    try:
        with ZipFile(BytesIO(body)) as archive:
            names = set(archive.namelist())
            missing_files = set(_TABLE_FILES.values()).difference(names)
            if missing_files:
                raise ValueError(
                    f"SEC_FORM4_ZIP_TABLES_MISSING:{sorted(missing_files)}:{source}"
                )
            tables = {
                key: pd.read_csv(
                    TextIOWrapper(archive.open(filename), encoding="utf-8"),
                    sep="\t",
                    dtype=str,
                    keep_default_na=False,
                )
                for key, filename in _TABLE_FILES.items()
            }
    except BadZipFile:
        raise ValueError(f"SEC_FORM4_ZIP_INVALID:{source}") from None
    for key, frame in tables.items():
        if missing := _REQUIRED_COLUMNS[key].difference(frame.columns):
            raise ValueError(
                f"SEC_FORM4_{key.upper()}_COLUMNS_MISSING:{sorted(missing)}:{source}"
            )
        frame["_source"] = source
    if tables["submission"].duplicated("ACCESSION_NUMBER").any():
        raise ValueError("SEC_FORM4_SUBMISSION_KEY_DUPLICATE")
    if tables["reportingowner"].duplicated(
        ["ACCESSION_NUMBER", "RPTOWNERCIK"]
    ).any():
        raise ValueError("SEC_FORM4_REPORTINGOWNER_KEY_DUPLICATE")
    if tables["nonderiv_trans"].duplicated(
        ["ACCESSION_NUMBER", "NONDERIV_TRANS_SK"]
    ).any():
        raise ValueError("SEC_FORM4_NONDERIV_TRANS_KEY_DUPLICATE")
    return tables


def _empty_filings() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "cik",
            "accession",
            "filing_date",
            "period_of_report",
            "purchase_notional",
            "sale_notional",
            "net_open_market_balance",
            "unique_purchasing_owners",
            "officer_director_purchase_share",
            "purchase_to_post_holding",
            "transaction_filing_lag_days",
            "late_reported",
            "qualifying_transaction_count",
            "source",
        ]
    )


def normalize_form4_filings(
    tables: dict[str, pd.DataFrame], identities: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize exact-CIK original Form 4 open-market P/S filing aggregates."""
    if missing := set(_TABLE_FILES).difference(tables):
        raise ValueError(f"SEC_FORM4_TABLES_MISSING:{sorted(missing)}")
    if missing := {"symbol", "cik"}.difference(identities.columns):
        raise ValueError(f"SEC_FORM4_IDENTITY_COLUMNS_MISSING:{sorted(missing)}")
    submissions = tables["submission"].copy()
    owners = tables["reportingowner"].copy()
    transactions = tables["nonderiv_trans"].copy()
    accessions = set(submissions["ACCESSION_NUMBER"].astype(str))
    if not set(transactions["ACCESSION_NUMBER"].astype(str)).issubset(accessions):
        raise ValueError("SEC_FORM4_TRANSACTION_ACCESSION_ORPHAN")
    if not set(owners["ACCESSION_NUMBER"].astype(str)).issubset(accessions):
        raise ValueError("SEC_FORM4_OWNER_ACCESSION_ORPHAN")
    joined = transactions.merge(
        submissions,
        on="ACCESSION_NUMBER",
        how="left",
        validate="many_to_one",
        suffixes=("_transaction", "_submission"),
    )
    joined["filing_date"] = pd.to_datetime(
        joined["FILING_DATE"], format="%d-%b-%Y", errors="coerce"
    )
    joined["transaction_date"] = pd.to_datetime(
        joined["TRANS_DATE"], format="%d-%b-%Y", errors="coerce"
    )
    joined["shares"] = pd.to_numeric(joined["TRANS_SHARES"], errors="coerce")
    joined["price"] = pd.to_numeric(
        joined["TRANS_PRICEPERSHARE"], errors="coerce"
    )
    joined["post_holding"] = pd.to_numeric(
        joined["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"
    )
    reasons = pd.Series("", index=joined.index, dtype="object")
    reasons = reasons.mask(
        ~joined["DOCUMENT_TYPE"].eq("4"), "SEC_FORM4_NOT_ORIGINAL_FORM4"
    )
    ps = joined["TRANS_CODE"].isin({"P", "S"})
    reasons = reasons.mask(reasons.eq("") & ~ps, "SEC_FORM4_NOT_OPEN_MARKET_PS")
    direction_ok = (
        joined["TRANS_CODE"].eq("P")
        & joined["TRANS_ACQUIRED_DISP_CD"].eq("A")
    ) | (
        joined["TRANS_CODE"].eq("S")
        & joined["TRANS_ACQUIRED_DISP_CD"].eq("D")
    )
    reasons = reasons.mask(
        reasons.eq("") & ~direction_ok, "SEC_FORM4_DIRECTION_MISMATCH"
    )
    swap = joined["EQUITY_SWAP_INVOLVED"].str.strip().str.lower().isin(
        {"1", "true", "yes"}
    )
    reasons = reasons.mask(reasons.eq("") & swap, "SEC_FORM4_EQUITY_SWAP")
    finite_value = (
        joined["shares"].notna()
        & joined["price"].notna()
        & joined["shares"].gt(0)
        & joined["price"].gt(0)
    )
    reasons = reasons.mask(
        reasons.eq("") & ~finite_value, "SEC_FORM4_VALUE_MISSING"
    )
    valid_dates = joined["filing_date"].notna() & joined["transaction_date"].notna()
    reasons = reasons.mask(
        reasons.eq("") & ~valid_dates, "SEC_FORM4_DATE_INVALID"
    )
    reasons = reasons.mask(
        reasons.eq("")
        & valid_dates
        & joined["transaction_date"].gt(joined["filing_date"]),
        "SEC_FORM4_TRANSACTION_AFTER_FILING",
    )
    identity = identities[["symbol", "cik"]].copy()
    identity["cik"] = pd.to_numeric(identity["cik"], errors="raise").astype("int64")
    joined["cik"] = pd.to_numeric(joined["ISSUERCIK"], errors="coerce")
    known_ciks = set(identity["cik"])
    reasons = reasons.mask(
        reasons.eq("") & ~joined["cik"].isin(known_ciks),
        "SEC_FORM4_IDENTITY_UNAVAILABLE",
    )
    rejected = joined.loc[reasons.ne(""), ["ACCESSION_NUMBER"]].copy()
    rejected["reason"] = reasons.loc[reasons.ne("")].to_numpy()
    rejected = rejected.rename(columns={"ACCESSION_NUMBER": "accession"})
    valid = joined.loc[reasons.eq("")].copy()
    if valid.empty:
        return _empty_filings(), rejected.reset_index(drop=True)
    valid["notional"] = valid["shares"] * valid["price"]
    valid["purchase_notional"] = valid["notional"].where(
        valid["TRANS_CODE"].eq("P"), 0.0
    )
    valid["sale_notional"] = valid["notional"].where(
        valid["TRANS_CODE"].eq("S"), 0.0
    )
    valid["purchased_shares"] = valid["shares"].where(
        valid["TRANS_CODE"].eq("P"), 0.0
    )
    owner_groups = owners.groupby("ACCESSION_NUMBER", observed=True)
    owner_count = owner_groups["RPTOWNERCIK"].nunique()
    officer_director = owner_groups["RPTOWNER_RELATIONSHIP"].apply(
        lambda values: bool(
            values.astype(str)
            .str.lower()
            .str.contains("officer|director", regex=True)
            .any()
        )
    )
    records: list[dict[str, object]] = []
    group_columns = ["ACCESSION_NUMBER", "cik"]
    for (accession, cik_value), group in valid.groupby(
        group_columns, sort=True, observed=True
    ):
        purchase = float(group["purchase_notional"].sum())
        sale = float(group["sale_notional"].sum())
        absolute = purchase + sale
        purchased_shares = float(group["purchased_shares"].sum())
        post = group.loc[group["TRANS_CODE"].eq("P"), "post_holding"].dropna()
        holding_fraction = (
            purchased_shares / float(post.max())
            if purchased_shares > 0 and not post.empty and float(post.max()) > 0
            else np.nan
        )
        source_column = (
            "_source_submission"
            if "_source_submission" in group.columns
            else "_source"
        )
        source = str(group[source_column].iloc[0]) if source_column in group else ""
        base = {
            "cik": int(cik_value),
            "accession": str(accession),
            "filing_date": group["filing_date"].iloc[0].date(),
            "period_of_report": pd.to_datetime(
                group["PERIOD_OF_REPORT"].iloc[0],
                format="%d-%b-%Y",
                errors="coerce",
            ).date(),
            "purchase_notional": purchase,
            "sale_notional": sale,
            "net_open_market_balance": (purchase - sale) / absolute,
            "unique_purchasing_owners": (
                int(owner_count.get(accession, 0)) if purchase > 0 else 0
            ),
            "officer_director_purchase_share": (
                float(bool(officer_director.get(accession, False)))
                if purchase > 0
                else 0.0
            ),
            "purchase_to_post_holding": holding_fraction,
            "transaction_filing_lag_days": int(
                (group["filing_date"] - group["transaction_date"]).dt.days.max()
            ),
            "late_reported": bool(group["TRANS_TIMELINESS"].eq("L").any()),
            "qualifying_transaction_count": len(group),
            "source": source,
        }
        for symbol in identity.loc[identity["cik"].eq(int(cik_value)), "symbol"]:
            records.append({"symbol": str(symbol), **base})
    filings = pd.DataFrame.from_records(records, columns=_empty_filings().columns)
    filings = filings.sort_values(["symbol", "filing_date", "accession"]).reset_index(
        drop=True
    )
    return filings, rejected.reset_index(drop=True)


def build_event_features(
    events: pd.DataFrame,
    filings: pd.DataFrame,
    identities: pd.DataFrame,
) -> pd.DataFrame:
    """Project filing states causally onto five subsequent training sessions."""
    event_required = {"symbol", "session_date", "bar_idx"}
    if missing := event_required.difference(events.columns):
        raise ValueError(f"SEC_FORM4_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    filing_required = {
        "symbol",
        "accession",
        "filing_date",
        "purchase_notional",
        "sale_notional",
        "net_open_market_balance",
        "unique_purchasing_owners",
        "officer_director_purchase_share",
        "purchase_to_post_holding",
    }
    if missing := filing_required.difference(filings.columns):
        raise ValueError(f"SEC_FORM4_FILING_COLUMNS_MISSING:{sorted(missing)}")
    result = events.copy()
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="coerce"
    ).dt.date
    if result["session_date"].isna().any():
        raise ValueError("SEC_FORM4_EVENT_DATE_INVALID")
    result = result.loc[
        result["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("SEC_FORM4_EVENT_KEY_DUPLICATE")
    source = filings.copy()
    source["filing_date"] = pd.to_datetime(
        source["filing_date"], errors="coerce"
    ).dt.date
    if source["filing_date"].isna().any():
        raise ValueError("SEC_FORM4_FILING_DATE_INVALID")
    if source.duplicated(["symbol", "accession"]).any():
        raise ValueError("SEC_FORM4_FILING_KEY_DUPLICATE")
    inventory = (
        source[["symbol", "accession"]]
        .drop_duplicates()
        .groupby("symbol", observed=True)
        .size()
    )
    result["sec_form4_qualifying_filing_count"] = (
        result["symbol"].map(inventory).fillna(0).astype("int64")
    )
    filing_years = sorted({value.year for value in source["filing_date"]})
    result["sec_form4_qualifying_filing_years"] = "|".join(
        str(year) for year in filing_years
    )
    sessions = sorted(result["session_date"].unique())
    session_index = {session: index for index, session in enumerate(sessions)}
    active_records: list[dict[str, object]] = []
    for filing in source.itertuples(index=False):
        available = next(
            (session for session in sessions if session > filing.filing_date), None
        )
        if available is None:
            continue
        start = session_index[available]
        for session in sessions[start : start + 5]:
            active_records.append(
                {
                    "symbol": str(filing.symbol),
                    "session_date": session,
                    "accession": str(filing.accession),
                    "filing_date": filing.filing_date,
                    "purchase_notional": float(filing.purchase_notional),
                    "sale_notional": float(filing.sale_notional),
                    "unique_purchasing_owners": float(
                        filing.unique_purchasing_owners
                    ),
                    "officer_director_purchase_share": float(
                        filing.officer_director_purchase_share
                    ),
                    "purchase_to_post_holding": float(
                        filing.purchase_to_post_holding
                    ),
                }
            )
    if active_records:
        active = pd.DataFrame.from_records(active_records)
        grouped_records: list[dict[str, object]] = []
        for (symbol, session), group in active.groupby(
            ["symbol", "session_date"], sort=True, observed=True
        ):
            purchase = float(group["purchase_notional"].sum())
            sale = float(group["sale_notional"].sum())
            absolute = purchase + sale
            officer_weight = (
                float(
                    np.average(
                        group["officer_director_purchase_share"],
                        weights=group["purchase_notional"],
                    )
                )
                if purchase > 0
                else np.nan
            )
            holding = pd.to_numeric(
                group["purchase_to_post_holding"], errors="coerce"
            )
            grouped_records.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "active_accessions": "|".join(sorted(group["accession"].unique())),
                    "latest_filing_date": max(group["filing_date"]),
                    "insider_purchase_notional": (
                        float(np.log1p(purchase)) if purchase > 0 else np.nan
                    ),
                    "insider_purchase_holding_fraction": (
                        float(holding.max())
                        if purchase > 0 and holding.notna().any()
                        else np.nan
                    ),
                    "insider_purchase_owner_cluster": (
                        float(group["unique_purchasing_owners"].sum())
                        if purchase > 0
                        else np.nan
                    ),
                    "insider_officer_director_purchase": officer_weight,
                    "insider_net_purchase_balance": (
                        (purchase - sale) / absolute
                        if purchase > 0 and absolute > 0
                        else np.nan
                    ),
                }
            )
        active_state = pd.DataFrame.from_records(grouped_records)
        active_state["sec_form4_feature_bearing"] = active_state[
            list(FEATURE_COLUMNS)
        ].notna().any(axis=1)
        for column in FEATURE_COLUMNS:
            raw = pd.to_numeric(active_state[column], errors="coerce").where(
                lambda value: value > 0
            )
            grouped = raw.groupby(active_state["session_date"], observed=True)
            lower = grouped.transform(lambda value: value.quantile(0.01))
            upper = grouped.transform(lambda value: value.quantile(0.99))
            winsorized = raw.clip(lower=lower, upper=upper)
            active_state[column] = winsorized.groupby(
                active_state["session_date"], observed=True
            ).rank(method="average", pct=True)
        result = result.merge(
            active_state,
            how="left",
            on=["symbol", "session_date"],
            validate="many_to_one",
        )
    else:
        result["active_accessions"] = pd.NA
        result["latest_filing_date"] = pd.NaT
        result["sec_form4_feature_bearing"] = False
        for column in FEATURE_COLUMNS:
            result[column] = np.nan
    known = result["symbol"].isin(set(identities["symbol"].astype(str)))
    active = result["active_accessions"].notna()
    feature = result["sec_form4_feature_bearing"].eq(True)
    result["coverage_reason"] = np.select(
        [~known, ~active, ~feature],
        [
            "SEC_FORM4_IDENTITY_UNAVAILABLE",
            "SEC_FORM4_NO_ACTIVE_FILING",
            "SEC_FORM4_FEATURE_MISSING",
        ],
        default="COVERED",
    )
    return result
