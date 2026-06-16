"""
CMC Agent Hub adapter — pulls live market data for strategy generation.
"""
import os
import urllib.request
import urllib.parse
import json
import time
from typing import Optional

CMC_BASE = "https://pro-api.coinmarketcap.com"


class CMCAdapter:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: dict = {}
        self._cache_ts: dict = {}
        self.cache_ttl = 60  # seconds

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{CMC_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        now = time.time()
        if url in self._cache and now - self._cache_ts.get(url, 0) < self.cache_ttl:
            return self._cache[url]
        req = urllib.request.Request(
            url, headers={"X-CMC_PRO_API_KEY": self.api_key, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        self._cache[url] = data
        self._cache_ts[url] = now
        return data

    def get_fear_and_greed(self) -> dict:
        """Current Fear & Greed index (0-100, Extreme Fear / Fear / Neutral / Greed / Extreme Greed)."""
        data = self._get("/v3/fear-and-greed/latest")
        fg = data["data"]
        return {
            "score": fg["value"],
            "label": fg["value_classification"],
            "updated": fg["update_time"],
        }

    def get_quote(self, symbol: str) -> dict:
        """Latest price quote for a symbol."""
        data = self._get("/v2/cryptocurrency/quotes/latest", {"symbol": symbol, "convert": "USDT"})
        for slug, entries in data["data"].items():
            info = entries[0] if isinstance(entries, list) else entries
            q = info["quote"]["USDT"]
            return {
                "symbol": symbol,
                "price": q["price"],
                "volume_24h": q["volume_24h"],
                "volume_change_24h": q["volume_change_24h"],
                "percent_change_1h": q["percent_change_1h"],
                "percent_change_24h": q["percent_change_24h"],
                "percent_change_7d": q["percent_change_7d"],
                "market_cap": q["market_cap"],
            }
        raise ValueError(f"Symbol not found: {symbol}")

    def get_ohlcv_daily(self, symbol: str, count: int = 365) -> list[dict]:
        """
        Historical daily OHLCV data via Binance public API (no key required).
        Falls back to CMC OHLCV if Binance unavailable.
        """
        pair = f"{symbol}USDT"
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={pair}&interval=1d&limit={count}"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = json.loads(r.read())
            return [
                {
                    "time": str(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                }
                for candle in raw
            ]
        except Exception:
            # Fallback: CMC OHLCV (requires Pro plan)
            data = self._get(
                "/v2/cryptocurrency/ohlcv/historical",
                {"symbol": symbol, "convert": "USDT", "count": count, "interval": "daily"},
            )
            quotes = data["data"]["quotes"]
            return [
                {
                    "time": q["time_open"],
                    "open": q["quote"]["USDT"]["open"],
                    "high": q["quote"]["USDT"]["high"],
                    "low": q["quote"]["USDT"]["low"],
                    "close": q["quote"]["USDT"]["close"],
                    "volume": q["quote"]["USDT"]["volume"],
                }
                for q in quotes
            ]

    def get_trending(self, limit: int = 10) -> list[dict]:
        """Trending tokens by CMC ranking."""
        data = self._get("/v1/cryptocurrency/trending/latest", {"limit": limit})
        return [
            {"symbol": t["symbol"], "name": t["name"], "rank": t["cmc_rank"]}
            for t in data.get("data", [])
        ]

    def get_global_metrics(self) -> dict:
        """Global market metrics: total market cap, BTC dominance, etc."""
        data = self._get("/v1/global-metrics/quotes/latest")
        q = data["data"]["quote"]["USD"]
        return {
            "total_market_cap": q["total_market_cap"],
            "total_volume_24h": q["total_volume_24h"],
            "btc_dominance": data["data"]["btc_dominance"],
            "eth_dominance": data["data"]["eth_dominance"],
            "active_cryptocurrencies": data["data"]["active_cryptocurrencies"],
        }
