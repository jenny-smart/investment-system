"""排程時段與資料新舊判斷、GitHub Actions 查詢與觸發（不依賴 Streamlit）。

判斷方式：找出「現在往前 5 分鐘」之前最後一個排程時間點（slot），最後一次有更新的執行
必須不早於它的前一個排程時間點（同樣在時段內），也就是容許漏跑一次；連漏兩次才算太舊。
往前 5 分鐘是留給剛觸發、還在執行中的那一次。

只有真的寫入的執行才算更新：workflow 的 run-name 標成 dry-run 的不算；auto 模式在
時段外會直接略過，所以 auto（或舊的、沒有 run-name 的執行）只有在時段內開始才算。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
import os
from typing import Callable

import requests

TAIPEI = timezone(timedelta(hours=8))
GITHUB_REPO = "jenny-smart/investment-system"
RUN_GRACE = timedelta(minutes=5)
RUNNER_DELAY = timedelta(minutes=9)
RUNS_TO_SCAN = 30
AUTO_DISPATCH_COOLDOWN = timedelta(minutes=15)


def tw_window(t: datetime) -> bool:
    return t.weekday() < 5 and time(8, 30) <= t.time() <= time(14, 30)


def us_window(t: datetime) -> bool:
    weekday = t.weekday()
    return (weekday < 5 and t.time() >= time(21, 0)) or (1 <= weekday <= 5 and t.time() <= time(6, 0))


def always(_t: datetime) -> bool:
    return True


@dataclass(frozen=True)
class Job:
    key: str
    label: str
    workflow: str
    step_minutes: int
    in_window: Callable[[datetime], bool]
    # app 觸發時用 update，避免 auto 模式在時段外直接略過卻被當成已更新
    inputs: dict = field(default_factory=dict)


JOBS = (
    Job("tw", "台股價格", "tw-stock-prices.yml", 10, tw_window, {"mode": "update"}),
    Job("us", "美股價格", "us-stock-prices.yml", 30, us_window, {"mode": "update"}),
    Job("fund", "基金淨值／匯率", "fund-nav.yml", 30, always),
)


def last_slot(now: datetime, job: Job) -> datetime | None:
    """now 之前（含）最後一個排程時間點；一週內都沒有則回 None。"""
    step = job.step_minutes
    t = now.replace(minute=now.minute - now.minute % step, second=0, microsecond=0)
    for _ in range(7 * 24 * 60 // step):
        if job.in_window(t):
            return t
        t -= timedelta(minutes=step)
    return None


def is_stale(job: Job, last_ok: datetime | None, now: datetime) -> bool:
    slot = last_slot(now - RUN_GRACE, job)
    if slot is None:
        return False
    if last_ok is None:
        return True
    previous = last_slot(slot - timedelta(minutes=job.step_minutes), job)
    return last_ok < (previous or slot)


def run_updated(job: Job, title: str, started: datetime) -> bool:
    """這次成功執行是否真的寫入（依 run-name：dry-run / update / auto）。"""
    if title == "dry-run":
        return False
    if title == "update":
        return True
    return job.in_window(started) or job.in_window(started - RUNNER_DELAY)


def github_token() -> str:
    try:
        import streamlit as st
        token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        token = ""
    return token or os.environ.get("GITHUB_TOKEN", "")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_last_success(workflow: str, token: str) -> datetime | None:
    """main 分支上該 workflow 最後一次真的有更新的成功執行開始時間（台北時間）。"""
    job = next(job for job in JOBS if job.workflow == workflow)
    response = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/runs",
        params={"status": "success", "branch": "main", "per_page": RUNS_TO_SCAN},
        headers=_headers(token), timeout=10,
    )
    response.raise_for_status()
    for run in response.json().get("workflow_runs", []):
        stamp = run.get("run_started_at") or run["created_at"]
        started = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(TAIPEI)
        if run_updated(job, run.get("display_title", ""), started):
            return started
    return None


def dispatch(job: Job, token: str) -> None:
    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{job.workflow}/dispatches",
        json={"ref": "main", "inputs": job.inputs}, headers=_headers(token), timeout=10,
    )
    response.raise_for_status()
