"""把本機「銀行帳戶」頁裝成 macOS 背景服務（LaunchAgent）：登入 Mac 後自動執行，只開在 http://localhost:8502。

python3 -m bank_sync app-install     安裝並啟動（只要做一次）
python3 -m bank_sync app-status      看服務狀態
python3 -m bank_sync app-uninstall   移除
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .credentials import BANK_DIR

LABEL = "com.jenny.bankapp"
PORT = 8502
URL = f"http://localhost:{PORT}"
REPO = Path(__file__).resolve().parent.parent
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = BANK_DIR / "_app_logs" / "service.log"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    if sys.platform != "darwin":
        raise SystemExit("背景服務只支援 macOS。")
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install() -> None:
    if sys.platform != "darwin":
        raise SystemExit("背景服務只支援 macOS。")
    try:
        import streamlit  # noqa: F401
    except ImportError:
        raise SystemExit("這個 python3 沒有 streamlit，請先執行：pip3 install streamlit")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "streamlit", "run", str(REPO / "bank_app.py"),
                             "--server.port", str(PORT), "--server.address", "127.0.0.1",
                             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        "WorkingDirectory": str(REPO),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                                 "BANK_APP_SERVICE": "1", "PYTHONIOENCODING": "utf-8"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    PLIST.write_bytes(plistlib.dumps(config))
    result = _launchctl("bootstrap", _domain(), str(PLIST))
    if result.returncode != 0:
        raise SystemExit(f"啟動失敗：{result.stderr.strip() or result.stdout.strip()}")
    print(f"✓ 已安裝並啟動。之後在 Mac 上打開 {URL} 就是銀行帳戶頁（雲端 App 的「銀行帳戶」頁也有按鈕連過來）。")
    print(f"  記錄檔：{LOG}")


def uninstall() -> None:
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    if PLIST.exists():
        PLIST.unlink()
    print("✓ 已移除背景服務。")


def status() -> None:
    result = _launchctl("print", f"{_domain()}/{LABEL}")
    if result.returncode != 0:
        print("✗ 沒有安裝。執行 python3 -m bank_sync app-install 安裝。")
        return
    state = next((l.strip() for l in result.stdout.splitlines() if l.strip().startswith("state =")), "")
    print(f"✓ 已安裝（{state}），網址 {URL}")


def restart_self() -> None:
    """在服務裡按「更新程式」：git pull 後結束自己，launchd 會用新程式重新啟動。"""
    subprocess.run(["git", "pull", "-q"], cwd=str(REPO))
    os._exit(0)
