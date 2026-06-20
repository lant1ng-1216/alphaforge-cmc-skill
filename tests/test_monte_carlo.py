"""Unit tests for monte_carlo.py"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.monte_carlo import run_monte_carlo


def _flat_curve(n=100, value=10000.0):
    return [value] * n


def _trending_curve(n=200, start=10000.0, daily_gain=0.005):
    curve = [start]
    for _ in range(n - 1):
        curve.append(curve[-1] * (1 + daily_gain))
    return curve


def _volatile_curve(n=200, seed=42):
    import random
    random.seed(seed)
    curve = [10000.0]
    for _ in range(n - 1):
        r = random.gauss(0.001, 0.03)
        curve.append(max(1.0, curve[-1] * (1 + r)))
    return curve


class TestRunMonteCarlo:
    def test_returns_expected_keys(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=100, seed=42)
        assert "n_simulations" in result
        assert "total_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "probability_positive_return_pct" in result
        assert "probability_sharpe_gt_1_pct" in result
        assert "probability_large_drawdown_pct" in result

    def test_total_return_percentile_ordering(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=500, seed=1)
        tr = result["total_return"]
        assert tr["p5"] <= tr["p25"] <= tr["p50"] <= tr["p75"] <= tr["p95"]

    def test_sharpe_percentile_ordering(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=200, seed=7)
        sr = result["sharpe_ratio"]
        assert sr["p5"] <= sr["p50"] <= sr["p95"]

    def test_max_drawdown_percentile_ordering(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=200, seed=99)
        dd = result["max_drawdown_pct"]
        assert dd["p50"] <= dd["p95"]

    def test_probability_fields_in_range(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=300, seed=5)
        for key in ("probability_positive_return_pct", "probability_sharpe_gt_1_pct",
                    "probability_large_drawdown_pct"):
            assert 0.0 <= result[key] <= 100.0

    def test_flat_curve_returns_note(self):
        curve = _flat_curve()
        result = run_monte_carlo(curve)
        assert "note" in result
        assert result["n_simulations"] == 0
        assert result["probability_positive_return_pct"] is None
        assert result["probability_sharpe_gt_1_pct"] is None
        assert result["probability_large_drawdown_pct"] is None

    def test_flat_curve_percentiles_are_zero(self):
        result = run_monte_carlo(_flat_curve())
        assert result["total_return"]["p50"] == 0.0
        assert result["max_drawdown_pct"]["p50"] == 0.0

    def test_insufficient_data_returns_error(self):
        result = run_monte_carlo([10000.0] * 5)
        assert "error" in result

    def test_trending_curve_positive_median_return(self):
        curve = _trending_curve(daily_gain=0.003)
        result = run_monte_carlo(curve, n_simulations=300, seed=42)
        assert result["total_return"]["p50"] > 0

    def test_seed_reproducibility(self):
        curve = _volatile_curve()
        r1 = run_monte_carlo(curve, n_simulations=100, seed=42)
        r2 = run_monte_carlo(curve, n_simulations=100, seed=42)
        assert r1["total_return"]["p50"] == r2["total_return"]["p50"]
        assert r1["probability_positive_return_pct"] == r2["probability_positive_return_pct"]

    def test_n_simulations_respected(self):
        curve = _volatile_curve()
        result = run_monte_carlo(curve, n_simulations=50, seed=1)
        assert result["n_simulations"] == 50
