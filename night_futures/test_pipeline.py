from night_futures.pipeline import (
    estimate_open,
    merge_history,
    parse_foreign_night,
    parse_fut_csv,
    parse_news_rss,
    summarize_sessions,
)

HEADER = ("交易日期,契約,到期月份(週別),開盤價,最高價,最低價,收盤價,漲跌價,漲跌%,成交量,結算價,"
          "未沖銷契約數,最後最佳買價,最後最佳賣價,歷史最高價,歷史最低價,是否因訊息面暫停交易,交易時段,價差對單式委託成交量")

CSV = "\n".join([
    HEADER,
    # 11/06（五）日盤
    "2026/11/06,TX,202611,27000,27200,26900,27100,100,0.37%,90000,27100,80000,27100,27101,28000,20000,,一般,",
    "2026/11/06,TX,202612,27050,27250,26950,27150,100,0.37%,9000,27150,10000,27150,27151,28000,20000,,一般,",
    "2026/11/06,TX,202611W2,27000,27200,26900,27100,100,0.37%,1000,-,-,27100,27101,28000,20000,,一般,",
    "2026/11/06,TX,202611/202612,50,50,50,50,-,-,500,-,-,-,-,-,-,,一般,",
    # 11/06 15:00～11/07 05:00 夜盤，期交所歸屬 11/09（一）
    "2026/11/09,TX,202611,27100,27400,27050,27370,270,1.00%,40000,-,-,27370,27371,28000,20000,,盤後,",
    "2026/11/09,TX,202612,27150,27450,27100,27420,270,1.00%,9000,-,-,27420,27421,28000,20000,,盤後,",
    "2026/11/09,TX,202611/202612,50,50,50,50,-,-,300,-,-,-,-,-,-,,盤後,",
    # 一個月份但成交量 0
    "2026/11/09,TX,202703,-,-,-,-,-,-,0,-,-,-,-,-,-,,盤後,",
])


def test_parse_and_ratio():
    rows = parse_fut_csv(CSV)
    assert len(rows) == 8
    nights = summarize_sessions(rows)
    assert len(nights) == 1
    n = nights[0]
    assert n["夜盤日期"] == "2026-11-09" and n["日盤日期"] == "2026-11-06"
    assert n["契約月份"] == "202611"
    # 價差單不算；週契約算
    assert n["日盤成交量"] == 100000
    assert n["夜盤成交量"] == 49000
    assert abs(n["夜盤量佔比"] - 49000 / 149000) < 1e-9
    assert n["夜盤漲跌點"] == 270
    assert abs(n["夜盤漲跌幅"] - 270 / 27100) < 1e-9


FOREIGN_HTML = """
<table>
<tr><td>序號</td><td>商品名稱</td><td>身份別</td><td>口數</td><td>契約金額</td><td>口數</td><td>契約金額</td><td>口數</td><td>契約金額</td></tr>
<tr><td>1</td><td>臺股期貨</td><td>自營商</td><td>1,049</td><td>9,673,710</td><td>1,241</td><td>11,435,527</td><td>-192</td><td>-1,761,817</td></tr>
<tr><td>投信</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
<tr><td> 外資 </td><td>18,377</td><td>169,314,897</td><td>18,759</td><td>172,818,006</td><td>-382</td><td>-3,503,109</td></tr>
<tr><td>2</td><td>電子期貨</td><td>自營商</td><td>18</td><td>212,060</td><td>37</td><td>436,084</td><td>-19</td><td>-224,024</td></tr>
<tr><td>外資</td><td>85</td><td>1,001,167</td><td>62</td><td>729,976</td><td>23</td><td>271,191</td></tr>
</table>
"""


def test_parse_foreign_night():
    f = parse_foreign_night(FOREIGN_HTML)
    assert f["淨額口數"] == -382
    assert f["淨額千元"] == -3503109
    assert f["多方口數"] == 18377
    assert parse_foreign_night(FOREIGN_HTML, "電子期貨")["淨額口數"] == 23


def test_estimate_open_and_history():
    night = summarize_sessions(parse_fut_csv(CSV))[0]
    quotes = [
        {"代號": "^TWII", "收盤": 27000.0, "漲跌幅": 0.0},
        {"代號": "^SOX", "收盤": 6000.0, "漲跌幅": 0.02},
        {"代號": "TSM", "收盤": 300.0, "漲跌幅": 0.03},
        {"代號": "TWD=X", "收盤": 30.0, "漲跌幅": 0.0},
        {"代號": "2330.TW", "收盤": 1500.0, "漲跌幅": 0.0},
    ]
    est = estimate_open(night, quotes, {"淨額口數": -382, "淨額千元": -3503109})
    assert est["方向"] == "開高"
    assert abs(est["預估開盤"] - 27000 * (1 + 270 / 27100)) < 1e-6
    assert abs(est["台積電ADR溢價"] - (300 * 30 / 5 / 1500 - 1)) < 1e-9
    assert any("外資夜盤" in s for s in est["依據"])

    hist = merge_history({"2026-11-05": {"夜盤日期": "2026-11-05", "外資夜盤多空淨額口數": "10"}},
                         [night], {"2026-11-09": {"淨額口數": -382, "淨額千元": -3503109}})
    assert [h["夜盤日期"] for h in hist] == ["2026-11-05", "2026-11-09"]
    assert hist[1]["外資夜盤多空淨額口數"] == -382


def test_parse_news_rss():
    xml = """<rss><channel>
    <item><title>台股夜盤大漲 - 經濟日報</title><link>https://example.com/a</link>
    <pubDate>Sun, 08 Nov 2026 22:00:00 GMT</pubDate><source url="x">經濟日報</source></item>
    </channel></rss>"""
    news = parse_news_rss(xml)
    assert news == [{"標題": "台股夜盤大漲", "來源": "經濟日報", "時間": "11/09 06:00", "連結": "https://example.com/a"}]


def test_pick_scenario():
    from night_futures.pipeline import pick_scenario
    hist = [0.30] * 25
    assert pick_scenario(100, 500, 0.35, hist)["名稱"] == "劇本一"
    assert pick_scenario(100, -500, 0.35, hist)["名稱"] == "劇本二"
    assert pick_scenario(-100, -500, 0.25, hist)["名稱"] == "劇本三"
    s4 = pick_scenario(-100, 500, 0.25, hist)
    assert s4["名稱"] == "劇本四" and s4["可信度"] == "可信度低"
    assert pick_scenario(100, 500, 0.35, hist)["可信度"] == "可信度高"
    assert pick_scenario(100, None, 0.35, hist)["編號"] is None
