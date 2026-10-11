"""股票研究頁：持股分析、觀察股票池、熱門候選。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False
from invest_app.core import (
    normalize_ticker,
)


def render_research_page(enriched) -> None:
    st.markdown("### 股票研究")
    st.caption("「提前發現」已直接套用在目前持股與熱門候選，不另外分頁；每檔一起看基本面、籌碼、相對強度與技術面。")

    own_tab, watch_tab, hot_tab = st.tabs(["📌 目前台股持股分析", "👀 觀察股票池", "🔥 熱門中短線候選"])

    def _technical_snapshot(ticker: str) -> dict[str, Any]:
        if not HAS_YF or not ticker:
            return {}
        try:
            hist = yf.Ticker(ticker).history(period="6mo", interval="1d", auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist:
                return {}
            close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
            volume = pd.to_numeric(hist.get("Volume", pd.Series(index=hist.index, dtype=float)), errors="coerce")
            if len(close) < 25:
                return {}
            ma5 = close.rolling(5).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean().replace(0, pd.NA)
            rsi = (100 - 100 / (1 + gain / loss)).iloc[-1]
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = (ema12 - ema26).iloc[-1]
            signal = (ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1]
            ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else None
            ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else None
            vol20 = volume.rolling(20).mean().iloc[-1] if len(volume.dropna()) >= 20 else None
            vol_ratio = (volume.iloc[-1] / vol20) if vol20 and vol20 > 0 else None
            support = close.tail(20).min()
            resistance = close.tail(20).max()
            trend = "偏多" if close.iloc[-1] > ma20 and ma5 > ma20 else ("偏空" if close.iloc[-1] < ma20 and ma5 < ma20 else "盤整")
            return {
                "close": float(close.iloc[-1]), "ma5": float(ma5), "ma20": float(ma20),
                "ma60": float(ma60) if ma60 is not None and pd.notna(ma60) else None,
                "rsi": float(rsi) if pd.notna(rsi) else None,
                "macd": float(macd), "signal": float(signal),
                "ret5": float(ret5) if ret5 is not None else None,
                "ret20": float(ret20) if ret20 is not None else None,
                "vol_ratio": float(vol_ratio) if vol_ratio is not None else None,
                "support": float(support), "resistance": float(resistance), "trend": trend,
            }
        except Exception:
            return {}

    def _analysis_label(s: dict[str, Any]) -> tuple[str, str, float | None]:
        if not s:
            return "資料不足", "缺少足夠行情", None
        rsi, ret5, ret20 = s.get("rsi"), s.get("ret5") or 0, s.get("ret20") or 0
        close, trend = s.get("close") or 0, s.get("trend", "盤整")
        target = s.get("resistance")
        if trend == "偏多" and close >= (target or 0):
            price_range = max(0, (s.get("resistance") or close) - (s.get("support") or close))
            target = close + price_range * 0.5 if price_range else close * 1.05
        if trend == "偏多" and (rsi is None or rsi < 75) and ret20 > 0:
            return "動能偏強", "價格站上 MA20、短均線偏多", float(target) if target else None
        if (rsi is not None and rsi >= 75) or ret5 >= 15:
            return "注意追高風險", "短線漲幅或 RSI 已偏高", float(target) if target else None
        if trend == "偏空":
            return "弱勢觀察", "價格與短均線結構偏弱", float(target) if target else None
        return "整理觀察", "趨勢尚未形成明確方向", float(target) if target else None

    @st.cache_data(ttl=1800, show_spinner=False)
    def _batch_stock_analysis(items: tuple[tuple[str, str], ...]) -> pd.DataFrame:
        rows = []
        for name, ticker in items:
            s = _technical_snapshot(ticker)
            label, reason, target = _analysis_label(s)
            rows.append({"股票": name, "代號": ticker, "最新價": s.get("close"), "技術目標價": target,
                         "分析註記": label, "分析原因": reason, "近5日%": s.get("ret5"),
                         "近20日%": s.get("ret20"), "RSI14": s.get("rsi"),
                         "支撐": s.get("support"), "壓力": s.get("resistance")})
        return pd.DataFrame(rows)

    def _two_decimal_display(df: pd.DataFrame, text_cols: list[str]) -> pd.DataFrame:
        out = df.copy()
        for col in out.columns:
            if col not in text_cols:
                out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
        return out

    def _research_column_config(df: pd.DataFrame, text_cols: list[str]) -> dict:
        return {
            col: st.column_config.NumberColumn(col, format="%.2f")
            for col in df.columns if col not in text_cols
        }

    @st.cache_data(ttl=3600, show_spinner=False)
    def _corporate_event_note(ticker: str) -> str:
        if not HAS_YF or not ticker:
            return ""
        try:
            t = yf.Ticker(ticker)
            notes = []
            div = t.dividends
            if div is not None and not div.empty:
                recent = div.tail(1)
                dt, amount = recent.index[-1], float(recent.iloc[-1])
                if (pd.Timestamp.now(tz=dt.tz) - dt).days <= 120:
                    notes.append(f"近期現金股利 {amount:.2f}（{dt.date()}）")
            splits = t.splits
            if splits is not None and not splits.empty:
                dt, ratio = splits.index[-1], float(splits.iloc[-1])
                if (pd.Timestamp.now(tz=dt.tz) - dt).days <= 180:
                    notes.append(f"近期股票分割/股票事件 {ratio:.2f}（{dt.date()}）")
            actions = getattr(t, "actions", None)
            if actions is not None and not actions.empty:
                recent_actions = actions.tail(8)
                for dt, row in recent_actions.iterrows():
                    for col in recent_actions.columns:
                        if "capital" in str(col).lower() and pd.notna(row[col]) and float(row[col]) != 0:
                            notes.append(f"近期資本事件 {dt.date()}")
            return "；".join(dict.fromkeys(notes))
        except Exception:
            return ""

    def _render_snapshot(s: dict[str, Any]) -> None:
        if not s:
            st.warning("目前無法取得足夠歷史行情，稍後再試。")
            return
        a, b, c1, d = st.columns(4)
        a.metric("最新價", f"{s['close']:.2f}")
        b.metric("技術趨勢", s["trend"])
        c1.metric("近 5 日", f"{s['ret5']:+.1f}%" if s.get("ret5") is not None else "-")
        d.metric("近 20 日", f"{s['ret20']:+.1f}%" if s.get("ret20") is not None else "-")
        st.write(
            f"MA5 **{s['ma5']:.2f}**｜MA20 **{s['ma20']:.2f}**"
            + (f"｜MA60 **{s['ma60']:.2f}**" if s.get("ma60") is not None else "")
            + (f"｜RSI14 **{s['rsi']:.1f}**" if s.get("rsi") is not None else "")
            + f"｜20 日支撐約 **{s['support']:.2f}**｜壓力約 **{s['resistance']:.2f}**"
        )
        notes = []
        if s["trend"] == "偏多":
            notes.append("價格與短均線結構偏強")
        elif s["trend"] == "偏空":
            notes.append("價格與短均線結構偏弱")
        else:
            notes.append("均線仍在整理")
        if s.get("rsi") is not None:
            if s["rsi"] >= 70:
                notes.append("RSI 偏高，追價風險增加")
            elif s["rsi"] <= 30:
                notes.append("RSI 偏低，留意是否只是弱勢反彈")
        if s.get("vol_ratio") is not None and s["vol_ratio"] >= 1.5:
            notes.append("今日量能明顯高於 20 日均量")
        st.info("；".join(notes) + "。")

    @st.cache_data(ttl=21600, show_spinner=False)
    def _growth_snapshot(ticker: str) -> dict[str, Any]:
        if not HAS_YF or not ticker:
            return {}
        try:
            t = yf.Ticker(ticker)
            inc = t.quarterly_income_stmt
            def _series(names):
                if inc is None or inc.empty:
                    return pd.Series(dtype=float)
                for name in names:
                    if name in inc.index:
                        return pd.to_numeric(inc.loc[name], errors="coerce").dropna()
                return pd.Series(dtype=float)
            eps = _series(["Diluted EPS", "Basic EPS"])
            rev = _series(["Total Revenue", "Operating Revenue"])
            eps_yoy = ((eps.iloc[0] / eps.iloc[4] - 1) * 100) if len(eps) >= 5 and eps.iloc[4] != 0 else None
            rev_yoy = ((rev.iloc[0] / rev.iloc[4] - 1) * 100) if len(rev) >= 5 and rev.iloc[4] != 0 else None
            eps_accel = None
            if len(eps) >= 6 and eps.iloc[4] != 0 and eps.iloc[5] != 0:
                prev_yoy = (eps.iloc[1] / eps.iloc[5] - 1) * 100
                eps_accel = eps_yoy - prev_yoy if eps_yoy is not None else None
            return {"EPS YoY%": eps_yoy, "營收 YoY%": rev_yoy, "EPS加速度": eps_accel}
        except Exception:
            return {}

    @st.cache_data(ttl=1800, show_spinner=False)
    def _relative_strength(ticker: str) -> dict[str, Any]:
        if not HAS_YF or not ticker:
            return {}
        try:
            stock = yf.Ticker(ticker).history(period="4mo", interval="1d", auto_adjust=False)["Close"].dropna()
            market = yf.Ticker("^TWII").history(period="4mo", interval="1d", auto_adjust=False)["Close"].dropna()
            def _ret(s, n):
                return (s.iloc[-1] / s.iloc[-n-1] - 1) * 100 if len(s) > n else None
            s20, s60, m20, m60 = _ret(stock, 20), _ret(stock, 60), _ret(market, 20), _ret(market, 60)
            return {
                "相對強度1月": s20 - m20 if s20 is not None and m20 is not None else None,
                "相對強度3月": s60 - m60 if s60 is not None and m60 is not None else None,
                "大盤1月%": m20,
            }
        except Exception:
            return {}


    def _apply_early_discovery(df: pd.DataFrame) -> pd.DataFrame:
        """Apply early-discovery signals to any stock analysis table."""
        out = df.copy()
        if out.empty or "代號" not in out.columns:
            return out
        growth = [_growth_snapshot(t) for t in out["代號"].tolist()]
        rs = [_relative_strength(t) for t in out["代號"].tolist()]
        snaps = [_technical_snapshot(t) for t in out["代號"].tolist()]
        for col in ["EPS YoY%","營收 YoY%","EPS加速度"]:
            out[col] = [x.get(col) for x in growth]
        for col in ["相對強度1月","相對強度3月","大盤1月%"]:
            out[col] = [x.get(col) for x in rs]
        out["量比"] = [x.get("vol_ratio") for x in snaps]

        def _stage(row):
            score, why = 0, []
            eps, rev, accel = row.get("EPS YoY%"), row.get("營收 YoY%"), row.get("EPS加速度")
            foreign, trust = row.get("外資買賣超"), row.get("投信買賣超")
            rs1, rs3, vr = row.get("相對強度1月"), row.get("相對強度3月"), row.get("量比")
            rsi, ret5 = row.get("RSI14"), row.get("近5日%")
            if pd.notna(eps) and eps > 15: score += 2; why.append("EPS成長")
            if pd.notna(accel) and accel > 0: score += 1; why.append("EPS加速")
            if pd.notna(rev) and rev > 10: score += 2; why.append("營收成長")
            if pd.notna(foreign) and foreign > 0: score += 1; why.append("外資買超")
            if pd.notna(trust) and trust > 0: score += 1; why.append("投信買超")
            if pd.notna(rs1) and rs1 > 0: score += 1; why.append("1月強於大盤")
            if pd.notna(rs3) and rs3 > 0: score += 1; why.append("3月強於大盤")
            if pd.notna(vr) and vr >= 1.2: score += 1; why.append("量能放大")
            if row.get("分析註記") == "動能偏強": score += 1; why.append("均線轉強")
            if (pd.notna(rsi) and rsi >= 75) or (pd.notna(ret5) and ret5 >= 15):
                return pd.Series(["🔴 過熱期", score, "短線漲幅/RSI偏高"])
            if score >= 7:
                return pd.Series(["🟡 啟動期", score, "、".join(why)])
            if score >= 4:
                return pd.Series(["🟢 潛伏期", score, "、".join(why)])
            return pd.Series(["⚪ 觀察", score, "、".join(why) or "訊號不足"])

        staged = out.apply(_stage, axis=1)
        staged.columns = ["提前階段","提前分數","提前觸發原因"]
        return pd.concat([out, staged], axis=1)

    WATCHLIST_STOCKS = [
        ("富邦金","2881.TW"),("國泰金","2882.TW"),("王品","2727.TW"),("五福","2745.TWO"),("意騰-KY","7749.TW"),
        ("士電","1503.TW"),("達興材料","5234.TW"),("創意","3443.TW"),("光寶科","2301.TW"),("台積電","2330.TW"),
        ("台達電","2308.TW"),("盟立","2464.TW"),("昇達科","3491.TWO"),("啟碁","6285.TW"),("國巨*","2327.TW"),
        ("華新科","2492.TW"),("旺宏","2337.TW"),("力積電","6770.TW"),("南亞科","2408.TW"),("群聯","8299.TWO"),
        ("勝一","1773.TW"),("富邦科技","0052.TW"),("南電","8046.TW"),("鴻勁","7769.TW"),("高僑","6234.TWO"),
        ("聯電","2303.TW"),("穩懋","3105.TWO"),("尚茂","8291.TWO"),("致茂","2360.TW"),("宇隆","2233.TW"),
        ("京元電子","2449.TW"),("益登","3048.TW"),("合晶","6182.TWO"),("泰創工程","6750.TW"),("雷虎","8033.TW"),
        ("漢唐","2404.TW"),("倍利科","7822.TW"),("台光電","2383.TW"),("華通","2313.TW"),("耀華","2367.TW"),
        ("麗嬰房","2911.TW"),("臻鼎-KY","4958.TW"),("同欣電","6271.TW"),("信昌電","6173.TWO"),("金山電","8042.TW"),
        ("禾伸堂","3026.TW"),("康舒","6282.TW"),("茂迪","6244.TWO"),("高力","8996.TW"),("振發","5426.TWO"),
        ("所羅門","2359.TW"),("日月光投控","3711.TW"),("聯發科","2454.TW"),("大立光","3008.TW"),("南茂","8150.TW"),
        ("希華","2484.TW"),("健策","3653.TW"),("聯亞","3081.TWO"),("全新","2455.TW"),("金像電","2368.TW"),
        ("川湖","2059.TW"),("寶雅","5904.TWO"),("仁寶","2324.TW"),("鼎元","2426.TW"),("友達","2409.TW"),
        ("世紀*","5314.TWO"),("新鼎","5209.TWO"),("晉泰","6221.TWO"),("環球晶","6488.TWO"),("台特化","4772.TW"),
        ("崇越","5434.TWO"),("昇陽半導體","8028.TW"),("台塑","1301.TW"),
    ]

    @st.cache_data(ttl=21600, show_spinner=False)
    def _analyst_snapshot(ticker: str) -> dict[str, Any]:
        if not HAS_YF or not ticker: return {}
        try:
            info = yf.Ticker(ticker).info or {}
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            target = info.get("targetMeanPrice")
            return {"市場目標價": target, "目標價低": info.get("targetLowPrice"), "目標價高": info.get("targetHighPrice"),
                    "目標價空間%": ((target/current-1)*100) if target and current else None,
                    "Forward EPS": info.get("forwardEps"), "Forward PE": info.get("forwardPE")}
        except Exception: return {}

    with watch_tab:
        st.markdown("#### 👀 完整觀察股票池")
        st.caption("已納入本次截圖與影片股票；目標價取可取得的分析師共識，缺資料留空，不猜數字。")
        watch = _batch_stock_analysis(tuple(WATCHLIST_STOCKS))
        if not watch.empty:
            radar_path_watch = Path(__file__).resolve().parent / "data" / "stock_radar" / "latest.csv"
            if radar_path_watch.exists():
                rw = pd.read_csv(radar_path_watch, dtype={"代號": str})
                rw["代號_key"] = rw["代號"].astype(str).str.replace(r"\.0$", "", regex=True)
                watch["代號_key"] = watch["代號"].astype(str).str.extract(r"(\d{4,6})", expand=False)
                cols = [x for x in ["代號_key","外資買賣超","投信買賣超","自營商買賣超","三大法人買賣超"] if x in rw.columns]
                watch = watch.merge(rw[cols], on="代號_key", how="left").drop(columns=["代號_key"])
            for col in ["外資買賣超","投信買賣超","自營商買賣超","三大法人買賣超"]:
                if col not in watch: watch[col] = pd.NA
            watch = _apply_early_discovery(watch)
            analyst = [_analyst_snapshot(t) for t in watch["代號"].tolist()]
            for col in ["市場目標價","目標價低","目標價高","目標價空間%","Forward EPS","Forward PE"]:
                watch[col] = [x.get(col) for x in analyst]
            watch["近期股利/資本事件"] = watch["代號"].map(_corporate_event_note)
            wanted = ["股票","代號","最新價","市場目標價","目標價空間%","目標價低","目標價高","Forward EPS","Forward PE",
                      "EPS YoY%","EPS加速度","營收 YoY%","外資買賣超","投信買賣超","三大法人買賣超","提前階段","提前分數",
                      "提前觸發原因","量比","相對強度1月","相對強度3月","近5日%","近20日%","RSI14","技術目標價","分析註記","近期股利/資本事件"]
            wanted = [x for x in wanted if x in watch.columns]
            text_cols = ["股票","代號","提前階段","提前觸發原因","分析註記","近期股利/資本事件"]
            out = _two_decimal_display(watch[wanted], text_cols)
            st.dataframe(out, use_container_width=True, hide_index=True, column_config=_research_column_config(out, text_cols))
            st.caption("市場目標價與 Forward EPS/PE 依資料源即時可得值；缺漏的 2026/2027 年度 EPS 不自行推估。")

    with own_tab:
        tw_holdings = enriched[enriched["platform"] == "台股"].copy() if not enriched.empty else pd.DataFrame()
        if tw_holdings.empty:
            st.info("目前沒有台股持倉資料。")
        else:
            st.markdown("#### ① 先看全部持股（依股票加總）")
            grouped_rows = []
            for ticker, group in tw_holdings.groupby("ticker", dropna=False):
                units = pd.to_numeric(group.get("units", 0), errors="coerce").fillna(0).sum()
                cost = pd.to_numeric(group.get("台幣成本", 0), errors="coerce").fillna(0).sum()
                value = pd.to_numeric(group.get("台幣市值", 0), errors="coerce").fillna(0).sum()
                dividend = pd.to_numeric(group.get("累計已領配息", 0), errors="coerce").fillna(0).sum()
                price = pd.to_numeric(group.get("即時價格/淨值", 0), errors="coerce").dropna()
                avg_cost = cost / units if units > 0 else 0
                pnl = value - cost
                total_pnl = pnl + dividend
                grouped_rows.append({
                    "name": group["name"].dropna().iloc[0] if "name" in group and not group["name"].dropna().empty else "",
                    "ticker": ticker,
                    "units": units,
                    "avg_cost": avg_cost,
                    "即時價格/淨值": float(price.iloc[0]) if not price.empty else None,
                    "台幣成本": cost,
                    "台幣市值": value,
                    "價差損益": pnl,
                    "價差損益率": pnl / cost if cost > 0 else None,
                    "累計已領配息": dividend,
                    "含息總損益": total_pnl,
                    "含息總損益率": total_pnl / cost if cost > 0 else None,
                })
            tw_holdings_grouped = pd.DataFrame(grouped_rows)
            grouped_numeric_cols = [x for x in tw_holdings_grouped.columns if x not in ["name", "ticker"]]
            grouped_display = _two_decimal_display(tw_holdings_grouped, ["name", "ticker"])
            st.dataframe(
                grouped_display,
                use_container_width=True,
                hide_index=True,
                column_config=_research_column_config(grouped_display, ["name", "ticker"]),
            )
            st.markdown("#### 今日持股分析")
            holding_items = tuple((str(r.get("name", "")), normalize_ticker(r.get("ticker", ""))) for _, r in tw_holdings_grouped.iterrows() if normalize_ticker(r.get("ticker", "")))
            holding_analysis = _batch_stock_analysis(holding_items)
            if not holding_analysis.empty:
                radar_path_for_holdings = Path(__file__).resolve().parent / "data" / "stock_radar" / "latest.csv"
                if radar_path_for_holdings.exists():
                    radar_hold = pd.read_csv(radar_path_for_holdings, dtype={"代號": str})
                    radar_hold["代號_key"] = radar_hold["代號"].astype(str).str.replace(r"\.0$", "", regex=True)
                    holding_analysis["代號_key"] = holding_analysis["代號"].astype(str).str.extract(r"(\d{4,6})", expand=False)
                    inst_cols = [x for x in ["代號_key", "外資買賣超", "投信買賣超", "自營商買賣超", "三大法人買賣超"] if x in radar_hold.columns]
                    holding_analysis = holding_analysis.merge(radar_hold[inst_cols], on="代號_key", how="left").drop(columns=["代號_key"])
                for col in ["外資買賣超", "投信買賣超", "自營商買賣超", "三大法人買賣超"]:
                    if col not in holding_analysis:
                        holding_analysis[col] = pd.NA
                holding_analysis["近期股利/資本事件"] = holding_analysis["代號"].map(_corporate_event_note)

                @st.cache_data(ttl=21600, show_spinner=False)
                def _fundamental_snapshot(ticker: str) -> dict[str, Any]:
                    if not HAS_YF or not ticker:
                        return {}
                    try:
                        t = yf.Ticker(ticker)
                        bs = t.quarterly_balance_sheet
                        inc = t.quarterly_income_stmt
                        def _latest(frame, names):
                            if frame is None or frame.empty:
                                return None
                            for name in names:
                                if name in frame.index:
                                    vals = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
                                    if not vals.empty:
                                        return float(vals.iloc[0])
                            return None
                        cash = _latest(bs, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash"])
                        debt = _latest(bs, ["Total Debt"])
                        if debt is None:
                            current_debt = _latest(bs, ["Current Debt", "Current Debt And Capital Lease Obligation"]) or 0
                            long_debt = _latest(bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]) or 0
                            debt = current_debt + long_debt if current_debt or long_debt else None
                        revenue = _latest(inc, ["Total Revenue", "Operating Revenue"])
                        gross_profit = _latest(inc, ["Gross Profit"])
                        gross_margin = (gross_profit / revenue * 100) if gross_profit is not None and revenue not in (None, 0) else None
                        return {"現金": cash, "負債": debt, "毛利率%": gross_margin}
                    except Exception:
                        return {}

                fundamentals = []
                for ticker in holding_analysis["代號"].tolist():
                    fundamentals.append(_fundamental_snapshot(ticker))
                holding_analysis["現金"] = [x.get("現金") for x in fundamentals]
                holding_analysis["負債"] = [x.get("負債") for x in fundamentals]
                holding_analysis["毛利率%"] = [x.get("毛利率%") for x in fundamentals]
                holding_analysis = _apply_early_discovery(holding_analysis)
                units_map = tw_holdings_grouped.set_index("ticker")["units"].to_dict()
                holding_analysis["持股數"] = holding_analysis["代號"].map(units_map).fillna(0)
                holding_analysis["目標價潛在價差"] = (
                    (pd.to_numeric(holding_analysis["技術目標價"], errors="coerce")
                     - pd.to_numeric(holding_analysis["最新價"], errors="coerce"))
                    * pd.to_numeric(holding_analysis["持股數"], errors="coerce").fillna(0)
                )
                ordered = ["股票", "代號", "持股數", "最新價", "技術目標價", "目標價潛在價差",
                           "提前階段", "提前分數", "提前觸發原因", "分析註記", "分析原因", "EPS YoY%", "EPS加速度", "營收 YoY%", "量比", "相對強度1月", "相對強度3月", "現金", "負債", "毛利率%", "外資買賣超", "投信買賣超", "自營商買賣超", "三大法人買賣超",
                           "近期股利/資本事件", "近5日%", "近20日%", "RSI14", "支撐", "壓力"]
                holding_analysis = holding_analysis[[x for x in ordered if x in holding_analysis.columns]]
                display_analysis = holding_analysis.rename(columns={"目標價潛在價差": "(目標價－目前股價) × 持股數"})
                display_analysis = _two_decimal_display(display_analysis, ["股票", "代號", "提前階段", "提前觸發原因", "分析註記", "分析原因", "近期股利/資本事件"])
                st.dataframe(
                    display_analysis,
                    use_container_width=True,
                    hide_index=True,
                    column_config=_research_column_config(display_analysis, ["股票", "代號", "分析註記", "分析原因", "近期股利/資本事件"]),
                )
                st.caption("技術目標價為近期支撐、壓力與價格區間的觀察位，不是券商目標價。")
                focus = holding_analysis[holding_analysis["分析註記"].isin(["動能偏強", "注意追高風險", "弱勢觀察"])]
                if not focus.empty:
                    st.markdown("#### 📍 今日持股注意清單")
                    st.dataframe(focus[["股票", "代號", "分析註記", "分析原因", "最新價", "技術目標價"]], use_container_width=True, hide_index=True)
            st.markdown("#### ② 選一檔做技術分析")
            labels = tw_holdings_grouped.apply(lambda r: f"{r.get('name','')}｜{r.get('ticker','')}", axis=1).tolist()
            selected_label = st.selectbox("選擇持股", labels, key="research_owned_stock")
            if selected_label:
                row = tw_holdings_grouped.iloc[labels.index(selected_label)]
                ticker = normalize_ticker(row.get("ticker", ""))
                if st.button("分析這檔持股", key="analyze_owned_stock", type="primary"):
                    snap = _technical_snapshot(ticker)
                    st.session_state["owned_research_snapshot"] = snap
                    st.session_state["owned_research_name"] = row.get("name", ticker)
                if st.session_state.get("owned_research_name") == row.get("name", ticker):
                    _render_snapshot(st.session_state.get("owned_research_snapshot", {}))
                    st.caption("搭配上方成本與現有損益一起看；這裡不會修改持股資料。")

    with hot_tab:
        st.markdown("#### ① 更新今日熱門候選")
        st.write("以台股上市股票的估值、外資／投信、三大法人、成交量與當日價格方向先篩選，再查看技術面。")
        if st.button("更新熱門候選", key="refresh_hot_radar", type="primary"):
            try:
                from stock_radar.pipeline import build_daily_radar
                build_daily_radar()
                st.success("今日熱門候選已更新。")
            except Exception as e:
                st.error(f"更新失敗：{e}")

        radar_path = Path(__file__).resolve().parent / "data" / "stock_radar" / "latest.csv"
        if radar_path.exists():
            radar_df = pd.read_csv(radar_path, dtype={"代號": str})
            hot = radar_df[radar_df["雷達分數"] >= 4].sort_values(
                ["雷達分數", "三大法人買賣超", "成交股數"], ascending=[False, False, False]
            ).head(20).copy()
            if hot.empty:
                st.info("今天沒有股票達到目前雷達門檻。")
            else:
                st.markdown("#### ② 今日研究候選")
                hot_cols = [x for x in ["代號", "名稱", "收盤價", "漲跌幅%", "本益比", "外資買賣超", "投信買賣超", "成交股數", "雷達分數", "入選原因"] if x in hot.columns]
                st.dataframe(hot[hot_cols], use_container_width=True, hide_index=True)
                market_items = tuple((str(r["名稱"]), f"{r['代號']}.TW") for _, r in hot.iterrows())
                market_analysis = _batch_stock_analysis(market_items)
                if not market_analysis.empty:
                    market_analysis["代號_key"] = market_analysis["代號"].astype(str).str.extract(r"(\d{4,6})", expand=False)
                    hot_merge = hot.copy()
                    hot_merge["代號_key"] = hot_merge["代號"].astype(str).str.replace(r"\.0$", "", regex=True)
                    merge_cols = [x for x in ["代號_key","外資買賣超","投信買賣超","自營商買賣超","三大法人買賣超"] if x in hot_merge.columns]
                    market_analysis = market_analysis.merge(hot_merge[merge_cols], on="代號_key", how="left").drop(columns=["代號_key"])
                    market_analysis = _apply_early_discovery(market_analysis)
                    market_focus = market_analysis[
                        market_analysis["提前階段"].isin(["🟢 潛伏期","🟡 啟動期","🔴 過熱期"])
                    ].copy()
                    st.markdown("#### 📍 今日市場注意清單")
                    if market_focus.empty:
                        st.info("目前候選中沒有形成明確中短線動能訊號的股票。")
                    else:
                        market_focus = market_focus.copy()
                        market_focus["近期股利/資本事件"] = market_focus["代號"].map(_corporate_event_note)
                        st.dataframe(
                            _two_decimal_display(
                                market_focus[["股票", "代號", "提前階段", "提前分數", "提前觸發原因", "最新價", "技術目標價", "分析註記", "分析原因", "近期股利/資本事件", "EPS YoY%", "EPS加速度", "營收 YoY%", "外資買賣超", "投信買賣超", "量比", "相對強度1月", "相對強度3月", "近5日%", "近20日%", "RSI14"]],
                                ["股票", "代號", "提前階段", "提前觸發原因", "分析註記", "分析原因", "近期股利/資本事件"],
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    st.caption("依每日雷達與技術條件整理研究優先順序，不代表保證獲利。")
                options = hot.apply(lambda r: f"{r['代號']}｜{r['名稱']}", axis=1).tolist()
                selected_hot = st.selectbox("選一檔進一步分析", options, key="research_hot_stock")
                if selected_hot and st.button("分析這檔熱門股", key="analyze_hot_stock"):
                    code = selected_hot.split("｜", 1)[0]
                    snap = _technical_snapshot(f"{code}.TW")
                    st.session_state["hot_research_snapshot"] = snap
                    st.session_state["hot_research_code"] = code
                if selected_hot:
                    code = selected_hot.split("｜", 1)[0]
                    if st.session_state.get("hot_research_code") == code:
                        _render_snapshot(st.session_state.get("hot_research_snapshot", {}))
                        st.caption("熱門候選代表目前條件較值得研究，不代表保證獲利或自動買進。")
        else:
            st.info("尚未有雷達資料，請先按「更新熱門候選」。")
