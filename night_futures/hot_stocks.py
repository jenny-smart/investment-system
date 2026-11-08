"""近期熱門台股 20 檔：漲跌趨勢＋買進／賣出建議（規則式技術面，每天早上跟夜盤一起更新）。

挑選：證交所前一交易日上市普通股，成交金額前 80 名中，
      依「成交金額排名 ＋ 三大法人買賣超金額排名」各半加權，取前 20。
趨勢：收盤 > 20 日線 > 60 日線＝多頭；收盤 < 20 日線 < 60 日線＝空頭；其餘＝盤整。
建議（依序判斷，先符合先用）：
  RSI ≥ 80                              → 過熱減碼（分批獲利了結）
  空頭且 RSI ≤ 20                        → 超跌勿追殺（等反彈再減碼）
  空頭                                   → 賣出／避開
  多頭＋法人買超＋RSI < 70               → 買進
  多頭（RSI 70–80 或法人賣超）           → 拉回再買（續抱）
  盤整且站上 20 日線＋法人買超           → 觀望偏多
  其餘                                   → 觀望
關鍵價位：偏多（買進／拉回再買／觀望偏多）＝停損，20 日線與近 20 日低點較高者，跌破出場；
          其他＝壓力，20 日線，站回才轉觀望。
只是統計規則，不是投資建議。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

import requests

from stock_radar.pipeline import HEADERS, INST_URL, PRICE_URL, _get_json, _institution_frame, _num, _pick

T86_RWD_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

TOP_TURNOVER = 80
PICK = 20


def turnover_frame(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        code = str(_pick(r, "Code", "證券代號") or "").strip()
        if not code.isdigit() or len(code) != 4:  # 普通股（排除 ETF 00xx 以外的 5～6 碼）
            continue
        close = _num(_pick(r, "ClosingPrice", "收盤價"))
        value = _num(_pick(r, "TradeValue", "成交金額"))
        if not close or close <= 0 or not value:
            continue
        out.append({"代號": code, "名稱": str(_pick(r, "Name", "證券名稱") or "").strip(),
                    "收盤價": close, "成交金額": value})
    return pd.DataFrame(out)


def institution_rows(today) -> list[dict]:
    """三大法人買賣超：先用 OpenAPI，失敗或空的就用證交所網站 rwd 版往前找最近一個交易日。"""
    try:
        rows = _get_json(INST_URL)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        print(f"WARN 三大法人 OpenAPI 抓不到，改用證交所網站：{exc}")
    from datetime import timedelta
    for back in range(0, 8):
        day = (today - timedelta(days=back)).strftime("%Y%m%d")
        try:
            resp = requests.get(T86_RWD_URL, params={"date": day, "selectType": "ALLBUT0999", "response": "json"},
                                headers=HEADERS, timeout=45)
            payload = resp.json()
        except Exception:  # noqa: BLE001
            continue
        if payload.get("stat") == "OK" and payload.get("data"):
            fields = [str(f).strip() for f in payload["fields"]]
            return [dict(zip(fields, row)) for row in payload["data"]]
    return []


def pick_hot(prices: pd.DataFrame, inst: pd.DataFrame, n: int = PICK) -> pd.DataFrame:
    df = prices.sort_values("成交金額", ascending=False).head(TOP_TURNOVER).copy()
    if not inst.empty:
        df = df.merge(inst, on="代號", how="left")
    for col in ["外資買賣超", "投信買賣超", "三大法人買賣超"]:
        if col not in df:
            df[col] = pd.NA
    df["法人買賣超金額"] = pd.to_numeric(df["三大法人買賣超"], errors="coerce") * df["收盤價"]
    df["熱門分數"] = (df["成交金額"].rank(pct=True) * 0.5
                    + df["法人買賣超金額"].rank(pct=True).fillna(0) * 0.5)
    return df.sort_values("熱門分數", ascending=False).head(n).reset_index(drop=True)


def rsi(close: pd.Series, period: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    if pd.isna(gain.iloc[-1]) or pd.isna(loss.iloc[-1]):
        return None
    if loss.iloc[-1] == 0:
        return 100.0
    return float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1]))


def classify(close: float, ma20: float | None, ma60: float | None, rsi_v: float | None,
             inst_net: float | None, low20: float | None) -> dict[str, Any]:
    if ma20 is None or ma60 is None:
        trend = "資料不足"
    elif close > ma20 > ma60:
        trend = "多頭"
    elif close < ma20 < ma60:
        trend = "空頭"
    else:
        trend = "盤整"
    inst_buy = inst_net is not None and inst_net > 0
    why = []
    if ma20 is not None:
        why.append(f"{'站上' if close >= ma20 else '跌破'} 20 日線 {ma20:,.1f}")
    if rsi_v is not None:
        why.append(f"RSI {rsi_v:.0f}")
    if inst_net is not None:
        why.append(f"法人{'買超' if inst_net > 0 else '賣超'} {abs(inst_net) / 1000:,.0f} 張")

    if rsi_v is not None and rsi_v >= 80:
        action = "過熱減碼"
    elif trend == "空頭" and rsi_v is not None and rsi_v <= 20:
        action = "超跌勿追殺"
    elif trend == "空頭":
        action = "賣出／避開"
    elif trend == "多頭" and inst_buy and (rsi_v is None or rsi_v < 70):
        action = "買進"
    elif trend == "多頭":
        action = "拉回再買"
    elif trend == "盤整" and ma20 is not None and close >= ma20 and inst_buy:
        action = "觀望偏多"
    else:
        action = "觀望"

    if action in {"買進", "拉回再買", "觀望偏多"} and ma20 is not None:
        level, kind = (max(ma20, low20) if low20 is not None else ma20), "停損"
    else:
        level, kind = ma20, "壓力"
    return {"趨勢": trend, "建議": action, "關鍵價位": level, "價位類型": kind, "理由": "，".join(why)}


def analyze(code: str, hist: pd.DataFrame, inst_net: float | None) -> dict[str, Any]:
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if len(close) < 2:
        return {"趨勢": "資料不足", "建議": "觀望", "理由": "查不到股價歷史"}
    last = float(close.iloc[-1])
    ma = lambda n: float(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None
    chg = lambda n: float(last / close.iloc[-1 - n] - 1) if len(close) > n else None
    low20 = float(close.tail(20).min())
    out = {"收盤價": last, "1日漲跌": chg(1), "5日漲跌": chg(5), "20日漲跌": chg(20),
           "5日線": ma(5), "20日線": ma(20), "60日線": ma(60), "RSI": rsi(close)}
    out.update(classify(last, out["20日線"], out["60日線"], out["RSI"], inst_net, low20))
    out["近20日走勢"] = [round(float(v), 2) for v in close.tail(20)]
    return out


def build_hot_stocks() -> list[dict[str, Any]]:
    import yfinance as yf

    prices = turnover_frame(_get_json(PRICE_URL))
    from night_futures.pipeline import tw_now
    inst = _institution_frame(institution_rows(tw_now()))
    if inst.empty:
        print("WARN 三大法人買賣超抓不到，熱門股只依成交金額排名")
    hot = pick_hot(prices, inst)
    symbols = [f"{c}.TW" for c in hot["代號"]]
    raw = yf.download(symbols, period="6mo", interval="1d", auto_adjust=False, progress=False, group_by="ticker")
    out = []
    for i, r in hot.iterrows():
        sym = f"{r['代號']}.TW"
        item = {"排名": i + 1, "代號": r["代號"], "名稱": r["名稱"],
                "成交金額億": round(float(r["成交金額"]) / 1e8, 1),
                "外資買賣超張": None if pd.isna(r["外資買賣超"]) else round(float(r["外資買賣超"]) / 1000),
                "投信買賣超張": None if pd.isna(r["投信買賣超"]) else round(float(r["投信買賣超"]) / 1000)}
        inst_net = None if pd.isna(r["三大法人買賣超"]) else float(r["三大法人買賣超"])
        try:
            hist = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
            item.update(analyze(r["代號"], hist, inst_net))
        except Exception as exc:  # noqa: BLE001
            item.update({"收盤價": r["收盤價"], "趨勢": "資料不足", "建議": "觀望", "理由": f"股價歷史抓不到：{exc}"[:80]})
        out.append(item)
    return out
