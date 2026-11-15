"""本機「銀行帳戶與信用卡」頁的進入密碼：只存雜湊（PBKDF2＋鹽），放在帳密檔的 "app" 區塊。"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import os

from .credentials import _read, DEFAULT_CREDENTIALS_FILE, save_section

ROUNDS = 200_000
LOCK_MINUTES = 15  # 閒置超過就要重新輸入


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ROUNDS).hex()


def has_password(path=DEFAULT_CREDENTIALS_FILE) -> bool:
    try:
        return bool((_read(path).get("app") or {}).get("page_password_hash"))
    except Exception:
        return False


def set_password(password: str, path=DEFAULT_CREDENTIALS_FILE) -> None:
    if len(password) < 4:
        raise ValueError("密碼至少 4 個字")
    salt = os.urandom(16)
    section = dict(_read(path).get("app") or {})
    section.update({"page_password_salt": salt.hex(), "page_password_hash": _hash(password, salt)})
    save_section("app", section, path)


def check_password(password: str, path=DEFAULT_CREDENTIALS_FILE) -> bool:
    section = _read(path).get("app") or {}
    try:
        salt = bytes.fromhex(section["page_password_salt"])
        return hmac.compare_digest(_hash(password, salt), section["page_password_hash"])
    except Exception:
        return False


def set_password_cli() -> None:
    first = getpass.getpass("設定銀行頁進入密碼：")
    if first != getpass.getpass("再輸入一次："):
        raise SystemExit("兩次不一樣，沒有設定。")
    set_password(first)
    print("✓ 已設定（只存雜湊在 ~/Bank account/personal_bank_accounts.json）")
