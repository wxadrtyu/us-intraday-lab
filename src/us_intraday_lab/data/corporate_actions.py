"""Read-only, paginated Alpaca corporate-action acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    SECRET_KEY_VARIABLE,
)

ENDPOINT = "https://data.alpaca.markets/v1/corporate-actions"
PageGetter = Callable[[str, Mapping[str, str]], Mapping[str, object]]


def _default_get(url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
    request = Request(url, method="GET", headers=dict(headers))
    with urlopen(request, timeout=60) as response:
        return cast(dict[str, object], json.load(response))


def fetch_corporate_actions(
    *,
    start: date,
    end: date,
    environ: Mapping[str, str] | None = None,
    page_getter: PageGetter = _default_get,
) -> tuple[list[dict[str, object]], int]:
    values = os.environ if environ is None else environ
    api_key = values.get(API_KEY_VARIABLE, "")
    secret_key = values.get(SECRET_KEY_VARIABLE, "")
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_CORPORATE_ACTION_CREDENTIAL_MISSING")
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    rows: list[dict[str, object]] = []
    token: str | None = None
    pages = 0
    while True:
        params = {"start": start.isoformat(), "end": end.isoformat(), "limit": "1000"}
        if token:
            params["page_token"] = token
        payload = page_getter(f"{ENDPOINT}?{urlencode(params)}", headers)
        pages += 1
        grouped = payload.get("corporate_actions", {})
        if not isinstance(grouped, Mapping):
            raise TypeError("corporate_actions must be grouped by action type")
        for action_type, actions in grouped.items():
            if not isinstance(actions, list):
                raise TypeError("corporate action group must be a list")
            for action in actions:
                if not isinstance(action, Mapping):
                    raise TypeError("corporate action must be an object")
                rows.append(
                    {
                        "action_type": str(action_type),
                        "id": action.get("id"),
                        "symbol": action.get("symbol")
                        or action.get("acquiree_symbol")
                        or action.get("old_symbol"),
                        "process_date": action.get("process_date"),
                        "ex_date": action.get("ex_date"),
                        "effective_date": action.get("effective_date"),
                        "payload_json": json.dumps(action, sort_keys=True, separators=(",", ":")),
                    }
                )
        next_token = payload.get("next_page_token")
        if not next_token:
            break
        token = str(next_token)
    return rows, pages


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_corporate_actions(
    rows: list[dict[str, object]],
    *,
    root: Path,
    start: date,
    end: date,
    pages: int,
    retrieved_at: datetime | None = None,
) -> dict[str, object]:
    observed = datetime.now(UTC) if retrieved_at is None else retrieved_at.astimezone(UTC)
    frame = pd.DataFrame(rows)
    if not frame.empty and frame["id"].duplicated().any():
        frame = frame.drop_duplicates("id", keep="last")
    if not frame.empty:
        frame = frame.sort_values(["process_date", "action_type", "id"], kind="stable")
    output_root = root.resolve() / "data" / "catalog" / "corporate_actions"
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".actions-", dir=output_root))
    data_path = temporary / "actions.parquet"
    frame.to_parquet(data_path, index=False, compression="zstd")
    content_hash = _sha256_file(data_path)
    dataset_id = f"alpaca-corporate-actions-{content_hash[:24]}"
    manifest = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "provider": "alpaca",
        "endpoint": ENDPOINT,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "retrieved_at": observed.isoformat(),
        "pages": pages,
        "row_count": len(frame),
        "content_sha256": content_hash,
        "read_only": True,
    }
    (temporary / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    final = output_root / dataset_id
    if final.exists():
        for child in temporary.iterdir():
            child.unlink()
        temporary.rmdir()
    else:
        temporary.rename(final)
    return manifest
