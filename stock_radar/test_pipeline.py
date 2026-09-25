import pandas as pd

from stock_radar.pipeline import _price_frame, _score


def test_price_frame_filters_non_stock_rows():
    rows = [
        {"Code": "2330", "Name": "台積電", "ClosingPrice": "1000", "Change": "10", "TradeVolume": "1,500,000"},
        {"Code": "IX0001", "Name": "指數", "ClosingPrice": "20000", "Change": "1", "TradeVolume": "0"},
    ]
    df = _price_frame(rows)
    assert df["代號"].tolist() == ["2330"]
    assert df.iloc[0]["漲跌幅%"] > 0


def test_score_handles_missing_optional_data():
    df = pd.DataFrame([{"代號": "2330", "名稱": "台積電", "收盤價": 1000, "漲跌幅%": 1.0, "成交股數": 2_000_000}])
    ranked = _score(df)
    assert int(ranked.iloc[0]["雷達分數"]) == 2
    assert "量能" in ranked.iloc[0]["入選原因"]
