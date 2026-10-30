"""App 畫面的資料更新狀態：顯示各排程最後成功時間、太舊時自動觸發一次、提供立即更新按鈕。"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from invest_app.sync_schedule import (
    AUTO_DISPATCH_COOLDOWN,
    JOBS,
    TAIPEI,
    Job,
    dispatch,
    fetch_last_success,
    github_token,
    is_stale,
)



@st.cache_data(ttl=60, show_spinner=False)
def _cached_last_success(workflow: str) -> tuple[datetime | None, str]:
    token = github_token()
    if not token:
        return None, "未設定 GITHUB_TOKEN"
    try:
        return fetch_last_success(workflow, token), ""
    except Exception as exc:
        return None, f"GitHub 讀取失敗：{str(exc)[:60]}"


@st.cache_resource(show_spinner=False)
def _dispatch_log() -> dict[str, datetime]:
    """各 job 最後一次由 app 觸發的時間（跨使用者共用，用來避免重複觸發）。"""
    return {}


def job_states(now: datetime | None = None) -> dict[str, dict]:
    """{key: {"job", "last_ok", "stale"(None=無法判斷), "error"}}"""
    now = now or datetime.now(TAIPEI)
    states = {}
    for job in JOBS:
        last_ok, error = _cached_last_success(job.workflow)
        stale = None if error else is_stale(job, last_ok, now)
        states[job.key] = {"job": job, "last_ok": last_ok, "stale": stale, "error": error}
    return states


def fresh_keys() -> set[str]:
    """確認總覽為最新的項目；無法判斷（例如沒設 token）不算。"""
    return {key for key, state in job_states().items() if state["stale"] is False}


def _trigger(job: Job, now: datetime) -> str:
    token = github_token()
    if not token:
        return "未設定 GITHUB_TOKEN，無法觸發"
    try:
        dispatch(job, token)
    except Exception as exc:
        return f"觸發失敗：{str(exc)[:60]}"
    _dispatch_log()[job.key] = now
    return "已要求更新，約 1–2 分鐘後完成"


def _fmt(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%H:%M") if dt.date() == now.date() else f"{dt.month}/{dt.day:02d} {dt:%H:%M}"


def render_sync_status(sheet_fetched_at: str = "") -> None:
    """總覽資料更新狀態列：最後成功時間、是否太舊、立即更新按鈕；太舊時自動觸發一次。"""
    now = datetime.now(TAIPEI)
    states = job_states(now)
    log = _dispatch_log()
    st.markdown("**🔄 資料更新狀態**")
    cols = st.columns(len(JOBS) + 1)
    for col, job in zip(cols, JOBS):
        state = states[job.key]
        with col:
            if state["error"]:
                st.caption(f"{job.label}：{_fmt(state['last_ok'], now)}　⚠ {state['error']}")
            elif state["stale"]:
                st.caption(f"{job.label}：{_fmt(state['last_ok'], now)}　⚠ 總覽未更新，使用即時價")
            else:
                st.caption(f"{job.label}：{_fmt(state['last_ok'], now)}　✓")
            triggered = log.get(job.key)
            cooling = triggered is not None and now - triggered < AUTO_DISPATCH_COOLDOWN
            if state["stale"] and not cooling and github_token():
                st.caption("自動補跑：" + _trigger(job, now))
            elif cooling:
                st.caption(f"{triggered:%H:%M} 已要求更新")
            if st.button("立即更新", key=f"sync_now_{job.key}", disabled=cooling):
                st.caption(_trigger(job, now))
                _cached_last_success.clear()
    with cols[-1]:
        st.caption(f"App 讀取總覽：{sheet_fetched_at or '—'}")
