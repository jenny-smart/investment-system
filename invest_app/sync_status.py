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


def _refresh_non_investment() -> None:
    from invest_app.core import load_sheet_grid
    load_sheet_grid.clear()


def _refresh_fund_dividends() -> None:
    from invest_app.core import _fetch_gas_div_for_enrich, _get_gas_data, load_sheet_raw_grid
    _get_gas_data.clear()
    _fetch_gas_div_for_enrich.clear()
    load_sheet_raw_grid.clear()


def _refresh_stock_dividends() -> None:
    from invest_app.stock_dividends import (
        fetch_tpex_stock_dividend_announcements,
        fetch_twse_stock_dividend_announcements,
        load_stock_dividend_log,
    )
    fetch_twse_stock_dividend_announcements.clear()
    fetch_tpex_stock_dividend_announcements.clear()
    load_stock_dividend_log.clear()


# (key, 標題, 讀取時間來源說明, 自動重讀間隔, 清快取函式)
APP_READS = (
    ("non_investment", "非投資金額", "總帳「資產總覽」", "每 2 分鐘", _refresh_non_investment),
    ("fund_dividend", "基金配息資料", "基金公司配息／除息日", "每 6 小時", _refresh_fund_dividends),
    ("stock_dividend", "台股除權息公告", "證交所／櫃買", "每天", _refresh_stock_dividends),
)


def _read_time(key: str) -> str:
    from invest_app.core import DATA_FETCHED_AT, ONLINE_SHEET_SOURCES, SHEET_FETCHED_AT
    if key == "non_investment":
        return SHEET_FETCHED_AT.get(ONLINE_SHEET_SOURCES["資產總覽"], "")
    return DATA_FETCHED_AT.get({"fund_dividend": "gas_dividend", "stock_dividend": "stock_dividend"}[key], "")


def render_app_reads(enriched=None) -> None:
    """App 自己讀的資料（不是排程寫入的）：最後讀取時間＋立即重讀按鈕；再加依總覽自動確認配息入帳。"""
    st.markdown("**📥 App 讀取資料**")
    cols = st.columns(len(APP_READS) + 1)
    for col, (key, label, source, interval, refresh) in zip(cols, APP_READS):
        with col:
            fetched = _read_time(key)
            st.caption(f"{label}：{fetched or '—（本次開啟尚未讀取）'}　｜{source}，{interval}自動重讀")
            if st.button("立即重讀", key=f"reread_{key}"):
                refresh()
                st.rerun()
    with cols[-1]:
        _render_auto_confirm(enriched)


def _render_auto_confirm(enriched) -> None:
    """配息入帳：總覽每月加總金額對得上的待確認配息自動確認，配息月份由排程隨後勾選。"""
    if enriched is None:
        return
    from invest_app.dividends import auto_confirm_from_ledger
    force = st.button("立即比對", key="auto_confirm_now")
    state = auto_confirm_from_ledger(enriched, force=force)
    parts = [f"配息入帳（比對總覽）：{state.get('time', '—')}"]
    if state.get("confirmed"):
        parts.append("✓ 自動確認 " + "、".join(state["confirmed"]))
    if state.get("waiting"):
        parts.append(f"{state['waiting']} 筆本月還沒入帳")
    if state.get("mismatch"):
        parts.append("⚠ 金額對不上：" + "、".join(state["mismatch"]) + "（到配息記錄頁核對）")
    if state.get("error"):
        parts.append(f"⚠ {state['error']}")
    st.caption("　".join(parts) + "　｜每 10 分鐘，確認後配息月份隨基金淨值排程勾選")
