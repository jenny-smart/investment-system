"""Richart 外幣活存匯率（賣外幣＝銀行買入價）。純 requests，不依賴 Streamlit，App 與排程共用。

頁面：https://richart.tw/TSDIB_RichartWeb/foreign-currency/demand-deposit
解析方式：把頁面轉成純文字，找到幣別（代碼或中文名）後，取後面落在合理區間的兩個匯率，
較小的就是「賣外幣」（銀行買入）價；只有一個數字時就用那個。
"""
from __future__ import annotations

import html
import re

RICHART_FX_URL = "https://richart.tw/TSDIB_RichartWeb/foreign-currency/demand-deposit"

# 幣別 → (頁面上可能出現的名稱, 合理匯率區間)；區間用來排除日期、利率等其他數字
RICHART_CURRENCIES: dict[str, tuple[tuple[str, ...], tuple[float, float]]] = {
    "USD": (("USD", "美元", "美金"), (20.0, 50.0)),
    "ZAR": (("ZAR", "南非幣", "南非"), (0.8, 4.0)),
    "CNY": (("CNY", "RMB", "人民幣"), (3.0, 7.0)),
    "JPY": (("JPY", "日圓", "日幣", "日元"), (0.1, 0.5)),
}
_NUMBER = re.compile(r"(?<![\d.])\d{1,3}\.\d{2,6}(?![\d.])")


def page_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", lambda m: " " + re.sub(r"<[^>]+>", " ", m.group(0)) + " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def parse_richart_rates(raw: str, window: int = 240) -> dict[str, float]:
    """回傳 {幣別: 賣外幣匯率}；找不到的幣別不放進結果。"""
    text = page_text(raw)
    rates: dict[str, float] = {}
    for code, (names, (low, high)) in RICHART_CURRENCIES.items():
        for name in names:
            for match in re.finditer(re.escape(name), text):
                chunk = text[match.end():match.end() + window]
                numbers = [float(n) for n in _NUMBER.findall(chunk) if low <= float(n) <= high][:2]
                if numbers:
                    rates[code] = min(numbers)
                    break
            if code in rates:
                break
    return rates


def fetch_richart_rates(timeout: float = 15) -> dict[str, float]:
    import requests
    response = requests.get(RICHART_FX_URL, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9",
    })
    response.raise_for_status()
    rates = parse_richart_rates(response.text)
    if not rates:
        raise RuntimeError(f"Richart 頁面找不到匯率（{len(response.text)} 字元）：{page_text(response.text)[:300]}")
    return rates


def debug_endpoints(raw: str, base: str = "https://richart.tw") -> None:
    """找不到匯率時，列出頁面與其 JS 引用的資料網址，方便找出匯率 API。"""
    import requests
    pattern = re.compile(r"""(?:url\s*[:=]\s*|\.(?:get|post|getJSON|ajax)\(\s*|fetch\(\s*|axios\.\w+\(\s*)['"`]([^'"`]+)['"`]""", re.I)
    print("== page endpoints ==")
    for hit in sorted(set(pattern.findall(raw))):
        print("  ", hit)
    print("== rate keywords in page ==")
    shown = 0
    for m in re.finditer(r"(?i)(rate|exchange|currency|匯率|buy|sell)", raw):
        snippet = raw[max(0, m.start() - 80):m.end() + 120].replace("\n", " ")
        if any(k in snippet for k in ("ajax", "url", "api", "fetch")) and shown < 40:
            print("  ...", snippet[:220])
            shown += 1
    scripts = re.findall(r"""<script[^>]+src=['"]([^'"]+)['"]""", raw)
    print("== scripts ==", scripts)
    for src in scripts:
        if src.startswith("http") and "richart" not in src:
            continue
        url = src if src.startswith("http") else base + ("" if src.startswith("/") else "/TSDIB_RichartWeb/") + src
        try:
            js = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text
        except Exception as exc:
            print("  ", url, "ERR", exc)
            continue
        hits = sorted(set(pattern.findall(js)))
        rate_hits = [h for h in hits if re.search(r"(?i)rate|fx|currency|exchange|RC\d|foreign", h)]
        if rate_hits:
            print("  ", url, rate_hits[:40])


if __name__ == "__main__":
    import requests
    page = requests.get(RICHART_FX_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
    try:
        print(parse_richart_rates(page) or "no rates parsed")
    finally:
        debug_endpoints(page)
