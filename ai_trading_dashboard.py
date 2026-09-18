from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False


DEFAULT_MARKET_WATCHLIST = [
    "0050.TW", "006208.TW", "2330.TW", "2317.TW", "2454.TW",
    "2382.TW", "3231.TW", "2308.TW", "2881.TW", "2603.TW",
]


@dataclass(frozen=True)
class Signal:
    ticker: str
    price: float
    signal: str
    score: int
    entry_low: float
    entry_high: float
    stop: float
    target: float
    rr: float
    rsi: float
    ma20: float
    ma60: float
    reason: str


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def normalize_tw_ticker(text: str) -> str:
    value = str(text or "").strip().upper()
    if not value:
        return ""
    if value.endswith(".TW") or value.endswith(".TWO"):
        return value
    if value.isdigit():
        return f"{value}.TW"
    return value


def extract_tw_holdings(enriched: pd.DataFrame) -> list[str]:
    if enriched is None or enriched.empty or "ticker" not in enriched.columns:
        return []
    view = enriched.copy()
    if "platform" in view.columns:
        view = view[view["platform"].astype(str).eq("台股")]
    tickers = []
    for raw in view["ticker"].dropna().tolist():
        ticker = normalize_tw_ticker(raw)
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def compute_indicators(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()
    df = history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    close = pd.to_numeric(df.get("Close"), errors="coerce")
    high = pd.to_numeric(df.get("High", close), errors="coerce")
    low = pd.to_numeric(df.get("Low", close), errors="coerce")
    df["MA20"] = close.rolling(20).mean()
    df["MA60"] = close.rolling(60).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI14"] = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["VOL20"] = pd.to_numeric(df.get("Volume"), errors="coerce").rolling(20).mean()
    return df


def build_signal(ticker: str, history: pd.DataFrame) -> Signal | None:
    df = compute_indicators(history)
    if len(df.dropna(subset=["Close"])) < 60:
        return None
    row = df.iloc[-1]
    price = _safe_float(row.get("Close"))
    ma20 = _safe_float(row.get("MA20"))
    ma60 = _safe_float(row.get("MA60"))
    rsi = _safe_float(row.get("RSI14"), 50.0)
    macd = _safe_float(row.get("MACD"))
    macd_signal = _safe_float(row.get("MACD_SIGNAL"))
    atr = max(_safe_float(row.get("ATR14")), price * 0.02)

    score = 0
    reasons = []
    if price > ma20:
        score += 1
        reasons.append("股價站上20日線")
    if ma20 > ma60:
        score += 2
        reasons.append("20日線高於60日線")
    if macd > macd_signal:
        score += 1
        reasons.append("MACD偏多")
    if 45 <= rsi <= 70:
        score += 1
        reasons.append("RSI位於中性偏強區")
    elif rsi > 75:
        score -= 1
        reasons.append("RSI偏熱")
    if price < ma60:
        score -= 2
        reasons.append("股價跌破60日線")

    recent_support = _safe_float(df["Low"].tail(20).min(), price - atr)
    support = max(recent_support, price - 2.0 * atr)
    stop = max(0.01, support - 0.5 * atr)
    risk = max(price - stop, atr)
    target = price + risk * 2
    entry_low = max(stop, min(price, ma20 if ma20 > 0 else price) - 0.25 * atr)
    entry_high = price + 0.25 * atr
    rr = (target - price) / max(price - stop, 0.01)

    if score >= 4:
        signal = "條件偏多"
    elif score >= 2:
        signal = "觀察"
    else:
        signal = "轉弱／等待"

    return Signal(
        ticker=ticker,
        price=price,
        signal=signal,
        score=score,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        target=target,
        rr=rr,
        rsi=rsi,
        ma20=ma20,
        ma60=ma60,
        reason="；".join(reasons) or "資料不足以形成明確訊號",
    )


@st.cache_data(ttl=900, show_spinner=False)
def download_history(tickers: tuple[str, ...], period: str = "1y") -> dict[str, pd.DataFrame]:
    if not HAS_YF or not tickers:
        return {}
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if not df.empty:
                out[ticker] = df
        except Exception:
            continue
    return out


def signals_dataframe(tickers: Iterable[str], histories: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        sig = build_signal(ticker, histories.get(ticker, pd.DataFrame()))
        if sig is None:
            continue
        rows.append({
            "代號": sig.ticker,
            "訊號": sig.signal,
            "分數": sig.score,
            "現價": sig.price,
            "觀察進場低": sig.entry_low,
            "觀察進場高": sig.entry_high,
            "停損參考": sig.stop,
            "目標參考": sig.target,
            "風報比": sig.rr,
            "RSI14": sig.rsi,
            "MA20": sig.ma20,
            "MA60": sig.ma60,
            "理由": sig.reason,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["分數", "風報比"], ascending=[False, False]).reset_index(drop=True)


def backtest_ma_cross(history: pd.DataFrame) -> dict[str, float]:
    df = compute_indicators(history).dropna(subset=["Close", "MA20", "MA60"]).copy()
    if len(df) < 80:
        return {}
    close = pd.to_numeric(df["Close"], errors="coerce")
    position = (df["MA20"] > df["MA60"]).astype(float).shift(1).fillna(0)
    daily = close.pct_change().fillna(0)
    strategy = daily * position
    equity = (1 + strategy).cumprod()
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    trades = int(((position.diff() > 0).fillna(False)).sum())
    return {
        "策略報酬": float(equity.iloc[-1] - 1),
        "持有報酬": float(close.iloc[-1] / close.iloc[0] - 1),
        "最大回撤": float(drawdown.min()),
        "交易次數": float(trades),
    }


def portfolio_risk_table(enriched: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    if enriched is None or enriched.empty or "台幣市值" not in enriched.columns:
        return pd.DataFrame(), {}
    view = enriched.copy()
    values = pd.to_numeric(view["台幣市值"], errors="coerce").fillna(0).clip(lower=0)
    total = float(values.sum())
    if total <= 0:
        return pd.DataFrame(), {}
    view["台幣市值"] = values
    view["權重"] = values / total
    group_col = "name" if "name" in view.columns else "ticker"
    rows = (
        view.groupby(group_col, dropna=False, as_index=False)
        .agg(台幣市值=("台幣市值", "sum"), 權重=("權重", "sum"))
        .sort_values("權重", ascending=False)
    )
    max_weight = float(rows["權重"].max()) if not rows.empty else 0.0
    top5 = float(rows["權重"].head(5).sum()) if not rows.empty else 0.0
    return rows, {
        "最大單一部位": max_weight,
        "前五大集中度": top5,
        "市場下跌20%估計損失": total * 0.20,
        "目前投資市值": total,
    }


def market_summary(signals: pd.DataFrame) -> str:
    if signals.empty:
        return "今日沒有足夠資料形成訊號。"
    strong = signals[signals["訊號"] == "條件偏多"]
    weak = signals[signals["訊號"] == "轉弱／等待"]
    top = signals.iloc[0]
    return (
        f"掃描 {len(signals)} 檔，{len(strong)} 檔符合偏多條件，{len(weak)} 檔偏弱或需等待。 "
        f"目前技術條件最高的是 {top['代號']}（分數 {int(top['分數'])}）。 "
        "訊號僅代表規則條件，不等於保證報酬；進場前仍需確認事件風險與部位大小。"
    )


def _render_news(ticker: str) -> None:
    st.markdown("#### 📰 最新事件")
    if not HAS_YF:
        st.info("目前無法讀取新聞。")
        return
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        items = []
    if not items:
        st.caption("目前沒有可用新聞。")
        return
    for item in items[:5]:
        content = item.get("content", item)
        title = content.get("title") or item.get("title") or "未命名新聞"
        provider = content.get("provider", {}) if isinstance(content.get("provider"), dict) else {}
        source = provider.get("displayName") or item.get("publisher") or ""
        published = content.get("pubDate") or ""
        st.write(f"• {title}" + (f" — {source}" if source else "") + (f" ({published[:10]})" if published else ""))


def render_ai_trading_dashboard(enriched: pd.DataFrame) -> None:
    st.subheader("🤖 AI 交易研究")
    st.caption("固定規則＋即時市場資料；用來產生研究訊號、回測與風險檢查，不自動下單。")

    holdings = extract_tw_holdings(enriched)
    default_codes = holdings[:20] if holdings else DEFAULT_MARKET_WATCHLIST
    raw = st.text_input(
        "掃描股票（以逗號分隔）",
        value=", ".join(t.replace(".TW", "").replace(".TWO", "") for t in default_codes),
        key="ai_trade_watchlist",
    )
    tickers = []
    for token in raw.replace("，", ",").split(","):
        ticker = normalize_tw_ticker(token)
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    tickers = tickers[:30]

    if st.button("🔄 重新掃描", key="refresh_ai_trading"):
        download_history.clear()

    with st.spinner("讀取市場資料…"):
        histories = download_history(tuple(tickers))
    signals = signals_dataframe(tickers, histories)

    st.markdown("### 今日摘要")
    st.info(market_summary(signals))

    if signals.empty:
        st.warning("目前沒有足夠的歷史價格資料。")
        return

    st.markdown("### 交易點子")
    st.dataframe(
        signals,
        use_container_width=True,
        hide_index=True,
        column_config={
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "觀察進場低": st.column_config.NumberColumn(format="%.2f"),
            "觀察進場高": st.column_config.NumberColumn(format="%.2f"),
            "停損參考": st.column_config.NumberColumn(format="%.2f"),
            "目標參考": st.column_config.NumberColumn(format="%.2f"),
            "風報比": st.column_config.NumberColumn(format="%.2f"),
            "RSI14": st.column_config.NumberColumn(format="%.1f"),
            "MA20": st.column_config.NumberColumn(format="%.2f"),
            "MA60": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    selected = st.selectbox("個股深入分析", signals["代號"].tolist(), key="ai_trade_selected")
    selected_row = signals[signals["代號"] == selected].iloc[0]
    hist = histories.get(selected, pd.DataFrame())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("訊號", selected_row["訊號"])
    c2.metric("RSI14", f"{selected_row['RSI14']:.1f}")
    c3.metric("風報比", f"{selected_row['風報比']:.2f}")
    c4.metric("技術分數", f"{int(selected_row['分數'])}")
    st.caption(selected_row["理由"])

    if not hist.empty:
        ind = compute_indicators(hist)
        chart_cols = [c for c in ["Close", "MA20", "MA60"] if c in ind.columns]
        if chart_cols:
            st.line_chart(ind[chart_cols].tail(120), use_container_width=True)

    bt = backtest_ma_cross(hist)
    st.markdown("#### 🧪 MA20 / MA60 回測")
    if bt:
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("策略報酬", f"{bt['策略報酬']:.1%}")
        b2.metric("持有報酬", f"{bt['持有報酬']:.1%}")
        b3.metric("最大回撤", f"{bt['最大回撤']:.1%}")
        b4.metric("交易次數", f"{int(bt['交易次數'])}")
    else:
        st.caption("歷史資料不足，暫時無法回測。")

    _render_news(selected)

    st.markdown("### 🛡️ 投資組合風險")
    risk_table, risk = portfolio_risk_table(enriched)
    if risk:
        r1, r2, r3 = st.columns(3)
        r1.metric("最大單一部位", f"{risk['最大單一部位']:.1%}")
        r2.metric("前五大集中度", f"{risk['前五大集中度']:.1%}")
        r3.metric("若整體下跌20%", f"-NT${risk['市場下跌20%估計損失']:,.0f}")
        st.dataframe(
            risk_table.head(20),
            use_container_width=True,
            hide_index=True,
            column_config={"權重": st.column_config.NumberColumn(format="%.2%")},
        )
    else:
        st.caption("目前沒有可計算的投資組合市值。")

    st.markdown("### 📓 交易紀錄")
    st.caption("先用本次工作階段紀錄，避免新增資料表而影響現有 Supabase；之後可再升級成永久紀錄。")
    if "ai_trade_log" not in st.session_state:
        st.session_state.ai_trade_log = []
    with st.form("ai_trade_log_form"):
        side = st.selectbox("動作", ["買進", "賣出", "觀察"])
        result = st.text_input("結果／備註")
        submitted = st.form_submit_button("加入紀錄")
        if submitted:
            st.session_state.ai_trade_log.append({
                "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "代號": selected,
                "動作": side,
                "參考價": float(selected_row["現價"]),
                "當時訊號": selected_row["訊號"],
                "備註": result,
            })
    if st.session_state.ai_trade_log:
        st.dataframe(pd.DataFrame(st.session_state.ai_trade_log), use_container_width=True, hide_index=True)
