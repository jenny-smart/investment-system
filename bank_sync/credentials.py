"""個人銀行帳密：只放在本機 ~/Bank account/personal_bank_accounts.json（與 tool-system 帳密同資料夾）。

檔案格式（每個登入一組，空白欄位會略過不填）：
{
  "taishin": {"id_number": "A123456789", "user_code": "...", "password": "..."},
  "fubon":   {"id_number": "...", "user_code": "...", "password": "..."}
}
範本見 bank_sync/personal_bank_accounts.example.json。此檔不可放進 git。
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

BANK_DIR = Path(os.environ.get("BANK_SYNC_DIR", str(Path.home() / "Bank account"))).expanduser()
DEFAULT_CREDENTIALS_FILE = Path(
    os.environ.get("BANK_SYNC_ACCOUNTS_FILE", str(BANK_DIR / "personal_bank_accounts.json"))
).expanduser()
FIELDS = ("id_number", "user_code", "password")


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 格式錯誤：最外層必須是物件")
    return data


def permission_warning(path: Path = DEFAULT_CREDENTIALS_FILE) -> str:
    """帳密檔若其他使用者讀得到，回傳提醒文字。"""
    if not path.exists():
        return ""
    mode = path.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        return f"提醒：{path} 其他使用者可讀，建議執行 chmod 600 \"{path}\""
    return ""


def load_credentials(login_key: str, path: Path = DEFAULT_CREDENTIALS_FILE) -> dict[str, str]:
    """回傳該登入有填的欄位（id_number / user_code / password）。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到帳密檔：{path}（可用 python -m bank_sync setup <銀行> 建立）")
    row = _read(path).get(login_key)
    if not isinstance(row, dict):
        raise KeyError(f"帳密檔沒有「{login_key}」這組登入")
    values = {field: str(row.get(field, "")).strip() for field in FIELDS}
    values["password"] = str(row.get("password", ""))  # 密碼不去空白
    values = {k: v for k, v in values.items() if v}
    if "password" not in values:
        raise ValueError(f"{login_key} 缺少 password")
    return values


def load_section(key: str, required: tuple[str, ...], path: Path = DEFAULT_CREDENTIALS_FILE) -> dict[str, str]:
    """讀帳密檔裡的任一組設定（例如 "mail" 或某家的 pdf_password）。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到帳密檔：{path}")
    row = _read(path).get(key)
    if not isinstance(row, dict):
        raise KeyError(f"帳密檔沒有「{key}」")
    values = {k: str(v) for k, v in row.items() if str(v).strip()}
    missing = [k for k in required if k not in values]
    if missing:
        raise ValueError(f"{key} 缺少 {'、'.join(missing)}")
    return values


def has_credentials(login_key: str, path: Path = DEFAULT_CREDENTIALS_FILE) -> bool:
    try:
        load_credentials(login_key, path)
        return True
    except (FileNotFoundError, KeyError, ValueError):
        return False


def configured_logins(path: Path = DEFAULT_CREDENTIALS_FILE) -> list[str]:
    return [key for key in _read(path) if not key.startswith("_") and has_credentials(key, path)]


def save_credentials(login_key: str, values: dict[str, str], path: Path = DEFAULT_CREDENTIALS_FILE) -> None:
    """寫入（或覆蓋）一組登入，檔案權限固定為 600。"""
    data = _read(path)
    row = data.get(login_key) if isinstance(data.get(login_key), dict) else {}
    row.update({field: values.get(field, "") for field in FIELDS})  # 保留 pdf_password 等其他欄位
    data[login_key] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def save_section(key: str, values: dict, path: Path = DEFAULT_CREDENTIALS_FILE) -> None:
    """寫入（覆蓋）帳密檔裡的一個區塊（例如 "google"），權限固定 600。"""
    data = _read(path)
    data[key] = values
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
