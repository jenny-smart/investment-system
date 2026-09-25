from __future__ import annotations

import pandas as pd


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic indicators to OHLCV history; never invent missing market data."""
    out = df.copy().sort_index()
    close = pd.to_numeric(out["Close"], errors="coerce")
    for window in (5, 10, 20, 60):
        out[f"MA{window}"] = close.rolling(window).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["RSI14"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False).mean()
    return out


def backtest_ma_cross(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> dict:
    """Simple long-only close-to-close MA crossover backtest."""
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < slow + 2:
        return {"trades": 0, "return_pct": None, "max_drawdown_pct": None}

    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    position = (fast_ma > slow_ma).astype(float).shift(1).fillna(0)
    strategy = close.pct_change().fillna(0) * position
    equity = (1 + strategy).cumprod()
    drawdown = equity / equity.cummax() - 1
    entries = ((position == 1) & (position.shift(1, fill_value=0) == 0)).sum()
    return {
        "trades": int(entries),
        "return_pct": round((equity.iloc[-1] - 1) * 100, 2),
        "max_drawdown_pct": round(drawdown.min() * 100, 2),
    }


def portfolio_health(positions: pd.DataFrame) -> dict:
    """Calculate concentration only from supplied positions; does not mutate holdings."""
    required = {"symbol", "market_value"}
    if not required.issubset(positions.columns):
        raise ValueError("positions requires symbol and market_value")
    values = pd.to_numeric(positions["market_value"], errors="coerce").fillna(0).clip(lower=0)
    total = float(values.sum())
    if total <= 0:
        return {"total_market_value": 0.0, "largest_weight_pct": None, "top3_weight_pct": None}
    weights = values / total
    return {
        "total_market_value": total,
        "largest_weight_pct": round(float(weights.max() * 100), 2),
        "top3_weight_pct": round(float(weights.nlargest(3).sum() * 100), 2),
    }
