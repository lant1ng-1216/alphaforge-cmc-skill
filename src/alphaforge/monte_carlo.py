"""
Monte Carlo simulation for AlphaForge strategy backtests.

Bootstrap-resamples the strategy's daily equity returns 1000 times to convert
a single deterministic backtest path into a probability distribution of outcomes.
This is standard practice in professional quant workflows — a single backtest
number is a point estimate; Monte Carlo gives confidence intervals.
"""
import math
import random
from typing import Optional


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(var)
    return (mean / std * math.sqrt(365)) if std > 0 else 0.0


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def run_monte_carlo(
    equity_curve: list[float],
    n_simulations: int = 1000,
    initial_capital: float = 10_000,
    seed: Optional[int] = 42,
) -> dict:
    """
    Bootstrap Monte Carlo on a strategy equity curve.

    Resamples daily returns with replacement N times. Each resampled path
    represents a plausible alternative history under the same strategy rules.
    Aggregating 1000 paths gives an empirical distribution of outcomes.

    Args:
        equity_curve: Full daily portfolio value series from the backtester.
        n_simulations: Bootstrap iterations (1000 is the professional standard).
        initial_capital: Starting capital for return normalization.
        seed: Fixed seed for reproducible output.

    Returns:
        Percentile estimates (p5/p25/p50/p75/p95) for return, Sharpe, and
        max drawdown, plus probability metrics.
    """
    if len(equity_curve) < 10:
        return {"error": "Insufficient equity curve data for Monte Carlo simulation"}

    if seed is not None:
        random.seed(seed)

    # Derive daily returns from the equity path
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            daily_returns.append((equity_curve[i] - prev) / prev)

    if len(daily_returns) < 5:
        return {"error": "Too few data points for Monte Carlo simulation"}

    n = len(daily_returns)
    sim_returns: list[float] = []
    sim_sharpes: list[float] = []
    sim_max_dds: list[float] = []

    for _ in range(n_simulations):
        # Bootstrap: resample n daily returns with replacement
        sample = [random.choice(daily_returns) for _ in range(n)]

        # Reconstruct a synthetic equity path from the resampled returns
        eq = [initial_capital]
        for r in sample:
            eq.append(eq[-1] * (1 + r))

        total_return = (eq[-1] - initial_capital) / initial_capital * 100
        sim_returns.append(total_return)
        sim_sharpes.append(_sharpe(sample))
        sim_max_dds.append(_max_drawdown(eq) * 100)

    prob_positive = sum(1 for r in sim_returns if r > 0) / n_simulations * 100
    prob_sharpe_gt_1 = sum(1 for s in sim_sharpes if s > 1.0) / n_simulations * 100
    prob_large_dd = sum(1 for d in sim_max_dds if d > 20) / n_simulations * 100

    return {
        "n_simulations": n_simulations,
        "total_return": {
            "p5":  round(_percentile(sim_returns, 5), 2),
            "p25": round(_percentile(sim_returns, 25), 2),
            "p50": round(_percentile(sim_returns, 50), 2),
            "p75": round(_percentile(sim_returns, 75), 2),
            "p95": round(_percentile(sim_returns, 95), 2),
        },
        "sharpe_ratio": {
            "p5":  round(_percentile(sim_sharpes, 5), 2),
            "p50": round(_percentile(sim_sharpes, 50), 2),
            "p95": round(_percentile(sim_sharpes, 95), 2),
        },
        "max_drawdown_pct": {
            "p50": round(_percentile(sim_max_dds, 50), 2),
            "p95": round(_percentile(sim_max_dds, 95), 2),
        },
        "probability_positive_return_pct": round(prob_positive, 1),
        "probability_sharpe_gt_1_pct": round(prob_sharpe_gt_1, 1),
        "probability_large_drawdown_pct": round(prob_large_dd, 1),
    }
