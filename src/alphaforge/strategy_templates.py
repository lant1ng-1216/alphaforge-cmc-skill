"""
Strategy templates — returns the appropriate spec structure for a given regime + intent.
"""
from typing import Optional
from .intent_parser import StrategyIntent


REGIME_TO_STRATEGY = {
    "bullish_trend": "regime_aware_momentum",
    "panic_reversal": "panic_reversal",
    "sentiment_overheated": "sentiment_divergence",
    "low_volatility_accumulation": "volatility_breakout",
    "high_volatility_chop": "no_trade",
    "bearish_trend": "sentiment_divergence",
    "derivatives_crowded_long": "sentiment_divergence",
    "derivatives_crowded_short": "regime_aware_momentum",
    "neutral": "regime_aware_momentum",
}


def select_template(regime: str, intent: StrategyIntent) -> str:
    """Select strategy template name based on regime + intent constraints."""
    # Override by intent style
    if intent.style == "mean_reversion" or "panic_reversal" in intent.constraints:
        return "panic_reversal"
    if intent.style == "breakout" or "low_volatility_accumulation" in intent.constraints:
        return "volatility_breakout"
    # Apply sentiment guard override
    if "avoid_overheated_sentiment" in intent.constraints and regime == "sentiment_overheated":
        return "sentiment_divergence"
    return REGIME_TO_STRATEGY.get(regime, "regime_aware_momentum")


def build_spec(
    template_name: str,
    intent: StrategyIntent,
    regime: str,
    secondary_regimes: list[str],
    fear_greed: int,
) -> dict:
    """Build the full machine-readable strategy spec."""

    risk_settings = {
        "aggressive": {"max_position_size_pct": 40, "stop_loss_pct": 10, "trailing_stop_pct": 12, "max_strategy_drawdown_pct": 25},
        "moderate":   {"max_position_size_pct": 25, "stop_loss_pct": 7,  "trailing_stop_pct": 9,  "max_strategy_drawdown_pct": 15},
        "conservative":{"max_position_size_pct": 12, "stop_loss_pct": 4,  "trailing_stop_pct": 6,  "max_strategy_drawdown_pct": 8},
    }
    risk = risk_settings.get(intent.risk_profile, risk_settings["moderate"])

    base = {
        "version": "1.0",
        "generated_by": "AlphaForge",
        "asset": intent.asset,
        "quote_asset": "USDT",
        "timeframe": intent.timeframe,
        "strategy_type": template_name,
        "market_regime": {
            "primary": regime,
            "secondary": secondary_regimes,
        },
        "features": {
            "technical": ["ema_20", "ema_50", "rsi_14", "macd_histogram", "volume_zscore", "atr_14"],
            "sentiment": ["fear_greed_score", "social_attention_zscore", "news_sentiment_score"],
            "derivatives": ["funding_rate_zscore", "open_interest_change", "long_short_crowding"],
            "data_note": (
                "fear_greed_score is live (CMC classic REST API). Market-wide funding rate and open "
                "interest are also live via the CMC Data MCP (see live_cross_check in the full result) — "
                "but as market-wide aggregates, not per-asset values, which is why funding_rate_zscore, "
                "open_interest_change, and long_short_crowding stay declared-only here: those need a "
                "per-asset series this pipeline doesn't have a source for yet. social_attention_zscore and "
                "news_sentiment_score are similarly declared-only — CMC's evidence-pack skills synthesize "
                "sentiment narratively rather than exposing a raw per-asset score for those two fields."
            ),
        },
        "backtest": {
            "start_date": "2025-06-01",
            "end_date": "2026-06-01",
            "initial_capital": 10000,
            "transaction_cost_bps": 10,
            "slippage_bps": 5,
            "benchmark": "buy_and_hold",
        },
        "evaluation_metrics": [
            "total_return", "annualized_return", "sharpe_ratio",
            "max_drawdown", "win_rate", "profit_factor", "exposure_time",
        ],
    }

    if template_name == "regime_aware_momentum":
        base.update({
            "entry_rules": {
                "all": [
                    "close > ema_20",
                    "ema_20 > ema_50",
                    "macd_histogram > 0",
                    "rsi_14 >= 50",
                    "rsi_14 <= 70",
                    "volume_zscore > 0.8",
                ]
            },
            "exit_rules": {
                "any": [
                    "close < ema_20",
                    "macd_histogram < 0",
                    "rsi_14 > 80 AND rsi_14_declining == true",
                ]
            },
            "filters": {
                "sentiment_guard": {
                    "avoid_entry_if_fear_greed_above": 85,
                    "reduce_position_if_social_attention_zscore_above": 2.5,
                },
                "derivatives_guard": {
                    "reduce_position_if_funding_rate_zscore_above": 1.5,
                    "avoid_entry_if_long_short_crowding_above": 0.7,
                },
                "avoid_entry_if": [
                    "fear_greed_score > 85",
                    "rsi_14 > 75",
                    "funding_rate_zscore > 1.5",
                    "social_attention_zscore > 2.5",
                ],
            },
        })

    elif template_name == "panic_reversal":
        base.update({
            "entry_rules": {
                "all": [
                    "rsi_14 < 30",
                    "fear_greed_score < 25",
                    "close_distance_from_ema_50_pct < -12",
                    "volume_zscore > 1.5",
                    "close > previous_bar_low",
                ]
            },
            "exit_rules": {
                "any": [
                    "close >= ema_20",
                    "rsi_14 >= 55",
                    "take_profit_pct >= 12",
                    "max_holding_bars >= 18",
                ]
            },
            "filters": {},
        })
        risk["max_position_size_pct"] = min(risk["max_position_size_pct"], 15)

    elif template_name == "sentiment_divergence":
        base.update({
            "long_setup": {
                "conditions": [
                    "price_momentum_10 > 0",
                    "volume_zscore > 0.7",
                    "fear_greed_score < 75",
                    "rsi_14 between 40 and 65",
                ]
            },
            "avoid_setup": {
                "conditions": [
                    "fear_greed_score > 80",
                    "rsi_14 > 75",
                ]
            },
            "filters": {
                "regime_note": "Enters only when price action and sentiment are NOT both extreme"
            },
        })

    elif template_name == "volatility_breakout":
        base.update({
            "entry_rules": {
                "all": [
                    "realized_volatility_percentile < 30",
                    "close > rolling_high_20",
                    "volume_zscore > 1.2",
                    "atr_expanding == true",
                ]
            },
            "exit_rules": {
                "any": [
                    "close < breakout_entry_level",
                    "atr_stop_triggered == true",
                    "momentum_decay == true",
                ]
            },
            "filters": {},
        })
        risk["stop_loss_atr_multiple"] = 2.0

    elif template_name == "no_trade":
        base.update({
            "entry_rules": {"all": ["no_entry — high volatility chop regime detected"]},
            "exit_rules": {"any": []},
            "filters": {"note": "Wait for regime to resolve before entering positions"},
        })

    if "reduce_exposure_on_volatility" in intent.constraints:
        filters = base.setdefault("filters", {})
        filters["volatility_guard"] = {
            "reduce_position_if_realized_volatility_above": 0.9,
            "exit_if_realized_volatility_spike_pct": 50,
        }
        exit_rules = base.get("exit_rules")
        if isinstance(exit_rules, dict) and "any" in exit_rules:
            exit_rules["any"].append("realized_volatility > realized_volatility_baseline * 1.5")
        risk["max_position_size_pct"] = round(risk["max_position_size_pct"] * 0.8)

    base["risk_management"] = risk
    return base
