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
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"

# Module-level cache for the full symbol list — it rarely changes and is
# expensive to refetch, so we share it across CMCAdapter instances/requests.
_SYMBOL_SET_CACHE: dict = {"symbols": None, "ts": 0.0}
_SYMBOL_SET_TTL = 6 * 3600  # 6 hours


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

    def get_symbol_set(self) -> set:
        """
        All active CMC ticker symbols (uppercase), used to validate a
        natural-language asset guess before spending a get_quote call on it.
        Cached for _SYMBOL_SET_TTL since the listing changes infrequently.
        """
        now = time.time()
        cached = _SYMBOL_SET_CACHE["symbols"]
        if cached is not None and now - _SYMBOL_SET_CACHE["ts"] < _SYMBOL_SET_TTL:
            return cached
        data = self._get("/v1/cryptocurrency/map", {"listing_status": "active", "limit": 5000})
        symbols = {item["symbol"].upper() for item in data.get("data", [])}
        _SYMBOL_SET_CACHE["symbols"] = symbols
        _SYMBOL_SET_CACHE["ts"] = now
        return symbols

    def get_quote(self, symbol: str) -> dict:
        """Latest price quote for a symbol."""
        data = self._get("/v2/cryptocurrency/quotes/latest", {"symbol": symbol, "convert": "USDT"})
        for slug, entries in data["data"].items():
            info = entries[0] if isinstance(entries, list) else entries
            q = info["quote"]["USDT"]
            return {
                "symbol": symbol,
                "cmc_id": info.get("id"),
                "price": q["price"],
                "volume_24h": q["volume_24h"],
                "volume_change_24h": q["volume_change_24h"],
                "percent_change_1h": q["percent_change_1h"],
                "percent_change_24h": q["percent_change_24h"],
                "percent_change_7d": q["percent_change_7d"],
                "market_cap": q["market_cap"],
            }
        raise ValueError(f"Symbol not found: {symbol}")

    def _mcp_call(self, tool_name: str, arguments: dict = None) -> Optional[dict]:
        """
        Call a tool on the CMC Data MCP server (https://mcp.coinmarketcap.com/mcp).
        This is a plain JSON-RPC-over-HTTP POST — no session handshake or SSE
        framing required in practice, so no MCP SDK dependency is needed.
        Returns None on any failure so callers can degrade gracefully (this is
        a supplementary live cross-check, not a dependency the core pipeline
        needs to function).
        """
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }).encode()
        req = urllib.request.Request(
            CMC_MCP_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-CMC-MCP-API-KEY": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                envelope = json.loads(r.read())
            text = envelope["result"]["content"][0]["text"]
            return json.loads(text)
        except Exception:
            return None

    def get_technical_analysis_live(self, cmc_id) -> Optional[dict]:
        """
        Official CMC-computed technical analysis (EMA/SMA/MACD/RSI) for a
        given CMC numeric id, via the Data MCP. Used as an independent live
        cross-check against AlphaForge's own feature engineering — not as the
        backtester's data source, since this is a point-in-time snapshot, not
        a historical series.
        """
        if not cmc_id:
            return None
        return self._mcp_call("get_crypto_technical_analysis", {"id": str(cmc_id)})

    def get_derivatives_snapshot_live(self) -> Optional[dict]:
        """
        Market-wide derivatives snapshot (funding rate, open interest, BTC
        liquidations) via the Data MCP. This is aggregate/market-wide, not
        per-asset, so it's used as a leverage/crowding context signal rather
        than a per-asset funding_rate_zscore replacement.
        """
        return self._mcp_call("get_global_crypto_derivatives_metrics")

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
            # Fallback: CMC OHLCV historical (used when Binance is unreachable,
            # e.g. blocked from a cloud/serverless IP range). CMC returns a LIST
            # per symbol since multiple tokens can share the same ticker
            # (impersonators, delisted duplicates) — same shape quirk as
            # get_quote's v2 response. Pick the first entry that actually has
            # quote history; copycat entries typically come back with [].
            data = self._get(
                "/v2/cryptocurrency/ohlcv/historical",
                {"symbol": symbol, "convert": "USDT", "count": count, "interval": "daily"},
            )
            entries = data["data"].get(symbol) or data["data"].get(symbol.upper()) or []
            if isinstance(entries, dict):
                entries = [entries]
            quotes = next((e["quotes"] for e in entries if e.get("quotes")), None)
            if not quotes:
                raise ValueError(f"No CMC OHLCV history found for symbol: {symbol}")
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
