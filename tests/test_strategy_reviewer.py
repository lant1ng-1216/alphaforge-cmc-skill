"""Unit tests for strategy_reviewer.py"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge.strategy_reviewer import (
    run_risk_agent,
    run_regime_agent,
    run_gatekeeper,
    review_strategy,
    AgentCheck,
    AgentReview,
    GatekeeperReview,
)


def _make_spec(stop_loss=7, max_pos=25, max_dd=15, strategy_type="regime_aware_momentum",
               risk_profile="moderate"):
    return {
        "strategy_type": strategy_type,
        "risk_management": {
            "stop_loss_pct": stop_loss,
            "max_position_size_pct": max_pos,
            "max_strategy_drawdown_pct": max_dd,
        },
    }


def _make_features(rv=0.05, rsi=55.0):
    return {"realized_volatility": rv, "rsi_14": rsi}


def _make_backtest(total_return=5.0, bah=-10.0, max_dd=8.0, sharpe=0.8,
                   n_trades=10, win_rate=55.0, exposure=30.0):
    return {
        "total_return_pct": total_return,
        "buy_and_hold_return_pct": bah,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "number_of_trades": n_trades,
        "win_rate_pct": win_rate,
        "exposure_time_pct": exposure,
    }


def _make_intent(asset="BNB", risk_profile="moderate", style="momentum", timeframe="4h"):
    return {"asset": asset, "risk_profile": risk_profile, "style": style, "timeframe": timeframe}


def _make_monte_carlo(prob_pos=60.0, med_sharpe=0.9, p95_dd=18.0):
    return {
        "probability_positive_return_pct": prob_pos,
        "sharpe_ratio": {"p50": med_sharpe},
        "max_drawdown_pct": {"p95": p95_dd},
    }


def _make_walk_forward():
    return [
        {"period": "P1/2", "bars": 182, "total_return_pct": 3.0, "sharpe_ratio": 0.9,
         "max_drawdown_pct": 4.0, "number_of_trades": 5},
        {"period": "P2/2", "bars": 183, "total_return_pct": 2.0, "sharpe_ratio": 0.7,
         "max_drawdown_pct": 5.0, "number_of_trades": 5},
    ]


class TestAgentDataclasses:
    def test_agent_check_fields(self):
        c = AgentCheck(name="test", verdict="pass", message="ok")
        assert c.name == "test"
        assert c.verdict == "pass"

    def test_agent_review_fields(self):
        check = AgentCheck("x", "pass", "ok")
        r = AgentReview(agent="RiskAgent", verdict="pass", checks=[check], confidence=80)
        assert r.agent == "RiskAgent"
        assert len(r.checks) == 1


class TestRiskAgent:
    def test_pass_on_calibrated_params(self):
        spec = _make_spec(stop_loss=7, max_pos=25, max_dd=15)
        feat = _make_features(rv=0.04)
        bt = _make_backtest(max_dd=10.0)
        review = run_risk_agent(spec, feat, bt, "moderate")
        assert review.verdict in ("pass", "warn", "reject")
        assert len(review.checks) == 3

    def test_reject_on_stop_too_tight(self):
        # stop_loss 2% vs realized vol 15% — should trigger reject
        spec = _make_spec(stop_loss=2, max_dd=15)
        feat = _make_features(rv=0.15)
        bt = _make_backtest(max_dd=5.0)
        review = run_risk_agent(spec, feat, bt, "moderate")
        stop_check = next(c for c in review.checks if "stop" in c.name.lower())
        assert stop_check.verdict in ("warn", "reject")

    def test_reject_on_backtest_dd_exceeds_spec(self):
        spec = _make_spec(max_dd=10)
        feat = _make_features(rv=0.04)
        bt = _make_backtest(max_dd=18.0)
        review = run_risk_agent(spec, feat, bt, "moderate")
        dd_check = next(c for c in review.checks if "drawdown" in c.name.lower())
        assert dd_check.verdict in ("warn", "reject")


class TestRegimeAgent:
    def test_returns_correct_fields(self):
        feat = _make_features(rsi=60.0)
        review = run_regime_agent(
            regime_primary="bullish_trend",
            strategy_type="regime_aware_momentum",
            features=feat,
            intent=_make_intent(),
        )
        assert review.agent == "RegimeAgent"
        assert len(review.checks) == 3
        assert review.verdict in ("pass", "warn", "reject")

    def test_warn_on_mismatched_regime(self):
        feat = _make_features(rsi=30.0)
        review = run_regime_agent(
            regime_primary="bearish_trend",
            strategy_type="regime_aware_momentum",
            features=feat,
            intent=_make_intent(),
        )
        alignment_check = next(c for c in review.checks if "alignment" in c.name.lower())
        assert alignment_check.verdict in ("warn", "reject")


class TestGatekeeper:
    def _make_risk_review(self, spec=None, rv=0.04, max_dd=8.0, risk_profile="moderate"):
        spec = spec or _make_spec()
        return run_risk_agent(spec, _make_features(rv=rv), _make_backtest(max_dd=max_dd), risk_profile)

    def _make_regime_review(self, regime="bullish_trend", strategy="regime_aware_momentum"):
        return run_regime_agent(
            regime_primary=regime,
            strategy_type=strategy,
            features=_make_features(),
            intent=_make_intent(),
        )

    def test_returns_gatekeeper_review(self):
        result = run_gatekeeper(
            risk_review=self._make_risk_review(),
            regime_review=self._make_regime_review(),
            backtest=_make_backtest(),
            walk_forward=_make_walk_forward(),
            monte_carlo=_make_monte_carlo(),
            intent=_make_intent(),
        )
        assert isinstance(result, GatekeeperReview)
        assert result.final_verdict in (
            "APPROVED", "APPROVED_WITH_WARNINGS", "CONDITIONALLY_APPROVED", "REJECTED"
        )
        assert 0 <= result.confidence <= 100

    def test_approved_on_strong_strategy(self):
        bt = _make_backtest(total_return=20.0, bah=-5.0, max_dd=7.0, sharpe=1.2, n_trades=15)
        mc = _make_monte_carlo(prob_pos=75.0, med_sharpe=1.1, p95_dd=12.0)
        result = run_gatekeeper(
            risk_review=self._make_risk_review(rv=0.03, max_dd=7.0),
            regime_review=self._make_regime_review("bullish_trend"),
            backtest=bt,
            walk_forward=_make_walk_forward(),
            monte_carlo=mc,
            intent=_make_intent(),
        )
        assert result.final_verdict in ("APPROVED", "APPROVED_WITH_WARNINGS")

    def test_rejected_or_conditional_on_weak_strategy(self):
        spec = _make_spec(stop_loss=2, max_pos=40, max_dd=5)
        bt = _make_backtest(total_return=-20.0, bah=5.0, max_dd=25.0, sharpe=-1.5, n_trades=2)
        mc = _make_monte_carlo(prob_pos=10.0, med_sharpe=-1.0, p95_dd=35.0)
        result = run_gatekeeper(
            risk_review=run_risk_agent(spec, _make_features(rv=0.15), bt, "aggressive"),
            regime_review=self._make_regime_review("bearish_trend", "regime_aware_momentum"),
            backtest=bt,
            walk_forward=_make_walk_forward(),
            monte_carlo=mc,
            intent=_make_intent(),
        )
        assert result.final_verdict in ("CONDITIONALLY_APPROVED", "REJECTED")


class TestReviewStrategy:
    def test_full_pipeline_returns_dict(self):
        spec = _make_spec()
        result = review_strategy(
            spec=spec,
            features=_make_features(),
            regime_primary="bullish_trend",
            intent=_make_intent(),
            backtest=_make_backtest(),
            walk_forward=_make_walk_forward(),
            monte_carlo=_make_monte_carlo(),
        )
        assert isinstance(result, dict)
        assert "final_verdict" in result
        assert "confidence" in result
        assert "summary" in result
        assert "risk_agent" in result
        assert "regime_agent" in result

    def test_flat_monte_carlo_handled(self):
        mc_flat = {
            "n_simulations": 0,
            "note": "No trades executed",
            "probability_positive_return_pct": None,
            "sharpe_ratio": {"p50": 0.0},
            "max_drawdown_pct": {"p95": 0.0},
        }
        result = review_strategy(
            spec=_make_spec(strategy_type="no_trade"),
            features=_make_features(),
            regime_primary="high_volatility_chop",
            intent=_make_intent(),
            backtest=_make_backtest(n_trades=0, total_return=0.0),
            walk_forward=_make_walk_forward(),
            monte_carlo=mc_flat,
        )
        assert result["final_verdict"] in (
            "APPROVED", "APPROVED_WITH_WARNINGS", "CONDITIONALLY_APPROVED", "REJECTED"
        )
