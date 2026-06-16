"""
Market Regime Classifier — the core differentiator of AlphaForge.
Detects market state from technical + sentiment + derivatives features.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RegimeResult:
    primary: str
    secondary: list[str]
    confidence: float  # 0.0 - 1.0
    signals: dict      # raw signal values used for classification
    explanation: str


REGIME_LABELS = {
    "bullish_trend": "Bullish Trend",
    "bearish_trend": "Bearish Trend",
    "low_volatility_accumulation": "Low Volatility Accumulation",
    "high_volatility_chop": "High Volatility Chop",
    "panic_reversal": "Panic / Extreme Fear Reversal",
    "sentiment_overheated": "Sentiment Overheated",
    "derivatives_crowded_long": "Derivatives Crowded Long",
    "derivatives_crowded_short": "Derivatives Crowded Short",
    "neutral": "Neutral / Unclear",
}


def classify_regime(
    feat: dict,
    fear_greed: int,
    price_change_24h: float,
    price_change_7d: float,
    volume_change_24h: Optional[float] = None,
) -> RegimeResult:
    """
    Classify market regime from latest feature values + CMC sentiment data.

    Args:
        feat: dict from latest_features()
        fear_greed: CMC Fear & Greed score (0-100)
        price_change_24h: 24h price change %
        price_change_7d: 7d price change %
        volume_change_24h: 24h volume change % (optional)
    """
    ema20 = feat.get("ema_20")
    ema50 = feat.get("ema_50")
    rsi14 = feat.get("rsi_14")
    macd_hist = feat.get("macd", {}).get("histogram") if isinstance(feat.get("macd"), dict) else None
    vol_z = feat.get("volume_zscore")
    rv = feat.get("realized_volatility")

    signals = {
        "ema_20": ema20,
        "ema_50": ema50,
        "rsi_14": rsi14,
        "macd_histogram": macd_hist,
        "volume_zscore": vol_z,
        "realized_volatility": rv,
        "fear_greed_score": fear_greed,
        "price_change_24h": price_change_24h,
        "price_change_7d": price_change_7d,
        "volume_change_24h": volume_change_24h,
    }

    secondary = []

    # --- Regime scoring ---

    # Sentiment overheated (hard gate — check first)
    if fear_greed > 80 and rsi14 is not None and rsi14 > 72:
        primary = "sentiment_overheated"
        confidence = min(1.0, (fear_greed - 80) / 20 * 0.5 + (rsi14 - 72) / 28 * 0.5)
        explanation = (
            f"Fear & Greed at {fear_greed} (Extreme Greed) combined with RSI {rsi14:.1f} "
            "signals the market is overheated. Momentum entries carry high reversal risk."
        )
        if price_change_7d > 20:
            secondary.append("extended_rally")
        return RegimeResult(primary, secondary, confidence, signals, explanation)

    # Panic reversal (extreme fear zone)
    if fear_greed < 20 and rsi14 is not None and rsi14 < 35:
        primary = "panic_reversal"
        confidence = min(1.0, (20 - fear_greed) / 20 * 0.5 + (35 - rsi14) / 35 * 0.5)
        explanation = (
            f"Fear & Greed at {fear_greed} (Extreme Fear) with RSI {rsi14:.1f} suggests "
            "capitulation conditions. Contrarian reversal setups may emerge."
        )
        return RegimeResult(primary, secondary, confidence, signals, explanation)

    # Bullish trend
    bullish_score = 0
    if ema20 and ema50 and ema20 > ema50:
        bullish_score += 2
    if rsi14 and 50 <= rsi14 <= 72:
        bullish_score += 1
    if macd_hist and macd_hist > 0:
        bullish_score += 1
    if vol_z and vol_z > 0.3:
        bullish_score += 1
    if price_change_7d > 5:
        bullish_score += 1
    if fear_greed > 50:
        secondary.append("moderate_sentiment")

    # Bearish trend
    bearish_score = 0
    if ema20 and ema50 and ema20 < ema50:
        bearish_score += 2
    if rsi14 and rsi14 < 45:
        bearish_score += 1
    if macd_hist and macd_hist < 0:
        bearish_score += 1
    if price_change_7d < -5:
        bearish_score += 1

    # Low volatility accumulation
    low_vol = rv is not None and rv < 0.4 and abs(price_change_7d) < 5

    # High volatility chop
    high_vol = rv is not None and rv > 0.8

    if high_vol:
        primary = "high_volatility_chop"
        confidence = min(1.0, (rv - 0.8) / 0.4)
        explanation = (
            f"Realized volatility at {rv:.2f} indicates a choppy, high-noise environment. "
            "Most trend-following strategies underperform in this regime."
        )
        return RegimeResult(primary, secondary, confidence, signals, explanation)

    if bullish_score >= bearish_score and bullish_score >= 3:
        primary = "bullish_trend"
        confidence = min(1.0, bullish_score / 6)
        if low_vol:
            secondary.append("low_volatility_accumulation")
        explanation = (
            f"Price is above EMA20 > EMA50, MACD positive, RSI in healthy range ({rsi14:.1f}). "
            f"7d return {price_change_7d:+.1f}%. Trend momentum conditions are met."
        )
    elif bearish_score > bullish_score and bearish_score >= 3:
        primary = "bearish_trend"
        confidence = min(1.0, bearish_score / 5)
        explanation = (
            f"Price below EMA20 < EMA50, MACD negative, RSI {rsi14:.1f}. "
            f"7d return {price_change_7d:+.1f}%. Bearish trend in effect."
        )
    elif low_vol:
        primary = "low_volatility_accumulation"
        confidence = 0.6
        explanation = (
            "Market is range-bound with low realized volatility. "
            "Accumulation phase — watch for breakout setup."
        )
    else:
        primary = "neutral"
        confidence = 0.4
        explanation = "No dominant regime detected. Mixed signals — reduce position size."

    return RegimeResult(primary, secondary, round(confidence, 2), signals, explanation)
