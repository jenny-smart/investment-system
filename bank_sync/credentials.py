from __future__ import annotations

import subprocess


SERVICE_PREFIX = "investment-system.bank"


def _service(account_key: str, field: str) -> str:
    return f"{SERVICE_PREFIX}.{account_key}.{field}"


def save_secret(account_key: str, field: str, value: str) -> None:
    if not value:
        raise ValueError("帳密不可為空")
    subprocess.run(
        ["security", "add-generic-password", "-U", "-a", account_key, "-s", _service(account_key, field), "-w", value],
        check=True, capture_output=True, text=True,
    )


def load_secret(account_key: str, field: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", account_key, "-s", _service(account_key, field), "-w"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.rstrip("\n")


def has_secret(account_key: str, field: str) -> bool:
    try:
        load_secret(account_key, field)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
