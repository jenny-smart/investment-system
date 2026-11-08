import pandas as pd

from night_futures.hot_stocks import analyze, classify, pick_hot, turnover_frame


def test_turnover_and_pick():
    rows = [{"Code": f"{1000 + i}", "Name": f"S{i}", "ClosingPrice": "100", "TradeValue": str((i + 1) * 1e8)}
            for i in range(100)]
    rows += [{"Code": "0050", "Name": "ETF", "ClosingPrice": "150", "TradeValue": "9e12"}]  # 4 碼 ETF 也算普通股代碼
    rows += [{"Code": "00878", "Name": "ETF5", "ClosingPrice": "20", "TradeValue": "9e12"}]  # 5 碼排除
    prices = turnover_frame(rows)
    assert "00878" not in set(prices["代號"])
    inst = pd.DataFrame({"代號": ["1099", "1020"], "外資買賣超": [1, 1], "投信買賣超": [0, 0],
                         "三大法人買賣超": [-5_000_000, 50_000_000]})
    hot = pick_hot(prices, inst, n=20)
    assert len(hot) == 20
    assert "1020" not in set(hot["代號"])  # 成交金額不在前 80 名，法人再多也不選
    assert hot["熱門分數"].is_monotonic_decreasing


def test_classify_rules():
    assert classify(110, 100, 90, 60, 1000, 95)["建議"] == "買進"
    assert classify(110, 100, 90, 75, 1000, 95)["建議"] == "拉回再買"
    assert classify(110, 100, 90, 60, -1000, 95)["建議"] == "拉回再買"
    assert classify(110, 100, 90, 85, 1000, 95)["建議"] == "過熱減碼"
    assert classify(80, 90, 100, 30, 1000, 75)["建議"] == "賣出／避開"
    assert classify(101, 100, 105, 55, 1000, 95)["建議"] == "觀望偏多"
    assert classify(99, 100, 95, 55, 1000, 95)["建議"] == "觀望"
    buy = classify(110, 100, 90, 60, 1000, 104)
    assert buy["停損參考"] == 104 and buy["趨勢"] == "多頭"


def test_analyze_uptrend():
    close = pd.Series([100 + i * 0.5 + (i % 3) for i in range(80)], dtype=float)
    res = analyze("2330", pd.DataFrame({"Close": close}), 1_000_000)
    assert res["趨勢"] == "多頭"
    assert res["20日線"] < res["收盤價"]
    assert len(res["近20日走勢"]) == 20
