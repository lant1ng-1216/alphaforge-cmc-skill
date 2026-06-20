"""
Strategy Experience Doctrine — AlphaForge's persistent institutional memory.

Every completed strategy run writes a compact record to ~/.alphaforge/doctrine.json.
When the Gatekeeper evaluates a new strategy, it queries the doctrine for prior
runs in the same regime × strategy_type combination and injects a human-readable
summary into its evidence packet.

This turns the Gatekeeper from a stateless reasoner into a learning agent: its
judgements are informed not just by the current run's numbers, but by the full
history of how this strategy has performed under the same market regime before.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DOCTRINE_PATH = Path.home() / ".alphaforge" / "doctrine.json"
MAX_RECORDS = 500  # cap to prevent unbounded growth


def _load_raw() -> dict:
    if not DOCTRINE_PATH.exists():
        return {"version": "1.0", "records": []}
    try:
        with open(DOCTRINE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if "records" in data else {"version": "1.0", "records": []}
    except Exception:
        return {"version": "1.0", "records": []}


def _save_raw(data: dict) -> None:
    DOCTRINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DOCTRINE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_doctrine_record(
    asset: str,
    regime: str,
    strategy_type: str,
    timeframe: str,
    style: str,
    backtest: dict,
    monte_carlo: dict,
    gatekeeper_verdict: str,
    gatekeeper_confidence: int,
) -> None:
    """Append a completed strategy run to the persistent doctrine."""
    alpha = backtest.get("total_return_pct", 0) - backtest.get("buy_and_hold_return_pct", 0)
    mc_prob = monte_carlo.get("probability_positive_return_pct")
    mc_sharpe_p50 = (monte_carlo.get("sharpe_ratio") or {}).get("p50")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asset": asset,
        "regime": regime,
        "strategy_type": strategy_type,
        "timeframe": timeframe,
        "style": style,
        "backtest_total_return_pct": round(backtest.get("total_return_pct", 0), 2),
        "backtest_alpha_pp": round(alpha, 2),
        "backtest_sharpe": round(backtest.get("sharpe_ratio", 0), 3),
        "backtest_max_dd_pct": round(backtest.get("max_drawdown_pct", 0), 2),
        "backtest_n_trades": backtest.get("number_of_trades", 0),
        "mc_prob_positive_pct": round(mc_prob, 1) if mc_prob is not None else None,
        "mc_median_sharpe": round(mc_sharpe_p50, 3) if mc_sharpe_p50 is not None else None,
        "gatekeeper_verdict": gatekeeper_verdict,
        "gatekeeper_confidence": gatekeeper_confidence,
    }

    data = _load_raw()
    data["records"].append(record)
    if len(data["records"]) > MAX_RECORDS:
        data["records"] = data["records"][-MAX_RECORDS:]
    _save_raw(data)


def query_doctrine(regime: str, strategy_type: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` most recent records matching regime + strategy_type."""
    data = _load_raw()
    matching = [
        r for r in data["records"]
        if r.get("regime") == regime and r.get("strategy_type") == strategy_type
    ]
    return matching[-limit:]


def build_doctrine_context(regime: str, strategy_type: str) -> Optional[str]:
    """
    Query the doctrine and produce a formatted summary for Gatekeeper injection.
    Returns None when no prior records exist for this combination.
    """
    records = query_doctrine(regime, strategy_type)
    if not records:
        return None

    n = len(records)
    lines = [
        f"=== STRATEGY DOCTRINE ({n} prior run{'s' if n > 1 else ''} in this regime) ===",
        f"Historical performance of '{strategy_type}' in '{regime}' regime:",
    ]
    alphas = []
    verdicts = []
    for i, r in enumerate(records, 1):
        ts = r.get("timestamp", "")[:10]
        asset_tf = f"{r.get('asset', '')}/{r.get('timeframe', '')}"
        alpha = r.get("backtest_alpha_pp", 0)
        dd = r.get("backtest_max_dd_pct", 0)
        verdict = r.get("gatekeeper_verdict", "UNKNOWN")
        conf = r.get("gatekeeper_confidence", 0)
        lines.append(
            f"  Run {i} ({ts}): {asset_tf} — alpha {alpha:+.1f}pp, "
            f"DD {dd:.1f}%, verdict {verdict} ({conf}%)"
        )
        alphas.append(alpha)
        verdicts.append(verdict)

    avg_alpha = sum(alphas) / len(alphas) if alphas else 0
    pos_count = sum(1 for a in alphas if a > 0)
    approved_count = sum(1 for v in verdicts if "APPROVED" in v)

    if pos_count == n and approved_count == n:
        insight = (
            f"Doctrine insight: Consistent track record "
            f"({pos_count}/{n} positive alpha, avg {avg_alpha:+.1f}pp, all runs approved). "
            f"Historical confidence is high."
        )
    elif pos_count > n // 2:
        insight = (
            f"Doctrine insight: Mostly positive history "
            f"({pos_count}/{n} positive alpha, avg {avg_alpha:+.1f}pp). "
            f"Strategy has worked in this regime before."
        )
    else:
        insight = (
            f"Doctrine insight: Mixed history "
            f"({pos_count}/{n} positive alpha, avg {avg_alpha:+.1f}pp). "
            f"Exercise caution — this strategy has underperformed in this regime."
        )
    lines.append(insight)
    return "\n".join(lines)


def doctrine_stats() -> dict:
    """Return summary statistics about the current doctrine (for display)."""
    data = _load_raw()
    records = data.get("records", [])
    if not records:
        return {"total_runs": 0, "unique_regimes": 0, "unique_assets": 0}
    regimes = {r.get("regime") for r in records}
    assets = {r.get("asset") for r in records}
    return {
        "total_runs": len(records),
        "unique_regimes": len(regimes),
        "unique_assets": len(assets),
        "latest_run": records[-1].get("timestamp", "")[:10],
    }
