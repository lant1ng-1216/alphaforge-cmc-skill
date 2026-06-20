"""
BSC Ecosystem Adapter — fetches BNB Chain-native signals.

Provides on-chain and DEX data specific to the BNB Chain ecosystem, including
PancakeSwap DEX activity and BSC network health metrics. These signals are
layered on top of the standard CMC data pipeline when the target asset is a
BSC-native token (BNB, CAKE, etc.).

Data sources used here require no additional API keys:
- BSC public JSON-RPC (bsc-dataseed.binance.org) — block stats
- BscScan public API (no key for basic endpoints)
- CMC DEX data via existing CMC API key
"""
import json
import urllib.request
import urllib.error
from typing import Optional

BSC_RPC = "https://bsc-dataseed.binance.org"
PANCAKESWAP_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v3-bsc"

BSC_NATIVE_ASSETS = {
    "BNB", "CAKE", "BUSD", "BSW", "XVS", "ALPACA", "BAKE", "AUTO",
    "BELT", "BURGER", "DODO", "EPS", "FOR", "LINA", "MBOX", "NULS",
    "PHA", "SFP", "SFUND", "TLOS", "TWT", "VAI", "WEX",
}


def is_bsc_native(asset: str) -> bool:
    return asset.upper() in BSC_NATIVE_ASSETS


def _rpc_call(method: str, params: list, timeout: int = 8) -> Optional[dict]:
    payload = json.dumps({
        "jsonrpc": "2.0", "method": method, "params": params, "id": 1
    }).encode()
    req = urllib.request.Request(
        BSC_RPC,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "AlphaForge/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def get_bsc_block_stats() -> dict:
    """
    Fetch current BSC block number and estimate recent block time (TPS proxy).
    Uses two sequential RPC calls to measure elapsed time over a window of blocks.
    Returns a dict with block_number, estimated_tps, and a health label.
    """
    result = {"available": False}
    try:
        resp = _rpc_call("eth_blockNumber", [])
        if not resp or "result" not in resp:
            return result
        latest_block = int(resp["result"], 16)

        # Fetch the latest block to get its timestamp
        block_resp = _rpc_call("eth_getBlockByNumber", [hex(latest_block), False])
        if not block_resp or "result" not in block_resp or not block_resp["result"]:
            return result
        latest_ts = int(block_resp["result"]["timestamp"], 16)

        # Fetch block 100 blocks back to compute average block time
        old_block = latest_block - 100
        old_resp = _rpc_call("eth_getBlockByNumber", [hex(old_block), False])
        if not old_resp or "result" not in old_resp or not old_resp["result"]:
            return result
        old_ts = int(old_resp["result"]["timestamp"], 16)

        elapsed = latest_ts - old_ts
        if elapsed <= 0:
            return result

        avg_block_time = elapsed / 100
        # BSC normal block time ≈ 3s; TPS estimate from tx count would need
        # per-block tx data. We use block time as a network health proxy.
        health = "normal"
        if avg_block_time > 4.0:
            health = "congested"
        elif avg_block_time < 2.5:
            health = "fast"

        result = {
            "available": True,
            "block_number": latest_block,
            "avg_block_time_sec": round(avg_block_time, 2),
            "network_health": health,
        }
    except Exception:
        pass
    return result


def get_pancakeswap_activity(cmc_api_key: str) -> dict:
    """
    Fetch PancakeSwap DEX metrics via CMC's exchange/market endpoint.
    Uses the standard CMC API key — no extra credentials needed.
    Returns 24h volume and a relative activity label vs typical ranges.
    """
    result = {"available": False}
    try:
        url = (
            "https://pro-api.coinmarketcap.com/v1/exchange/quotes/latest"
            "?slug=pancakeswap&convert=USD"
        )
        req = urllib.request.Request(
            url,
            headers={
                "X-CMC_PRO_API_KEY": cmc_api_key,
                "Accept": "application/json",
                "User-Agent": "AlphaForge/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())

        # Navigate the CMC exchange response structure
        exchange_data = data.get("data", {})
        if not exchange_data:
            return result
        entry = next(iter(exchange_data.values()), {})
        quote = entry.get("quote", {}).get("USD", {})
        volume_24h = quote.get("volume_24h", 0)
        volume_7d = quote.get("volume_7d", 0)

        # Derive a daily average from 7d for relative comparison
        avg_daily_7d = volume_7d / 7 if volume_7d else None
        relative = "normal"
        label = "normal"
        if avg_daily_7d and avg_daily_7d > 0:
            ratio = volume_24h / avg_daily_7d
            if ratio > 1.5:
                relative = "surge"
                label = "DEX surge (24h vol >1.5× 7d avg)"
            elif ratio < 0.6:
                relative = "quiet"
                label = "DEX quiet (24h vol <0.6× 7d avg)"
            else:
                label = f"DEX normal (24h vol {ratio:.1f}× 7d avg)"

        result = {
            "available": True,
            "pancakeswap_volume_24h_usd": round(volume_24h),
            "pancakeswap_volume_7d_avg_usd": round(avg_daily_7d) if avg_daily_7d else None,
            "dex_activity": relative,  # "surge" | "quiet" | "normal"
            "dex_activity_label": label,
        }
    except Exception:
        pass
    return result


def get_bsc_ecosystem_signals(asset: str, cmc_api_key: str) -> Optional[dict]:
    """
    Public entry point. Returns BSC ecosystem signals when the asset is BSC-native,
    None when not applicable (so callers can skip the display block cleanly).

    Combines:
    - PancakeSwap DEX activity (CMC exchange API)
    - BSC network health (public RPC block stats)
    - A composite bsc_signal label for use in regime classification

    Returns None if asset is not BSC-native or all sub-calls fail.
    """
    if not is_bsc_native(asset):
        return None

    dex = get_pancakeswap_activity(cmc_api_key)
    chain = get_bsc_block_stats()

    if not dex["available"] and not chain["available"]:
        return None

    # Composite signal: dex_activity drives the regime hint
    dex_activity = dex.get("dex_activity", "normal") if dex["available"] else "unknown"
    chain_health = chain.get("network_health", "unknown") if chain["available"] else "unknown"

    # Map to regime confidence boost
    # dex_surge + chain_fast → strong bullish BSC ecosystem signal
    # dex_quiet + chain_congested → weak / risk-off
    if dex_activity == "surge" and chain_health in ("fast", "normal"):
        bsc_signal = "ecosystem_active"
        regime_hint = "bullish_bsc_ecosystem"
        confidence_boost = 0.10
    elif dex_activity == "quiet":
        bsc_signal = "ecosystem_quiet"
        regime_hint = "bearish_bsc_ecosystem"
        confidence_boost = -0.05
    else:
        bsc_signal = "ecosystem_normal"
        regime_hint = None
        confidence_boost = 0.0

    return {
        "asset": asset,
        "bsc_native": True,
        "bsc_signal": bsc_signal,
        "regime_hint": regime_hint,
        "confidence_boost": confidence_boost,
        "pancakeswap": dex if dex["available"] else {"available": False},
        "bsc_chain": chain if chain["available"] else {"available": False},
    }
