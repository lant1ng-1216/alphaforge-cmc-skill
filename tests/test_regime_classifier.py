"""Tests for market regime classifier."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.regime_classifier import classify_regime


def test_sentiment_overheated():
    feat = {"ema_20": 110.0, "ema_50": 100.0, "rsi_14": 78.0, "macd": {"histogram": 2.0},
            "volume_zscore": 1.2, "realized_volatility": 0.5, "rolling_high_20": 115.0, "atr_14": 3.0}
    result = classify_regime(feat, fear_greed=85, price_change_24h=3.0, price_change_7d=25.0)
    assert result.primary == "sentiment_overheated"
    assert result.confidence > 0


def test_panic_reversal():
    feat = {"ema_20": 80.0, "ema_50": 90.0, "rsi_14": 22.0, "macd": {"histogram": -3.0},
            "volume_zscore": 2.0, "realized_volatility": 0.9, "rolling_high_20": 100.0, "atr_14": 5.0}
    result = classify_regime(feat, fear_greed=15, price_change_24h=-8.0, price_change_7d=-25.0)
    assert result.primary == "panic_reversal"


def test_bullish_trend():
    feat = {"ema_20": 105.0, "ema_50": 100.0, "rsi_14": 62.0, "macd": {"histogram": 1.5},
            "volume_zscore": 1.0, "realized_volatility": 0.4, "rolling_high_20": 107.0, "atr_14": 3.0}
    result = classify_regime(feat, fear_greed=60, price_change_24h=2.0, price_change_7d=8.0)
    assert result.primary == "bullish_trend"
    assert result.confidence > 0.5


def test_high_volatility_chop():
    feat = {"ema_20": 100.0, "ema_50": 100.0, "rsi_14": 50.0, "macd": {"histogram": 0.0},
            "volume_zscore": 0.0, "realized_volatility": 1.2, "rolling_high_20": 102.0, "atr_14": 8.0}
    result = classify_regime(feat, fear_greed=45, price_change_24h=0.5, price_change_7d=1.0)
    assert result.primary == "high_volatility_chop"


if __name__ == "__main__":
    test_sentiment_overheated()
    test_panic_reversal()
    test_bullish_trend()
    test_high_volatility_chop()
    print("All regime classifier tests passed.")
