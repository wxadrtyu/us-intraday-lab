from __future__ import annotations

from datetime import date

from us_intraday_lab.data.corporate_actions import fetch_corporate_actions


def test_corporate_actions_follow_pagination_and_retain_raw_payload() -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict[str, str]) -> dict[str, object]:
        calls.append(url)
        assert headers["APCA-API-KEY-ID"] == "key"
        if len(calls) == 1:
            return {
                "corporate_actions": {
                    "forward_splits": [{"id": "1", "symbol": "ABC", "process_date": "2022-01-02"}]
                },
                "next_page_token": "next token",
            }
        return {
            "corporate_actions": {
                "name_changes": [{"id": "2", "old_symbol": "OLD", "process_date": "2022-01-03"}]
            },
            "next_page_token": None,
        }

    rows, pages = fetch_corporate_actions(
        start=date(2022, 1, 1),
        end=date(2022, 1, 31),
        environ={"ALPACA_PAPER_API_KEY": "key", "ALPACA_PAPER_SECRET_KEY": "secret"},
        page_getter=fake_get,
    )

    assert pages == 2
    assert [row["symbol"] for row in rows] == ["ABC", "OLD"]
    assert "page_token=next+token" in calls[1]
    assert '"symbol":"ABC"' in str(rows[0]["payload_json"])
