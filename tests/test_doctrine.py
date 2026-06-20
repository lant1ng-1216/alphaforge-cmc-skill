"""Unit tests for doctrine.py — Strategy Experience Doctrine"""
import pytest
import json
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import alphaforge.doctrine as doctrine_mod


def _make_bt(total_return=5.0, bah=-10.0, sharpe=0.8, max_dd=8.0, n_trades=10):
    return {
        "total_return_pct": total_return,
        "buy_and_hold_return_pct": bah,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "number_of_trades": n_trades,
    }


def _make_mc(prob_pos=60.0, med_sharpe=0.9):
    return {
        "probability_positive_return_pct": prob_pos,
        "sharpe_ratio": {"p50": med_sharpe},
    }


@pytest.fixture(autouse=True)
def isolated_doctrine(tmp_path, monkeypatch):
    """Redirect doctrine storage to a temp dir so tests don't touch ~/.alphaforge."""
    test_path = tmp_path / "doctrine.json"
    monkeypatch.setattr(doctrine_mod, "DOCTRINE_PATH", test_path)
    yield test_path


class TestLoadSave:
    def test_load_returns_empty_on_missing_file(self):
        data = doctrine_mod._load_raw()
        assert data["records"] == []

    def test_save_and_reload(self, isolated_doctrine):
        doctrine_mod._save_raw({"version": "1.0", "records": [{"x": 1}]})
        reloaded = doctrine_mod._load_raw()
        assert reloaded["records"][0]["x"] == 1


class TestSaveDoctrine:
    def test_saves_record_correctly(self, isolated_doctrine):
        doctrine_mod.save_doctrine_record(
            asset="BNB", regime="bearish_trend", strategy_type="sentiment_divergence",
            timeframe="4h", style="momentum",
            backtest=_make_bt(), monte_carlo=_make_mc(),
            gatekeeper_verdict="APPROVED_WITH_WARNINGS", gatekeeper_confidence=75,
        )
        records = doctrine_mod._load_raw()["records"]
        assert len(records) == 1
        r = records[0]
        assert r["asset"] == "BNB"
        assert r["regime"] == "bearish_trend"
        assert r["gatekeeper_verdict"] == "APPROVED_WITH_WARNINGS"
        assert r["backtest_alpha_pp"] == pytest.approx(15.0, abs=0.1)  # 5 - (-10)

    def test_multiple_records_accumulate(self, isolated_doctrine):
        for _ in range(3):
            doctrine_mod.save_doctrine_record(
                asset="ETH", regime="bullish_trend", strategy_type="regime_aware_momentum",
                timeframe="1d", style="momentum",
                backtest=_make_bt(), monte_carlo=_make_mc(),
                gatekeeper_verdict="APPROVED", gatekeeper_confidence=85,
            )
        records = doctrine_mod._load_raw()["records"]
        assert len(records) == 3

    def test_cap_at_max_records(self, isolated_doctrine, monkeypatch):
        monkeypatch.setattr(doctrine_mod, "MAX_RECORDS", 3)
        for _ in range(5):
            doctrine_mod.save_doctrine_record(
                asset="BTC", regime="neutral", strategy_type="regime_aware_momentum",
                timeframe="1h", style="momentum",
                backtest=_make_bt(), monte_carlo=_make_mc(),
                gatekeeper_verdict="APPROVED", gatekeeper_confidence=80,
            )
        records = doctrine_mod._load_raw()["records"]
        assert len(records) == 3


class TestQueryDoctrine:
    def test_returns_empty_when_no_match(self, isolated_doctrine):
        doctrine_mod.save_doctrine_record(
            asset="BNB", regime="bullish_trend", strategy_type="regime_aware_momentum",
            timeframe="4h", style="momentum",
            backtest=_make_bt(), monte_carlo=_make_mc(),
            gatekeeper_verdict="APPROVED", gatekeeper_confidence=80,
        )
        results = doctrine_mod.query_doctrine("bearish_trend", "sentiment_divergence")
        assert results == []

    def test_returns_matching_records(self, isolated_doctrine):
        for i in range(3):
            doctrine_mod.save_doctrine_record(
                asset="BNB", regime="bearish_trend", strategy_type="sentiment_divergence",
                timeframe="4h", style="momentum",
                backtest=_make_bt(total_return=float(i)), monte_carlo=_make_mc(),
                gatekeeper_verdict="APPROVED_WITH_WARNINGS", gatekeeper_confidence=70,
            )
        results = doctrine_mod.query_doctrine("bearish_trend", "sentiment_divergence")
        assert len(results) == 3

    def test_respects_limit(self, isolated_doctrine):
        for _ in range(10):
            doctrine_mod.save_doctrine_record(
                asset="BNB", regime="bearish_trend", strategy_type="sentiment_divergence",
                timeframe="4h", style="momentum",
                backtest=_make_bt(), monte_carlo=_make_mc(),
                gatekeeper_verdict="APPROVED", gatekeeper_confidence=80,
            )
        results = doctrine_mod.query_doctrine("bearish_trend", "sentiment_divergence", limit=3)
        assert len(results) == 3


class TestBuildDoctrineContext:
    def test_returns_none_when_no_records(self, isolated_doctrine):
        ctx = doctrine_mod.build_doctrine_context("bearish_trend", "sentiment_divergence")
        assert ctx is None

    def test_returns_string_with_records(self, isolated_doctrine):
        doctrine_mod.save_doctrine_record(
            asset="BNB", regime="bearish_trend", strategy_type="sentiment_divergence",
            timeframe="4h", style="momentum",
            backtest=_make_bt(total_return=5.0, bah=-20.0), monte_carlo=_make_mc(),
            gatekeeper_verdict="APPROVED_WITH_WARNINGS", gatekeeper_confidence=70,
        )
        ctx = doctrine_mod.build_doctrine_context("bearish_trend", "sentiment_divergence")
        assert ctx is not None
        assert "STRATEGY DOCTRINE" in ctx
        assert "bearish_trend" in ctx
        assert "APPROVED_WITH_WARNINGS" in ctx

    def test_positive_history_produces_high_confidence_insight(self, isolated_doctrine):
        for _ in range(3):
            doctrine_mod.save_doctrine_record(
                asset="BNB", regime="bullish_trend", strategy_type="regime_aware_momentum",
                timeframe="4h", style="momentum",
                backtest=_make_bt(total_return=20.0, bah=5.0), monte_carlo=_make_mc(prob_pos=80.0),
                gatekeeper_verdict="APPROVED", gatekeeper_confidence=90,
            )
        ctx = doctrine_mod.build_doctrine_context("bullish_trend", "regime_aware_momentum")
        assert "Consistent track record" in ctx or "Historical confidence is high" in ctx

    def test_mixed_history_produces_caution_insight(self, isolated_doctrine):
        for i, ret in enumerate([-15.0, -20.0, 5.0]):
            doctrine_mod.save_doctrine_record(
                asset="BTC", regime="high_volatility_chop", strategy_type="regime_aware_momentum",
                timeframe="1d", style="momentum",
                backtest=_make_bt(total_return=ret, bah=0.0), monte_carlo=_make_mc(),
                gatekeeper_verdict="REJECTED" if ret < 0 else "APPROVED_WITH_WARNINGS",
                gatekeeper_confidence=40,
            )
        ctx = doctrine_mod.build_doctrine_context("high_volatility_chop", "regime_aware_momentum")
        assert "caution" in ctx.lower() or "mixed" in ctx.lower()
