# Point-in-Time News Event Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and audit a training-only, point-in-time Alpaca News metadata probe that can later populate deterministic news features for all 799,799 frozen intraday event keys.

**Architecture:** A read-only HTTP client downloads immutable UTC-day pages using `updated_at` as the only causal availability time. A separate pure feature builder joins deduplicated metadata to frozen event cutoffs and emits explicit zero-news rows; scripts orchestrate acquisition and audit without importing any broker module.

**Tech Stack:** Python 3.12, urllib, Pydantic-compatible dataclasses, pandas, PyArrow/Parquet, pytest, Ruff.

## Global Constraints

- `available_at = updated_at`; final headline/summary data is never backdated to `created_at`.
- Never request, inspect, persist, or log `content`, images, URL, author, credentials, response headers, or full page tokens.
- Probe and feature selection use 2021-2023 only; 2024-2025 is development-only after freeze, 2026Q1 is consumed-only after candidate freeze, and 2026-04 onward is forbidden.
- Full output must preserve exactly 799,799 frozen event keys with explicit zero-news rows.
- Long-only, gross no greater than 1, no overnight; no broker imports, order submission, cancellation, Paper-pool mutation, or v11098 changes.
- Raw partitions, manifests with secrets, caches, credentials, logs, and runtime state remain untracked.

---

### Task 1: Read-only paginated News client

**Files:**
- Create: `src/us_intraday_lab/data/news_event_acquisition.py`
- Test: `tests/unit/data/test_news_event_acquisition.py`

**Interfaces:**
- Produces: `NewsPage`, `canonicalize_article(raw: Mapping[str, object]) -> dict[str, object]`, and `fetch_updated_day(transport: NewsTransport, day: date, *, limit: int = 50) -> tuple[pd.DataFrame, tuple[dict[str, object], ...]]`.
- The injectable `NewsTransport` accepts a query mapping and returns decoded JSON; the default transport adds credentials only in memory and uses the fixed Alpaca News URL.

- [ ] **Step 1: Write failing causal and pagination tests**

```python
def test_fetch_updated_day_pages_deduplicates_and_never_retains_content():
    transport = FakeTransport([
        {"news": [{"id": 7, "created_at": "2022-03-14T20:00:00Z",
                   "updated_at": "2022-03-15T10:00:00Z", "source": "wire",
                   "symbols": ["AAPL"], "headline": "Raises guidance",
                   "summary": "Outlook improves", "content": "forbidden"}],
         "next_page_token": "opaque-secret-token"},
        {"news": [{"id": 7, "created_at": "2022-03-14T20:00:00Z",
                   "updated_at": "2022-03-15T10:00:00Z", "source": "wire",
                   "symbols": ["AAPL"], "headline": "Raises guidance",
                   "summary": "Outlook improves"}], "next_page_token": None},
    ])
    frame, pages = fetch_updated_day(transport, date(2022, 3, 15))
    assert frame["news_id"].tolist() == ["7"]
    assert frame["available_at"].tolist() == [pd.Timestamp("2022-03-15T10:00:00Z")]
    assert "content" not in frame.columns
    assert pages[0]["token_sha256"] != "opaque-secret-token"
    assert transport.calls[1]["page_token"] == "opaque-secret-token"

def test_fetch_updated_day_rejects_missing_updated_at():
    transport = FakeTransport([{"news": [{"id": 1, "created_at": "2022-01-01T00:00:00Z"}]}])
    with pytest.raises(ValueError, match="NEWS_UPDATED_AT_INVALID"):
        fetch_updated_day(transport, date(2022, 1, 1))
```

- [ ] **Step 2: Run tests and confirm the module is absent**

Run: `python -m pytest tests/unit/data/test_news_event_acquisition.py -q`

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the minimal client and canonicalizer**

```python
NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
ALLOWED_FIELDS = ("id", "created_at", "updated_at", "source", "symbols", "headline", "summary")

def canonicalize_article(raw: Mapping[str, object]) -> dict[str, object]:
    updated = pd.to_datetime(raw.get("updated_at"), utc=True, errors="coerce")
    if pd.isna(updated):
        raise ValueError("NEWS_UPDATED_AT_INVALID")
    return {
        "news_id": str(raw["id"]),
        "created_at": pd.to_datetime(raw.get("created_at"), utc=True, errors="coerce"),
        "available_at": updated,
        "source": str(raw.get("source", "")),
        "symbols": tuple(sorted({str(x).upper() for x in raw.get("symbols", [])})),
        "headline": str(raw.get("headline", "")),
        "summary": str(raw.get("summary", "")),
    }
```

`fetch_updated_day` must request `[day 00:00Z, next day 00:00Z)`, `sort=asc`, follow tokens, hash tokens before manifest output, hash canonical page content, verify every `available_at` is inside the interval, and reject the same ID with different canonical metadata.

- [ ] **Step 4: Run focused tests and static checks**

Run: `python -m pytest tests/unit/data/test_news_event_acquisition.py -q && python -m ruff check src/us_intraday_lab/data/news_event_acquisition.py tests/unit/data/test_news_event_acquisition.py`

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the client**

```powershell
git add src/us_intraday_lab/data/news_event_acquisition.py tests/unit/data/test_news_event_acquisition.py
git commit -m "Add causal Alpaca News metadata client"
```

---

### Task 2: Immutable training-day acquisition and resume

**Files:**
- Modify: `src/us_intraday_lab/data/news_event_acquisition.py`
- Create: `scripts/acquire_us_market_news_events.py`
- Test: `tests/unit/data/test_news_event_acquisition.py`

**Interfaces:**
- Produces: `acquire_updated_days(root: Path, start: date, end: date, transport: NewsTransport) -> list[dict[str, object]]`.
- Creates one Parquet file and one JSON manifest per UTC day under `data/staging/alpaca_news_metadata_v1/YYYY-MM/`.

- [ ] **Step 1: Write failing immutability, resume, and date-boundary tests**

```python
def test_acquire_days_resumes_complete_day_and_rejects_partial_or_post_training(tmp_path):
    manifest = acquire_updated_days(tmp_path, date(2022, 3, 15), date(2022, 3, 15), fake)[0]
    assert manifest["available_time_field"] == "updated_at"
    assert manifest["complete"] is True
    calls = len(fake.calls)
    assert acquire_updated_days(tmp_path, date(2022, 3, 15), date(2022, 3, 15), fake)[0] == manifest
    assert len(fake.calls) == calls
    (tmp_path / "data/staging/alpaca_news_metadata_v1/2022-03/2022-03-16.parquet").touch()
    with pytest.raises(ValueError, match="PARTIAL_NEWS_DAY"):
        acquire_updated_days(tmp_path, date(2022, 3, 16), date(2022, 3, 16), fake)
    with pytest.raises(ValueError, match="TRAINING_ONLY"):
        acquire_updated_days(tmp_path, date(2024, 1, 1), date(2024, 1, 1), fake)
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run: `python -m pytest tests/unit/data/test_news_event_acquisition.py::test_acquire_days_resumes_complete_day_and_rejects_partial_or_post_training -q`

Expected: fail because `acquire_updated_days` does not exist.

- [ ] **Step 3: Implement atomic partitions and CLI**

Write temporary Parquet/manifest files in the target directory, `replace` them only after validation, and record schema version, UTC interval, provider, page count, row count, unique IDs, symbol links, rejected rows, page hashes, content SHA-256, and `complete=true`. The CLI accepts only `--start`, `--end`, and `--root`, rejects dates outside 2021-2023, and never prints environment values.

- [ ] **Step 4: Verify focused behavior**

Run: `python -m pytest tests/unit/data/test_news_event_acquisition.py -q && python -m ruff check src/us_intraday_lab/data/news_event_acquisition.py scripts/acquire_us_market_news_events.py tests/unit/data/test_news_event_acquisition.py`

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit acquisition support**

```powershell
git add src/us_intraday_lab/data/news_event_acquisition.py scripts/acquire_us_market_news_events.py tests/unit/data/test_news_event_acquisition.py
git commit -m "Persist immutable training news partitions"
```

---

### Task 3: Pure point-in-time feature builder

**Files:**
- Create: `src/us_intraday_lab/data/news_event_features.py`
- Test: `tests/unit/data/test_news_event_features.py`

**Interfaces:**
- Produces: `build_news_features(events: pd.DataFrame, articles: pd.DataFrame, lexicon: NewsLexicon) -> pd.DataFrame`.
- Required event columns are `event_key`, `symbol`, and `decision_timestamp`; output preserves event order and adds fixed 30-minute, 2-hour, 1-day, and 5-day features.

- [ ] **Step 1: Write failing cutoff and zero-row tests**

```python
def test_features_use_strict_updated_at_cutoff_and_preserve_zero_rows():
    events = pd.DataFrame({"event_key": ["a", "b"], "symbol": ["AAPL", "MSFT"],
                           "decision_timestamp": pd.to_datetime(["2022-03-15T10:00:00Z"] * 2)})
    articles = pd.DataFrame({"news_id": ["early", "equal"], "available_at": pd.to_datetime([
        "2022-03-15T09:59:59Z", "2022-03-15T10:00:00Z"]), "source": ["wire", "wire"],
        "symbols": [("AAPL",), ("AAPL",)], "headline": ["raises guidance", "record profit"],
        "summary": ["", ""]})
    result = build_news_features(events, articles, FROZEN_NEWS_LEXICON)
    assert result["event_key"].tolist() == ["a", "b"]
    assert result.loc[0, "article_count_30m"] == 1
    assert result.loc[1, "article_count_30m"] == 0
    assert bool(result.loc[1, "news_available_30m"]) is False
```

- [ ] **Step 2: Run tests and confirm the module is absent**

Run: `python -m pytest tests/unit/data/test_news_event_features.py -q`

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement deterministic normalization and features**

Use lowercase Unicode normalization, ASCII token boundaries, a frozen in-code lexicon, simple preceding-token negation, and stable SHA-256 story hashes. Explode symbols before the as-of join; filter with `available_at < decision_timestamp`; aggregate counts, decay, source diversity/concentration, recency, breadth, lexical counts, disagreement, and repeated-story intensity. Reindex to the original event keys and fill only count/indicator features with zero; unavailable recency remains null.

- [ ] **Step 4: Add duplicate-key and forbidden-date failures**

Add tests proving duplicate event keys fail, articles with invalid timestamps fail, event dates outside 2021-2023 fail in training mode, output is deterministic under input row permutation, and no raw text column appears in output.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest tests/unit/data/test_news_event_features.py -q && python -m ruff check src/us_intraday_lab/data/news_event_features.py tests/unit/data/test_news_event_features.py`

Expected: all tests pass and Ruff reports no errors.

```powershell
git add src/us_intraday_lab/data/news_event_features.py tests/unit/data/test_news_event_features.py
git commit -m "Build causal news event features"
```

---

### Task 4: Freeze protocol and execute a bounded training probe

**Files:**
- Create: `research/protocols/alpaca_news_event_metadata_v1.json`
- Create: `scripts/audit_us_market_news_event_probe.py`
- Test: `tests/unit/test_audit_us_market_news_event_probe.py`
- Create after execution: `research/results/2026-09-08-alpaca-news-event-probe.json`
- Create after execution: `research/results/2026-09-08-alpaca-news-event-probe.md`

**Interfaces:**
- The audit script reads immutable training partitions and a frozen training slice of event keys, then writes publishable aggregate evidence only.
- Produces no strategy metrics and cannot open development or consumed data.

- [ ] **Step 1: Write the failing audit-contract test**

```python
def test_probe_audit_requires_complete_pages_and_reports_cost_without_strategy_metrics(tmp_path):
    result = audit_probe(root=tmp_path, start=date(2022, 3, 15), end=date(2022, 3, 15))
    assert result["available_time_field"] == "updated_at"
    assert result["training_only"] is True
    assert result["partial_days"] == 0
    assert result["estimated_full_calls"] > 0
    assert "annualized_return" not in result
    assert "information_ratio" not in result
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/unit/test_audit_us_market_news_event_probe.py -q`

Expected: collection fails because the audit script does not exist.

- [ ] **Step 3: Freeze protocol before network acquisition**

The JSON protocol records the design commit, source URL, `updated_at` availability rule, training boundary, fixed daily pagination, retained/excluded fields, fixed lookbacks, lexicon SHA-256, event-universe SHA-256, no-broker rule, probe dates, failure conditions, and the rule that probe output cannot rank strategy parameters. Commit this protocol and tests before running the downloader.

```powershell
git add research/protocols/alpaca_news_event_metadata_v1.json scripts/audit_us_market_news_event_probe.py tests/unit/test_audit_us_market_news_event_probe.py
git commit -m "Preregister Alpaca News metadata probe"
```

- [ ] **Step 4: Run the fixed one-day training probe and audit**

Run: `python scripts/acquire_us_market_news_events.py --root E:/us-intraday-lab-data/us-market --start 2022-03-15 --end 2022-03-15`

Run: `python scripts/audit_us_market_news_event_probe.py --root E:/us-intraday-lab-data/us-market --start 2022-03-15 --end 2022-03-15 --json research/results/2026-09-08-alpaca-news-event-probe.json --markdown research/results/2026-09-08-alpaca-news-event-probe.md`

Expected: complete pagination, zero partial days, unique canonical IDs, no forbidden fields, only training dates, and an explicit estimated call count for 2021-2023. Any failure stops before bulk acquisition.

- [ ] **Step 5: Verify, commit, and push aggregate evidence**

Run: `python -m pytest tests/unit/data/test_news_event_acquisition.py tests/unit/data/test_news_event_features.py tests/unit/test_audit_us_market_news_event_probe.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/news_event_acquisition.py src/us_intraday_lab/data/news_event_features.py scripts/acquire_us_market_news_events.py scripts/audit_us_market_news_event_probe.py tests/unit/data/test_news_event_acquisition.py tests/unit/data/test_news_event_features.py tests/unit/test_audit_us_market_news_event_probe.py`

Run: `git grep -n -E 'content|author|images|url' -- research/results/2026-09-08-alpaca-news-event-probe.*`

Expected: tests pass, Ruff passes, and the final grep returns no raw forbidden fields. Commit only code, protocol, tests, and aggregate reports; do not add staging Parquet, manifests containing request state, caches, credentials, logs, or SQLite files.

```powershell
git add research/results/2026-09-08-alpaca-news-event-probe.json research/results/2026-09-08-alpaca-news-event-probe.md
git commit -m "Audit Alpaca News training probe"
git push origin codex/v550-v649-second-strategy
```

## Plan Self-Review

- Spec coverage: pagination, updated-time causality, forbidden fields, immutable partitions, strict chronological isolation, explicit zero rows, audit evidence, and Paper separation each map to a task.
- Placeholder scan: no placeholder markers, deferred implementation, or unspecified error-handling steps remain.
- Interface check: acquisition outputs canonical article columns consumed unchanged by the feature builder; the audit consumes only completed acquisition manifests and aggregate counts.
