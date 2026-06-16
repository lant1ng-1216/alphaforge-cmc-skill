"""
Feature engineering — converts OHLCV + CMC data into quantitative signals.
"""
import math
from typing import Optional


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def ema(prices: list[float], period: int) -> list[float]:
    if not prices:
        return []
    k = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result


def rsi(prices: list[float], period: int = 14) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * period
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    for i in range(period, len(prices)):
        if i > period:
            diff = prices[i] - prices[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
        result.append(100 - 100 / (1 + rs))
    return result


def macd(prices: list[float], fast=12, slow=26, signal=9) -> list[dict]:
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    return [
        {"macd": m, "signal": s, "histogram": m - s}
        for m, s in zip(macd_line, signal_line)
    ]


def volume_zscore(volumes: list[float], window: int = 20) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * (window - 1)
    for i in range(window - 1, len(volumes)):
        window_vols = volumes[i - window + 1 : i + 1]
        m = _mean(window_vols)
        s = _std(window_vols)
        result.append((volumes[i] - m) / s if s > 0 else 0.0)
    return result


def realized_volatility(closes: list[float], window: int = 14) -> list[Optional[float]]:
    """Annualized realized volatility (log returns std * sqrt(365))."""
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    result: list[Optional[float]] = [None] * window
    for i in range(window, len(log_returns) + 1):
        window_ret = log_returns[i - window : i]
        result.append(_std(window_ret) * math.sqrt(365))
    return result


def compute_features(ohlcv: list[dict]) -> dict:
    """
    Compute all technical features from OHLCV list.
    Returns a dict of feature arrays aligned to the OHLCV length.
    """
    closes = [c["close"] for c in ohlcv]
    volumes = [c["volume"] for c in ohlcv]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    macd_vals = macd(closes)
    vol_z = volume_zscore(volumes, 20)
    rv = realized_volatility(closes, 14)

    # Rolling 20-bar high for breakout detection
    rolling_high_20 = [None] * 19 + [
        max(closes[i - 19 : i + 1]) for i in range(19, len(closes))
    ]

    # ATR
    atrs: list[Optional[float]] = [None]
    for i in range(1, len(ohlcv)):
        h, l, pc = ohlcv[i]["high"], ohlcv[i]["low"], ohlcv[i - 1]["close"]
        atrs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr14: list[Optional[float]] = [None] * 14
    atr_window = [a for a in atrs[1:15] if a is not None]
    cur_atr: float = _mean(atr_window) if atr_window else 0.0
    for i in range(15, len(atrs)):
        if atrs[i] is not None:
            cur_atr = (cur_atr * 13 + atrs[i]) / 14
        atr14.append(cur_atr)

    return {
        "ema_20": ema20,
        "ema_50": ema50,
        "rsi_14": rsi14,
        "macd": macd_vals,
        "volume_zscore": vol_z,
        "realized_volatility": rv,
        "rolling_high_20": rolling_high_20,
        "atr_14": atr14,
    }


def latest_features(features: dict) -> dict:
    """Extract the most recent value for each feature."""
    result = {}
    for k, v in features.items():
        if isinstance(v, list) and v:
            val = next((x for x in reversed(v) if x is not None), None)
            result[k] = val
        else:
            result[k] = v
    return result
