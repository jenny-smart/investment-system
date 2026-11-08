"""「台指期夜盤」頁籤：讀 night-futures.yml 每天早上寫的 data/night_futures/，再算對目前持股的影響。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from invest_app.core import money, normalize_text, normalize_ticker, pct, signed_money, to_float, two_line_metric

try:
    import yfinance as yf
    HAS_YF = True
except Exception:  # noqa: BLE001
    HAS_YF = False

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "night_futures"
TWII = "^TWII"


def _load() -> tuple[dict[str, Any] | None, pd.DataFrame]:
    latest = None
    latest_path, history_path = DATA_DIR / "latest.json", DATA_DIR / "history.csv"
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    history = pd.read_csv(history_path) if history_path.exists() else pd.DataFrame()
    return latest, history


def _yahoo_symbol(ticker: str) -> str:
    t = normalize_ticker(ticker)
    if not t:
        return ""
    return t if t.endswith(".TW") or t.endswith(".TWO") else f"{t}.TW"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _beta_table(symbols: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    """近半年日報酬對加權指數的 beta 與相關係數。"""
    if not HAS_YF or not symbols:
        return {}
    raw = yf.download(list(symbols) + [TWII], period="6mo", interval="1d",
                      auto_adjust=True, progress=False, group_by="column")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    rets = close.pct_change(fill_method=None)
    if TWII not in rets:
        return {}
    market = rets[TWII]
    out = {}
    for s in symbols:
        if s not in rets:
            continue
        pair = pd.concat([rets[s], market], axis=1).dropna()
        if len(pair) < 30 or pair.iloc[:, 1].var() == 0:
            continue
        beta = pair.iloc[:, 0].cov(pair.iloc[:, 1]) / pair.iloc[:, 1].var()
        out[s] = {"beta": float(beta), "corr": float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))}
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _last_change(symbols: tuple[str, ...]) -> dict[str, float]:
    """美股持股最近一個交易日的漲跌幅。"""
    if not HAS_YF or not symbols:
        return {}
    raw = yf.download(list(symbols), period="10d", interval="1d", auto_adjust=True, progress=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": symbols[0]})
    out = {}
    for s in symbols:
        if s in close:
            c = close[s].dropna()
            if len(c) >= 2 and c.iloc[-2]:
                out[s] = float(c.iloc[-1] / c.iloc[-2] - 1)
    return out


def _holdings(enriched: pd.DataFrame, asset_type: str) -> pd.DataFrame:
    if enriched is None or enriched.empty:
        return pd.DataFrame()
    df = enriched[enriched["asset_type"].astype(str) == asset_type].copy()
    df["台幣市值"] = pd.to_numeric(df.get("台幣市值"), errors="coerce")
    df = df[df["台幣市值"].fillna(0) > 0]
    if df.empty:
        return df
    df["ticker"] = df["ticker"].map(normalize_ticker)
    # 同一檔分在不同券商／批次時合併
    return (df.groupby("ticker", as_index=False)
              .agg(名稱=("name", "first"), 台幣市值=("台幣市值", "sum")))


def _render_holdings_impact(enriched: pd.DataFrame, est_pct: float | None, latest: dict[str, Any]) -> None:
    st.markdown("#### 對我持股的影響")
    tw = _holdings(enriched, "台股")
    if tw.empty:
        st.info("目前沒有台股持倉資料。")
    elif est_pct is None:
        st.info("夜盤漲跌幅還沒有資料，無法估算。")
    else:
        tw["yahoo"] = tw["ticker"].map(_yahoo_symbol)
        with st.spinner("計算持股與大盤的連動（每 6 小時更新一次）…"):
            try:
                betas = _beta_table(tuple(sorted(set(tw["yahoo"]) - {""})))
            except Exception as exc:  # noqa: BLE001
                betas = {}
                st.caption(f"Beta 暫時算不出來：{exc}")
        tw["Beta"] = tw["yahoo"].map(lambda s: (betas.get(s) or {}).get("beta"))
        tw["相關係數"] = tw["yahoo"].map(lambda s: (betas.get(s) or {}).get("corr"))
        # 算不出 beta 的（新上市、資料不足）先當 1，跟大盤同步
        tw["預估漲跌幅"] = tw["Beta"].fillna(1.0) * est_pct
        tw["預估損益"] = tw["台幣市值"] * tw["預估漲跌幅"]
        total_value = tw["台幣市值"].sum()
        tw["佔台股部位"] = tw["台幣市值"] / total_value if total_value else None

        # 台積電另外用 ADR 漲跌參考
        quotes = {g["代號"]: g for g in latest.get("國際盤", [])}
        tsm_chg = (quotes.get("TSM") or {}).get("漲跌幅")

        total_pnl = tw["預估損益"].sum()
        weighted_beta = (tw["Beta"].fillna(1.0) * tw["台幣市值"]).sum() / total_value if total_value else None
        c1, c2, c3 = st.columns(3)
        two_line_metric(c1, "台股部位市值", money(total_value))
        two_line_metric(c2, "今日開盤預估損益", signed_money(total_pnl),
                        delta=pct(total_pnl / total_value) if total_value else "")
        two_line_metric(c3, "部位加權 Beta", f"{weighted_beta:.2f}" if weighted_beta is not None else "-",
                        sub="大於 1：波動比大盤大")

        show = tw.sort_values("台幣市值", ascending=False)
        st.dataframe(
            pd.DataFrame({
                "名稱": show["名稱"],
                "代號": show["ticker"],
                "台幣市值": show["台幣市值"].map(money),
                "佔台股部位": show["佔台股部位"].map(pct),
                "Beta": show["Beta"].map(lambda v: "-（以 1 計）" if pd.isna(v) else f"{v:.2f}"),
                "與大盤相關係數": show["相關係數"].map(lambda v: "-" if pd.isna(v) else f"{v:.2f}"),
                "預估漲跌幅": show["預估漲跌幅"].map(lambda v: f"{v:+.2%}"),
                "預估損益": show["預估損益"].map(signed_money),
            }),
            hide_index=True, use_container_width=True,
        )
        notes = ["預估漲跌幅＝個股 Beta（近半年日報酬對加權指數）× 夜盤近月漲跌幅；只是統計上的連動，個股消息面不在內。"]
        if tsm_chg is not None and any(t.startswith("2330") for t in tw["ticker"]):
            notes.append(f"台積電另可參考 ADR 昨夜 {tsm_chg:+.2%}。")
        st.caption(" ".join(notes))

    us = _holdings(enriched, "美股")
    if not us.empty:
        st.markdown("##### 美股持股昨夜表現")
        try:
            changes = _last_change(tuple(sorted(set(us["ticker"]) - {""})))
        except Exception as exc:  # noqa: BLE001
            changes = {}
            st.caption(f"美股漲跌暫時抓不到：{exc}")
        us["漲跌幅"] = us["ticker"].map(changes)
        us["損益"] = us["台幣市值"] / (1 + us["漲跌幅"]) * us["漲跌幅"]
        show = us.sort_values("台幣市值", ascending=False)
        st.dataframe(
            pd.DataFrame({
                "名稱": show["名稱"],
                "代號": show["ticker"],
                "台幣市值": show["台幣市值"].map(money),
                "昨夜漲跌幅": show["漲跌幅"].map(lambda v: "-" if pd.isna(v) else f"{v:+.2%}"),
                "昨夜損益（台幣）": show["損益"].map(lambda v: "-" if pd.isna(v) else signed_money(v)),
            }),
            hide_index=True, use_container_width=True,
        )


QUADRANTS = [  # 依象限圖位置：上排 劇本二｜劇本一，下排 劇本三｜劇本四
    (2, "夜盤上漲＋外資偏空", "先漲・小心開高走低", "#fff7ed", "#ea580c"),
    (1, "夜盤上漲＋外資偏多", "開高・續揚機率高", "#f0fdf4", "#16a34a"),
    (3, "夜盤下跌＋外資偏空", "開低・續跌機率高", "#fef2f2", "#dc2626"),
    (4, "夜盤下跌＋外資偏多", "先跌・開低反彈", "#eff6ff", "#2563eb"),
]


def _render_scenario(scn: dict[str, Any]) -> None:
    st.markdown("#### 四種劇本")
    current = scn.get("編號")
    cells = []
    for n, cond, read, bg, fg in QUADRANTS:
        active = n == current
        border = f"3px solid {fg}" if active else "1px solid #e2e8f0"
        opacity = "1" if active or current is None else ".45"
        badge = ('<span style="float:right;background:%s;color:#fff;border-radius:999px;padding:1px 10px;'
                 'font-size:.75rem">今天</span>' % fg) if active else ""
        cells.append(
            f'<div style="background:{bg};border:{border};border-radius:12px;padding:12px 14px;opacity:{opacity}">'
            f'<div style="font-weight:700;color:{fg}">劇本{"一二三四"[n - 1]}{badge}</div>'
            f'<div style="color:#334155;font-size:.9rem;margin-top:4px">{cond}</div>'
            f'<div style="color:#1e293b;font-weight:600;margin-top:4px">{read}</div></div>')
    st.markdown(
        '<div style="display:grid;grid-template-columns:auto 1fr 1fr;gap:10px;align-items:stretch;margin-bottom:.5rem">'
        '<div style="writing-mode:vertical-rl;color:#64748b;font-size:.8rem;text-align:center">夜盤漲 ↑</div>'
        + cells[0] + cells[1]
        + '<div style="writing-mode:vertical-rl;color:#64748b;font-size:.8rem;text-align:center">夜盤跌 ↓</div>'
        + cells[2] + cells[3]
        + '<div></div><div style="color:#64748b;font-size:.8rem;text-align:center">← 外資偏空</div>'
        '<div style="color:#64748b;font-size:.8rem;text-align:center">外資偏多 →</div></div>',
        unsafe_allow_html=True,
    )
    confidence = scn.get("可信度", "")
    conf_color = {"可信度高": "#16a34a", "可信度低": "#ea580c"}.get(confidence, "#64748b")
    st.markdown(f'<div style="margin-bottom:1rem"><b style="color:{conf_color}">{confidence}</b>'
                f'<span style="color:#475569">　{scn.get("說明", "")}</span></div>', unsafe_allow_html=True)
    st.caption("看法：① 夜盤漲跌決定隔天開盤方向 ② 夜盤量佔比確認方向可不可信（高於近 20 晚平均＝可信度高）"
               " ③ 外資多空淨額判斷外資站哪邊，推估走哪一種劇本。")


def render_night_futures_page(enriched: pd.DataFrame) -> None:
    st.markdown("### 台指期夜盤")
    latest, history = _load()
    if not latest:
        st.info("還沒有夜盤資料。每天早上 07:00 自動更新；也可以到 GitHub Actions 手動執行「Taiwan futures night session」。")
        return

    night = latest.get("夜盤") or {}
    foreign = latest.get("外資夜盤") or {}
    est = latest.get("開盤預估") or {}
    st.caption(f"夜盤 {night.get('日盤日期', '')} 15:00～次日 05:00（期交所歸屬日 {night.get('夜盤日期', '')}）"
               f"｜近月 {night.get('契約月份', '')}｜更新 {latest.get('更新時間', '')}")

    c1, c2, c3, c4, c5 = st.columns(5)
    two_line_metric(c1, "夜盤收盤", money(night.get("夜盤收盤")),
                    sub=f"高 {money(night.get('夜盤最高'))}／低 {money(night.get('夜盤最低'))}",
                    delta=f"{signed_money(night.get('夜盤漲跌點'))} 點（{pct(night.get('夜盤漲跌幅'))}）"
                    if night.get("夜盤漲跌點") is not None else "")
    two_line_metric(c2, "日盤成交量", money(night.get("日盤成交量")), sub=f"日盤 {night.get('日盤日期', '')}")
    two_line_metric(c3, "夜盤成交量", money(night.get("夜盤成交量")), sub="TX 各月份合計（不含價差單）")
    two_line_metric(c4, "夜盤量佔比", pct(night.get("夜盤量佔比")), sub="夜盤量 ÷（日盤量＋夜盤量）")
    if foreign:
        two_line_metric(c5, "外資夜盤多空淨額", f"{signed_money(foreign.get('淨額口數'))} 口",
                        sub=f"{signed_money((to_float(foreign.get('淨額千元')) or 0) / 1e5)} 億元"
                        f"（多 {money(foreign.get('多方口數'))}／空 {money(foreign.get('空方口數'))}）")
    else:
        two_line_metric(c5, "外資夜盤多空淨額", "-", sub="期交所尚未公布")

    _render_scenario(latest.get("劇本") or {})

    st.markdown("#### 今日開盤預估")
    direction = est.get("方向", "無法判斷")
    color = {"開高": "#dc2626", "開低": "#059669"}.get(direction, "#475569")  # 台股慣例：紅漲綠跌
    est_open = to_float(est.get("預估開盤"))
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 18px;margin-bottom:1rem">'
        f'<span style="font-size:1.3rem;font-weight:700;color:{color}">{direction}</span>'
        f'<span style="margin-left:12px;color:#475569">加權指數預估開盤 {money(est_open)}'
        f'（前收 {money(est.get("加權指數前收"))}，{pct(est.get("預估漲跌幅"))}）</span>'
        + "".join(f'<div style="color:#334155;margin-top:6px">• {s}</div>' for s in est.get("依據", []))
        + f'<div style="font-size:.8rem;color:#94a3b8;margin-top:8px">{est.get("說明", "")}</div></div>',
        unsafe_allow_html=True,
    )

    _render_holdings_impact(enriched, to_float(est.get("預估漲跌幅")), latest)

    st.markdown("#### 國際盤")
    gq = pd.DataFrame(latest.get("國際盤", []))
    if not gq.empty:
        st.dataframe(
            pd.DataFrame({
                "名稱": gq["名稱"],
                "收盤": gq["收盤"].map(lambda v: money(v, 2)),
                "漲跌": gq["漲跌"].map(lambda v: "-" if v is None or pd.isna(v) else f"{v:+,.2f}"),
                "漲跌幅": gq["漲跌幅"].map(lambda v: "-" if v is None or pd.isna(v) else f"{v:+.2%}"),
                "日期": gq["日期"],
            }),
            hide_index=True, use_container_width=True,
        )

    if not history.empty:
        st.markdown("#### 近期走勢")
        h = history.tail(30).copy()
        h["夜盤日期"] = h["夜盤日期"].astype(str)
        h = h.set_index("夜盤日期")
        left, right = st.columns(2)
        with left:
            st.caption("夜盤量佔比")
            st.line_chart(pd.to_numeric(h["夜盤量佔比"], errors="coerce"), height=220)
        with right:
            st.caption("外資夜盤多空淨額（口）")
            st.bar_chart(pd.to_numeric(h["外資夜盤多空淨額口數"], errors="coerce"), height=220)
        with st.expander("每晚明細"):
            st.dataframe(history.iloc[::-1], hide_index=True, use_container_width=True)

    news = latest.get("新聞", [])
    if news:
        st.markdown("#### 重要新聞")
        for n in news:
            meta = "・".join(x for x in [normalize_text(n.get("來源")), normalize_text(n.get("時間"))] if x)
            st.markdown(f"- [{n.get('標題', '')}]({n.get('連結', '')})　<span style='color:#94a3b8;font-size:.85rem'>{meta}</span>",
                        unsafe_allow_html=True)
