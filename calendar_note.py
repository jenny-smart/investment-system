"""在 Google 日曆加一則全天提醒（服務帳號寫入 jennytsai26888@gmail.com 的日曆，需已共用「變更活動」）。

同一個 key 只會加一次（用活動的 private extended property 查重）。失敗只回傳原因，不丟例外。
"""
from __future__ import annotations

from datetime import date, timedelta
import json
import os

CALENDAR_ID = os.environ.get("DIVIDEND_CALENDAR_ID", "jennytsai26888@gmail.com")
API = "https://www.googleapis.com/calendar/v3/calendars/{cal}/events"


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials
    info = json.loads(os.environ["INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/calendar.events"])
    return AuthorizedSession(creds)


def add_once(key: str, day: date, summary: str, description: str) -> str:
    """回傳 "added"、"exists" 或錯誤訊息。"""
    try:
        session = _session()
        url = API.format(cal=CALENDAR_ID)
        found = session.get(url, params={"privateExtendedProperty": f"jenny_key={key}", "maxResults": 1}, timeout=20)
        found.raise_for_status()
        if found.json().get("items"):
            return "exists"
        body = {"summary": summary, "description": description,
                "start": {"date": day.isoformat()}, "end": {"date": (day + timedelta(days=1)).isoformat()},
                "extendedProperties": {"private": {"jenny_key": key}}}
        resp = session.post(url, json=body, timeout=20)
        resp.raise_for_status()
        return "added"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc)[:200]}"
