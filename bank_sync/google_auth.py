"""本機寫入總帳／行事曆用的 Google 授權。

不需要 investment-system 的服務帳號金鑰：用 Jenny 本人帳號（jennytsai26888@gmail.com）授權一次，
refresh token 存在帳密檔的 "google" 區塊：
  "google": {"client_id": "...", "client_secret": "...", "refresh_token": "..."}

OAuth 用戶端沿用 tool-system 的「電腦版應用程式」用戶端：
  - 自動從 ~/lemon/.streamlit/secrets.toml 讀 GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET；
  - 或給 client_secret JSON 路徑（Google Cloud Console 下載的 tool-system-oauth.json）。
仍可改用服務帳號：  "google": {"service_account_file": "金鑰 JSON 路徑"}
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from .credentials import DEFAULT_CREDENTIALS_FILE, _read, save_section

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/calendar.events"]
CALENDAR_ID = "jennytsai26888@gmail.com"
LEMON_SECRETS = Path.home() / "lemon/.streamlit/secrets.toml"


def _secrets_toml(path: Path = LEMON_SECRETS) -> dict:
    if not path.exists():
        return {}
    found = {}
    for key in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
        m = re.search(rf'^\s*{key}\s*=\s*"([^"]+)"', path.read_text("utf-8"), re.M)
        if m:
            found[key] = m.group(1)
    return found


def client_config(client_json: Path | None = None) -> dict:
    if client_json:
        data = json.loads(Path(client_json).expanduser().read_text("utf-8"))
        info = data.get("installed") or data.get("web") or {}
        return {"installed": {"client_id": info["client_id"], "client_secret": info["client_secret"],
                              "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                              "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}
    toml = _secrets_toml()
    if "GOOGLE_OAUTH_CLIENT_ID" in toml and "GOOGLE_OAUTH_CLIENT_SECRET" in toml:
        return {"installed": {"client_id": toml["GOOGLE_OAUTH_CLIENT_ID"],
                              "client_secret": toml["GOOGLE_OAUTH_CLIENT_SECRET"],
                              "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                              "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}
    raise SystemExit("找不到 OAuth 用戶端：請給 client_secret JSON 路徑，"
                     f"或確認 {LEMON_SECRETS} 有 GOOGLE_OAUTH_CLIENT_ID／GOOGLE_OAUTH_CLIENT_SECRET。")


def login(client_json: Path | None = None, path: Path = DEFAULT_CREDENTIALS_FILE) -> None:
    """開瀏覽器授權一次，把 refresh token 存進帳密檔。"""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit("請先安裝：pip3 install google-auth-oauthlib") from exc
    config = client_config(client_json)
    flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
    print("即將開啟瀏覽器：請用 jennytsai26888@gmail.com（總帳擁有者）登入並同意「試算表」「日曆活動」……")
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        raise SystemExit("沒有拿到 refresh token；到 https://myaccount.google.com/permissions 移除這個應用程式後再試一次。")
    save_section("google", {"client_id": config["installed"]["client_id"],
                            "client_secret": config["installed"]["client_secret"],
                            "refresh_token": creds.refresh_token}, path)
    print(f"授權完成，已存進 {path}（不用再做第二次）。")


def credentials(path: Path = DEFAULT_CREDENTIALS_FILE):
    section = _read(path).get("google") or {}
    if section.get("refresh_token"):
        from google.oauth2.credentials import Credentials
        return Credentials(token=None, refresh_token=section["refresh_token"],
                           token_uri="https://oauth2.googleapis.com/token",
                           client_id=section["client_id"], client_secret=section["client_secret"], scopes=SCOPES)
    if section.get("service_account_file"):
        from google.oauth2.service_account import Credentials
        return Credentials.from_service_account_file(str(Path(section["service_account_file"]).expanduser()),
                                                     scopes=SCOPES)
    raise SystemExit("還沒有 Google 授權：請先執行 python3 -m bank_sync google-login")


def calendar_add_once(creds, key: str, day: date, summary: str, description: str) -> str:
    """同 calendar_note.add_once：同一個 key 只加一次。回傳 added／exists／錯誤訊息。"""
    try:
        from google.auth.transport.requests import AuthorizedSession
        session = AuthorizedSession(creds)
        url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
        found = session.get(url, params={"privateExtendedProperty": f"jenny_key={key}", "maxResults": 1}, timeout=20)
        found.raise_for_status()
        if found.json().get("items"):
            return "exists"
        body = {"summary": summary, "description": description,
                "start": {"date": day.isoformat()}, "end": {"date": (day + timedelta(days=1)).isoformat()},
                "extendedProperties": {"private": {"jenny_key": key}}}
        session.post(url, json=body, timeout=20).raise_for_status()
        return "added"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc)[:200]}"
