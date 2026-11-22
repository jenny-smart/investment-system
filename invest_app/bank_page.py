"""App「銀行帳戶」頁：在介面上執行 bank_sync（銀行明細、信用卡帳單），即時顯示過程與結果。

只能在 Jenny 的 Mac 本機開 App 時使用（帳密在 ~/Bank account/，要開本機 Chrome）。
雲端版只顯示說明。每個動作都是在背景跑 `python -m bank_sync ...`，輸出寫進記錄檔，頁面每 2 秒更新一次；
程式需要按 Enter 時（例如請你手動點到某頁），按頁面上的「繼續（Enter）」即可。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from bank_sync.credentials import BANK_DIR, DEFAULT_CREDENTIALS_FILE

REPO = Path(__file__).resolve().parent.parent
LOG_DIR = BANK_DIR / "_app_logs"
TX_DIR = BANK_DIR / "transactions" / "taishin"
STATEMENT_DIR = BANK_DIR / "statements"
CARD_BANKS = {"fubon": "富邦", "taishin": "台新", "sc": "渣打", "dbs": "星展", "cathay": "國泰世華", "hsbc": "滙豐", "ubot": "聯邦"}
FETCH_BANKS = {"taishin": "台新", "fubon": "富邦", "next": "將來", "linebank": "LINE Bank", "yuanta": "元大", "sc": "渣打", "post": "郵局"}
LOGIN_BANKS = {"taishin": "台新", "fubon": "富邦", "sc": "渣打", "linebank": "LINE Bank", "yuanta": "元大", "next": "將來"}


def is_local() -> bool:
    return DEFAULT_CREDENTIALS_FILE.exists()


# ---------- 背景執行 ----------

def _job():
    return st.session_state.get("bank_job")


def start_job(title: str, args: list[str]) -> None:
    job = _job()
    if job and job["proc"].poll() is None:
        st.warning("上一個動作還在執行，請等它完成或按「停止」。")
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.log"
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "bank_sync", *args],
        cwd=str(REPO), stdin=subprocess.PIPE, stdout=handle, stderr=subprocess.STDOUT, text=True,
        env={**__import__("os").environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
    )
    st.session_state["bank_job"] = {"proc": proc, "log": log_path, "title": title, "args": args,
                                    "started": datetime.now().strftime("%H:%M:%S")}


def send_enter(text: str = "") -> None:
    job = _job()
    if job and job["proc"].poll() is None and job["proc"].stdin:
        try:
            job["proc"].stdin.write(text + "\n")
            job["proc"].stdin.flush()
        except Exception:
            pass


def stop_job() -> None:
    job = _job()
    if job and job["proc"].poll() is None:
        job["proc"].terminate()


@st.fragment(run_every=2)
def job_panel(prefix: str = "") -> None:
    job = _job()
    if not job:
        st.caption("還沒有執行任何動作。")
        return
    running = job["proc"].poll() is None
    code = job["proc"].returncode
    state = "⏳ 執行中" if running else ("✅ 完成" if code == 0 else f"⚠️ 結束（代碼 {code}）")
    st.markdown(f"**{job['title']}**　{state}　（{job['started']} 開始）")
    try:
        text = job["log"].read_text("utf-8")
    except Exception:
        text = ""
    st.code(text[-12000:] or "（等待輸出…）", language=None)
    if running and job["args"][:1] == ["explore"]:
        c1, c2, c3 = st.columns([1, 1, 1])
        if c1.button("📸 記錄目前頁面", key=prefix + "exp_snap", type="primary"):
            send_enter()
        if c2.button("✅ 結束探索", key=prefix + "exp_quit"):
            send_enter("q")
        if c3.button("停止", key=prefix + "exp_stop"):
            stop_job()
    elif running:
        c1, c2, c3 = st.columns([1, 1, 3])
        if c1.button("繼續（Enter）", key=prefix + "bank_enter", help="程式說「按 Enter」時按這裡"):
            send_enter()
        if c2.button("停止", key=prefix + "bank_stop"):
            stop_job()
        if "請選擇" in text[-300:] or "Enter" in text[-300:] or "q＝結束" in text[-300:]:
            c3.info("程式在等你：照上面訊息在 Chrome 操作完，再按「繼續（Enter）」。")
    elif not st.session_state.get(prefix + "bank_job_done_rerun") == str(job["log"]):
        st.session_state[prefix + "bank_job_done_rerun"] = str(job["log"])
        try:  # 明細分頁剛更新：清掉 App 讀總帳的快取
            from invest_app.ledger_pages import _load
            _load.clear()
        except Exception:
            pass
        st.rerun()  # 完成後整頁更新一次，讓下面的結果顯示最新


# ---------- 結果 ----------

def _latest(folder: Path, pattern: str):
    files = sorted(folder.glob(pattern)) if folder.exists() else []
    return files[-1] if files else None


def render_taishin_results(code: str = "taishin") -> None:
    folder = BANK_DIR / "transactions" / code
    latest = _latest(folder, "2*.json")
    if not latest:
        st.caption(f"還沒有抓過{FETCH_BANKS.get(code, code)}明細。")
        return
    data = json.loads(latest.read_text("utf-8"))
    st.caption(f"最近一次：{latest.name}")
    summary = [{"類別": "台幣" if a["type"] == "TWD" else "外幣", "帳戶": a["account"],
                "細帳": a.get("ledger_row") or "未對應", "起始日": a.get("from", ""),
                "新交易筆數": len(a.get("rows", [])), "錯誤": a.get("error", "")} for a in data.get("accounts", [])]
    if summary:
        st.dataframe(pd.DataFrame(summary), hide_index=True, use_container_width=True)
    for block in data.get("accounts", []):
        rows = block.get("rows") or []
        if not rows:
            continue
        head = block.get("head") or []
        width = max(len(r) for r in rows)
        cols = head if len(head) == width else [f"欄{i + 1}" for i in range(width)]
        with st.expander(f"{block['account']}（{len(rows)} 筆）"):
            st.dataframe(pd.DataFrame([r + [""] * (width - len(r)) for r in rows], columns=cols),
                         hide_index=True, use_container_width=True)
    state_file = folder / "_state.json"
    if state_file.exists():
        with st.expander("各帳戶已抓到的最後日期"):
            state = json.loads(state_file.read_text("utf-8"))
            st.dataframe(pd.DataFrame([{"帳戶": k, "最後一筆日期": v.get("last_date", "")} for k, v in state.items()]),
                         hide_index=True, use_container_width=True)


def render_statement_results() -> None:
    rows = []
    for code, name in CARD_BANKS.items():
        folder = STATEMENT_DIR / code
        pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
        latest = pdfs[-1] if pdfs else None
        rows.append({"銀行": name, "已下載期數": len(pdfs), "最新一期": latest.name.split("_")[0] if latest else "",
                     "下載時間": datetime.fromtimestamp(latest.stat().st_mtime).strftime("%m/%d %H:%M") if latest else ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    report = _latest(BANK_DIR, "_細帳比對_*.xlsx") or _latest(STATEMENT_DIR, "_細帳比對_*.xlsx")
    if report:
        st.download_button(f"下載比對報表 {report.name}", report.read_bytes(), file_name=report.name)


# ---------- 頁面 ----------

def unlock_gate() -> bool:
    """進這頁要先輸入密碼（只存雜湊在本機帳密檔）；閒置 15 分鐘自動鎖定。"""
    import time as _t
    from bank_sync.app_auth import LOCK_MINUTES, check_password, has_password, set_password
    now = _t.time()
    last = st.session_state.get("bank_unlocked_at")
    if last and now - last < LOCK_MINUTES * 60:
        st.session_state["bank_unlocked_at"] = now
        with st.sidebar:
            if st.button("🔒 鎖定銀行頁", key="bank_lock"):
                st.session_state.pop("bank_unlocked_at", None)
                st.rerun()
        return True
    st.session_state.pop("bank_unlocked_at", None)
    if not has_password():
        st.info("第一次使用：請設定這一頁的進入密碼（只存在你的 Mac，不會上傳）。")
        with st.form("bank_set_pw"):
            a = st.text_input("設定密碼", type="password")
            b = st.text_input("再輸入一次", type="password")
            if st.form_submit_button("設定"):
                if a != b:
                    st.error("兩次不一樣")
                else:
                    try:
                        set_password(a)
                        st.session_state["bank_unlocked_at"] = now
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        return False
    with st.form("bank_login"):
        pw = st.text_input("請輸入銀行頁密碼", type="password")
        if st.form_submit_button("進入"):
            if check_password(pw):
                st.session_state["bank_unlocked_at"] = now
                st.rerun()
            else:
                st.error("密碼不對")
    st.caption(f"閒置 {LOCK_MINUTES} 分鐘會自動鎖定。忘記密碼：在 Mac 終端機執行 python3 -m bank_sync app-password 重設。")
    return False


def render_bank_page() -> None:
    st.subheader("銀行帳戶與信用卡")
    if not is_local():
        st.link_button("🏦 開啟本機銀行頁", "http://localhost:8502", type="primary")
        st.caption("銀行帳密和登入用的 Chrome 都只在你的 Mac 上，所以操作在本機頁面進行；這個按鈕只有在你的 Mac 上點才打得開。\n\n"
                   "還沒安裝本機服務的話，在 Mac 終端機執行一次："
                   "`cd ~/Documents/codex-workspace/investment-system-bank && git pull && python3 -m bank_sync app-install`")
        return
    render_bank_tools()


def render_bank_tools() -> None:
    """本機操作（不用密碼）：各銀行抓明細、確認表、寫入細帳、全年核對、信用卡、登入、探索。"""
    if os.environ.get("BANK_APP_SERVICE") == "1":
        with st.sidebar:
            st.caption("本機背景服務 http://localhost:8502")
            if st.button("⬇️ 更新程式並重新啟動", help="git pull 後重新啟動，約 10 秒後重新整理頁面"):
                st.info("更新中…約 10 秒後請重新整理頁面。")
                from bank_sync.app_service import restart_self
                restart_self()

    tab_bank, tab_ledger, tab_card, tab_login, tab_explore = st.tabs(
        ["銀行明細", "細帳確認與核對", "信用卡帳單", "登入銀行", "探索新銀行"])

    with tab_bank:
        st.markdown("每個帳戶從**上次抓到的最後一筆日期**查到今天。按下後會開 Chrome，請輸入驗證碼登入，之後自動查詢並登出。")
        c1, c2 = st.columns([1, 2])
        refetch = c1.checkbox("指定起始日重抓", key="tx_refetch")
        since = c2.date_input("起始日", value=date.today().replace(day=1), key="tx_since", disabled=not refetch)
        extra = ["--since", since.isoformat()] if refetch else []
        cols = st.columns(len(FETCH_BANKS))
        for col, (code, name) in zip(cols, FETCH_BANKS.items()):
            if col.button(f"🔄 {name}", key=f"tx_go_{code}", type="primary" if code == "taishin" else "secondary"):
                start_job(f"抓{name}明細", [f"fetch-{code}"] + extra)
        show = st.selectbox("顯示哪一家的最近結果", list(FETCH_BANKS), format_func=FETCH_BANKS.get, key="tx_show")
        render_taishin_results(show)

    with tab_ledger:
        st.markdown("**確認表**：把抓到、還沒寫進細帳的明細列在總帳「銀行明細確認」分頁（要確認的標黃），並模擬記入後核對銀行餘額。")
        c1, c2, c3 = st.columns(3)
        if st.button("📤 更新網頁明細（銀行明細／信用卡分頁）", key="bl_publish"):
            start_job("更新網頁明細", ["publish"])
        if c1.button("📝 產生確認表＋餘額模擬", key="bl_review", type="primary"):
            start_job("銀行明細確認表", ["bank-review"])
        if c2.button("🧪 模擬寫入（不寫）", key="bl_dry"):
            start_job("模擬寫入細帳", ["bank-ledger"])
        if c3.button("✍️ 寫入細帳", key="bl_apply"):
            st.session_state["bl_confirm"] = True
        if st.session_state.get("bl_confirm"):
            st.warning("會依確認表寫入 2026細帳與 2026細帳(含信用卡)，模擬餘額對不上會自動停止。")
            a, b = st.columns(2)
            if a.button("確定寫入", key="bl_apply_yes", type="primary"):
                st.session_state["bl_confirm"] = False
                start_job("寫入細帳", ["bank-ledger", "--apply"])
            if b.button("取消", key="bl_apply_no"):
                st.session_state["bl_confirm"] = False
        st.divider()
        st.markdown("**全年核對**：複製一份細帳，把沒記到的明細用底色標出（原本細帳不動），另列一張清單。")
        c1, c2 = st.columns(2)
        if c1.button("📥 先下載今年富邦／台新／將來，再核對", key="ba_fetch"):
            start_job("下載全年明細並核對", ["bank-audit", "--fetch"])
        if c2.button("🔍 用已下載的明細核對", key="ba_go"):
            start_job("全年核對", ["bank-audit"])

    with tab_card:
        st.markdown("從 jenny@hers.com.tw 信箱下載信用卡電子帳單，比對後寫入 2026細帳 備註與「2026細帳(含信用卡)」。")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("📥 下載新帳單", key="st_fetch"):
            start_job("下載信用卡帳單", ["fetch-statements"])
        if c2.button("🔍 解析預覽", key="st_preview"):
            start_job("帳單解析預覽", ["preview-statements"])
        if c3.button("📊 比對細帳（不寫入）", key="st_ledger"):
            start_job("信用卡 → 細帳 比對", ["ledger"])
        if c4.button("✍️ 寫入細帳", key="st_apply", type="primary"):
            st.session_state["confirm_apply"] = True
        if st.session_state.get("confirm_apply"):
            st.warning("會寫入總帳 2026細帳 備註、2026細帳(含信用卡)，並發行事曆。請先看過「比對細帳」的結果。")
            a, b = st.columns(2)
            if a.button("確定寫入", key="st_apply_yes", type="primary"):
                st.session_state["confirm_apply"] = False
                start_job("寫入細帳", ["ledger", "--apply"])
            if b.button("取消", key="st_apply_no"):
                st.session_state["confirm_apply"] = False
        render_statement_results()

    with tab_login:
        st.markdown("一次登入一家，自動填好帳密，你輸入驗證碼。用完按「繼續（Enter）」會自動登出並關閉 Chrome。")
        picked = st.multiselect("要登入的銀行", list(LOGIN_BANKS), format_func=LOGIN_BANKS.get, key="login_pick")
        if st.button("🔐 登入", key="login_go", disabled=not picked):
            start_job("登入：" + "、".join(LOGIN_BANKS[k] for k in picked), ["login", *picked])

    with tab_explore:
        st.markdown("給還沒自動化的銀行用：程式幫你登入後，你在 Chrome 用平常方式點到**交易明細**頁（選帳戶、期間、按查詢），"
                    "每到一頁按下方「📸 記錄目前頁面」；完成按「✅ 結束探索」。只記錄頁面結構（帳號遮蔽、不含金額），"
                    "存在 ~/Bank account/_explore/，看過後上傳給 Claude。")
        bank = st.selectbox("銀行", [k for k in LOGIN_BANKS if k != "sc"], format_func=LOGIN_BANKS.get, key="exp_bank")
        if st.button("🧭 開始探索", key="exp_go"):
            start_job(f"探索：{LOGIN_BANKS[bank]}", ["explore", bank])
        latest = _latest(BANK_DIR / "_explore", f"{bank}_2*.json")
        if latest:
            st.caption(f"最近一次探索記錄：{latest}")
            st.download_button("下載這份記錄（上傳給 Claude 用）", latest.read_bytes(), file_name=latest.name, key="exp_dl")

    st.divider()
    st.markdown("#### 執行過程")
    job_panel()
