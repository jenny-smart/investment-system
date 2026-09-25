import pandas as pd

from stock_radar.research import add_technical_indicators, backtest_ma_cross, portfolio_health


def test_indicators_preserve_input_and_add_columns():
    src = pd.DataFrame({"Close": range(1, 81)})
    out = add_technical_indicators(src)
    assert "MA20" in out and "RSI14" in out and "MACD" in out
    assert "MA20" not in src


def test_backtest_short_history_returns_no_fake_numbers():
    result = backtest_ma_cross(pd.DataFrame({"Close": [1, 2, 3]}))
    assert result["trades"] == 0
    assert result["return_pct"] is None


def test_portfolio_health_handles_empty_and_concentration():
    empty = portfolio_health(pd.DataFrame({"symbol": [], "market_value": []}))
    assert empty["largest_weight_pct"] is None
    result = portfolio_health(pd.DataFrame({"symbol": ["A", "B"], "market_value": [75, 25]}))
    assert result["largest_weight_pct"] == 75.0
