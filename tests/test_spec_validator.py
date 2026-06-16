"""Tests for strategy spec validator."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.spec_validator import validate_spec


def _base_spec():
    return {
        "version": "1.0",
        "generated_by": "AlphaForge",
        "asset": "BNB",
        "quote_asset": "USDT",
        "timeframe": "4h",
        "strategy_type": "regime_aware_momentum",
        "market_regime": {"primary": "bullish_trend", "secondary": []},
        "features": {"technical": ["ema_20", "rsi_14"]},
        "entry_rules": {"all": ["close > ema_20"]},
        "exit_rules": {"any": ["close < ema_20"]},
        "risk_management": {"max_position_size_pct": 25, "stop_loss_pct": 7, "max_strategy_drawdown_pct": 15},
        "backtest": {"start_date": "2025-01-01", "end_date": "2026-01-01", "initial_capital": 10000},
        "evaluation_metrics": ["total_return", "max_drawdown", "sharpe_ratio"],
    }


def test_valid_spec():
    result = validate_spec(_base_spec())
    assert result.valid, f"Expected valid, got errors: {result.errors}"


def test_missing_required_field():
    spec = _base_spec()
    del spec["asset"]
    result = validate_spec(spec)
    assert not result.valid
    assert any("asset" in e for e in result.errors)


def test_invalid_strategy_type():
    spec = _base_spec()
    spec["strategy_type"] = "magic_strategy"
    result = validate_spec(spec)
    assert not result.valid


def test_invalid_timeframe():
    spec = _base_spec()
    spec["timeframe"] = "2h"
    result = validate_spec(spec)
    assert not result.valid


def test_stop_loss_warning():
    spec = _base_spec()
    spec["risk_management"]["stop_loss_pct"] = 20
    spec["risk_management"]["max_strategy_drawdown_pct"] = 15
    result = validate_spec(spec)
    assert any("stop_loss" in w for w in result.warnings)


def test_invalid_regime():
    spec = _base_spec()
    spec["market_regime"]["primary"] = "moon_regime"
    result = validate_spec(spec)
    assert not result.valid


def test_backtest_date_order():
    spec = _base_spec()
    spec["backtest"]["start_date"] = "2026-01-01"
    spec["backtest"]["end_date"] = "2025-01-01"
    result = validate_spec(spec)
    assert not result.valid


if __name__ == "__main__":
    test_valid_spec()
    test_missing_required_field()
    test_invalid_strategy_type()
    test_invalid_timeframe()
    test_stop_loss_warning()
    test_invalid_regime()
    test_backtest_date_order()
    print("All spec validator tests passed.")
