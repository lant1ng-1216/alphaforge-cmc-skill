"""Tests for feature engineering."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.features import ema, rsi, macd, volume_zscore, compute_features, latest_features


def make_ohlcv(n=100, base=100.0):
    import math
    candles = []
    for i in range(n):
        close = base + math.sin(i * 0.3) * 10 + i * 0.1
        candles.append({
            "time": str(i),
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": 1000 + i * 10,
        })
    return candles


def test_ema_length():
    prices = [float(i) for i in range(50)]
    result = ema(prices, 20)
    assert len(result) == len(prices)


def test_rsi_range():
    prices = [float(i) for i in range(30)]
    result = rsi(prices, 14)
    for v in result:
        if v is not None:
            assert 0 <= v <= 100


def test_macd_length():
    prices = [float(i + 1) for i in range(50)]
    result = macd(prices)
    assert len(result) == len(prices)


def test_compute_features():
    ohlcv = make_ohlcv(100)
    feat = compute_features(ohlcv)
    assert "ema_20" in feat
    assert "rsi_14" in feat
    assert "macd" in feat
    assert len(feat["ema_20"]) == 100


def test_latest_features():
    ohlcv = make_ohlcv(100)
    feat = compute_features(ohlcv)
    latest = latest_features(feat)
    assert "ema_20" in latest
    assert latest["ema_20"] is not None
    assert isinstance(latest["ema_20"], float)


if __name__ == "__main__":
    test_ema_length()
    test_rsi_range()
    test_macd_length()
    test_compute_features()
    test_latest_features()
    print("All feature tests passed.")
