"""Tests for the backtester."""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.backtester import run_backtest, run_walk_forward_backtest


def make_trending_ohlcv(n=200, start=100.0, drift=0.003):
    """Uptrending market with volume spikes — should trigger momentum entries."""
    candles = []
    price = start
    import math, random
    random.seed(42)
    for i in range(n):
        price *= (1 + drift + math.sin(i * 0.3) * 0.002)
        # Occasional volume spikes to trigger volume_zscore > 0.8
        volume = 1000 * (1 + random.random() * 0.5) if i % 7 != 0 else 3000
        candles.append({
            "time": str(i),
            "open": price * 0.999,
            "high": price * 1.008,
            "low": price * 0.992,
            "close": price,
            "volume": volume,
        })
    return candles


def make_crash_ohlcv(n=200, start=100.0):
    """Crashing market — should trigger panic reversal conditions late."""
    candles = []
    price = start
    for i in range(n):
        drop = 0.005 if i < 150 else -0.003
        price *= (1 - drop)
        candles.append({
            "time": str(i),
            "open": price * 1.001,
            "high": price * 1.005,
            "low": price * 0.995,
            "close": price,
            "volume": 1000 + abs(i - 150) * 20,
        })
    return candles


def _base_spec(strategy_type="regime_aware_momentum"):
    return {
        "version": "1.0",
        "generated_by": "AlphaForge",
        "strategy_type": strategy_type,
        "risk_management": {
            "max_position_size_pct": 25,
            "stop_loss_pct": 7,
            "trailing_stop_pct": 9,
            "max_strategy_drawdown_pct": 30,
        },
        "backtest": {
            "initial_capital": 10000,
            "transaction_cost_bps": 10,
            "slippage_bps": 5,
        },
    }


def test_backtest_returns_required_keys():
    ohlcv = make_trending_ohlcv()
    result = run_backtest(ohlcv, _base_spec())
    required = ["total_return_pct", "buy_and_hold_return_pct", "max_drawdown_pct",
                "sharpe_ratio", "win_rate_pct", "profit_factor", "number_of_trades",
                "exposure_time_pct", "final_equity"]
    for k in required:
        assert k in result, f"Missing key: {k}"


def test_final_equity_positive():
    ohlcv = make_trending_ohlcv()
    result = run_backtest(ohlcv, _base_spec())
    assert result["final_equity"] > 0


def test_max_drawdown_non_negative():
    ohlcv = make_crash_ohlcv()
    result = run_backtest(ohlcv, _base_spec())
    assert result["max_drawdown_pct"] >= 0


def test_trending_market_buy_and_hold_positive():
    """In an uptrending market, buy-and-hold return should be positive."""
    ohlcv = make_trending_ohlcv(n=200)
    result = run_backtest(ohlcv, _base_spec("regime_aware_momentum"))
    assert result["buy_and_hold_return_pct"] > 0, "Expected positive buy-and-hold in uptrend"


def test_exposure_time_range():
    ohlcv = make_trending_ohlcv()
    result = run_backtest(ohlcv, _base_spec())
    assert 0 <= result["exposure_time_pct"] <= 100


def test_win_rate_range():
    ohlcv = make_trending_ohlcv()
    result = run_backtest(ohlcv, _base_spec())
    assert 0 <= result["win_rate_pct"] <= 100


def test_walk_forward_splits_into_requested_periods():
    ohlcv = make_trending_ohlcv(n=400)
    results = run_walk_forward_backtest(ohlcv, _base_spec(), n_periods=2)
    assert len(results) == 2
    for p in results:
        assert "period_label" in p
        assert "equity_curve" not in p  # stripped to keep the payload small
        assert p["period_bars"] > 0


def test_walk_forward_too_short_returns_empty():
    ohlcv = make_trending_ohlcv(n=100)  # below the 2x min_period_bars floor
    results = run_walk_forward_backtest(ohlcv, _base_spec(), n_periods=2)
    assert results == []


if __name__ == "__main__":
    test_backtest_returns_required_keys()
    test_final_equity_positive()
    test_max_drawdown_non_negative()
    test_trending_market_buy_and_hold_positive()
    test_exposure_time_range()
    test_win_rate_range()
    test_walk_forward_splits_into_requested_periods()
    test_walk_forward_too_short_returns_empty()
    print("All backtester tests passed.")
