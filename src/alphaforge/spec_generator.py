"""
AlphaForge main pipeline — orchestrates the full flow from intent to strategy spec + backtest.
"""
import json
from .cmc_adapter import CMCAdapter
from .intent_parser import parse_intent, StrategyIntent
from .features import compute_features, latest_features
from .regime_classifier import classify_regime, RegimeResult
from .strategy_templates import select_template, build_spec
from .backtester import run_backtest
from .spec_validator import validate_spec


def generate_strategy(user_input: str, cmc_api_key: str) -> dict:
    """
    Full AlphaForge pipeline.

    Args:
        user_input: Natural language strategy request
        cmc_api_key: CoinMarketCap API key

    Returns:
        dict with keys: intent, market_context, regime, spec, backtest, explanation, failure_modes
    """
    cmc = CMCAdapter(cmc_api_key)

    # Step 1: Parse intent
    intent = parse_intent(user_input)

    # Step 2: Pull CMC market context
    fg = cmc.get_fear_and_greed()
    quote = cmc.get_quote(intent.asset)
    ohlcv = cmc.get_ohlcv_daily(intent.asset, count=365)
    global_metrics = cmc.get_global_metrics()

    market_context = {
        "asset": intent.asset,
        "price": quote["price"],
        "price_change_24h": quote["percent_change_24h"],
        "price_change_7d": quote["percent_change_7d"],
        "volume_24h": quote["volume_24h"],
        "volume_change_24h": quote["volume_change_24h"],
        "fear_greed_score": fg["score"],
        "fear_greed_label": fg["label"],
        "btc_dominance": global_metrics["btc_dominance"],
        "data_points": len(ohlcv),
    }

    # Step 3: Compute features
    feat_series = compute_features(ohlcv)
    feat = latest_features(feat_series)
    # macd comes back as dict from latest_features
    if isinstance(feat.get("macd"), dict):
        feat["macd_histogram"] = feat["macd"].get("histogram")

    # Step 4: Classify market regime
    regime_result: RegimeResult = classify_regime(
        feat=feat,
        fear_greed=fg["score"],
        price_change_24h=quote["percent_change_24h"],
        price_change_7d=quote["percent_change_7d"],
        volume_change_24h=quote.get("volume_change_24h"),
    )

    # Step 5: Select strategy template
    template_name = select_template(regime_result.primary, intent)

    # Step 6: Build strategy spec
    spec = build_spec(
        template_name=template_name,
        intent=intent,
        regime=regime_result.primary,
        secondary_regimes=regime_result.secondary,
        fear_greed=fg["score"],
    )

    # Step 7: Validate spec
    validation = validate_spec(spec)

    # Step 8: Run backtest
    backtest_results = run_backtest(
        ohlcv=ohlcv,
        spec=spec,
        initial_capital=spec["backtest"]["initial_capital"],
        transaction_cost_bps=spec["backtest"]["transaction_cost_bps"],
        slippage_bps=spec["backtest"]["slippage_bps"],
    )

    # Step 9: Build explanation + failure modes
    explanation = _build_explanation(intent, regime_result, template_name, backtest_results)
    failure_modes = _build_failure_modes(template_name, regime_result)

    return {
        "intent": intent.to_dict(),
        "market_context": market_context,
        "_ohlcv": ohlcv,  # kept for visualizer; stripped from JSON export
        "validation": {
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
        "regime": {
            "primary": regime_result.primary,
            "secondary": regime_result.secondary,
            "confidence": regime_result.confidence,
            "explanation": regime_result.explanation,
            "signals": {k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in regime_result.signals.items() if v is not None},
        },
        "spec": spec,
        "backtest": backtest_results,
        "explanation": explanation,
        "failure_modes": failure_modes,
    }


def _build_explanation(intent: StrategyIntent, regime: RegimeResult, template: str, bt: dict) -> str:
    alpha = bt["total_return_pct"] - bt["buy_and_hold_return_pct"]
    return (
        f"Strategy: {template.replace('_', ' ').title()} on {intent.asset}/{intent.timeframe}\n\n"
        f"Market context: {regime.explanation}\n\n"
        f"This strategy {'enters only when trend, momentum, and volume align' if template == 'regime_aware_momentum' else 'targets mean-reversion setups in capitulation conditions' if template == 'panic_reversal' else 'avoids entries when sentiment and price action diverge' if template == 'sentiment_divergence' else 'intentionally holds cash — no entry conditions met in this regime' if template == 'no_trade' else 'waits for low-volatility compression before breakout entry'}.\n\n"
        f"Backtest summary ({bt['number_of_trades']} trades, {bt['exposure_time_pct']}% exposure): "
        f"Total return {bt['total_return_pct']:+.1f}% vs buy-and-hold {bt['buy_and_hold_return_pct']:+.1f}% "
        f"({'outperformed' if alpha > 0 else 'underperformed'} by {abs(alpha):.1f}pp). "
        f"Sharpe {bt['sharpe_ratio']:.2f}, max drawdown {bt['max_drawdown_pct']:.1f}%, "
        f"win rate {bt['win_rate_pct']:.1f}%."
    )


def _build_failure_modes(template: str, regime: RegimeResult) -> list[str]:
    common = [
        "Sudden news-driven gap reversals that bypass stop-loss levels.",
        "Liquidity crises where slippage far exceeds modeled assumptions.",
        "Regime misclassification during transition periods between bull and bear markets.",
    ]
    template_specific = {
        "regime_aware_momentum": [
            "Extended low-volume rallies where momentum signals fire but volume doesn't confirm.",
            "False MACD crossovers during high-volatility sideways markets.",
        ],
        "panic_reversal": [
            "Continuation of downtrend after apparent capitulation (dead-cat bounce risk).",
            "Insufficient holding time to capture the full rebound.",
        ],
        "sentiment_divergence": [
            "Prolonged periods of extreme sentiment that the filter avoids entirely, missing real moves.",
            "Sentiment data lag causing late entries after the move has already occurred.",
        ],
        "volatility_breakout": [
            "False breakouts: price briefly exceeds resistance but immediately reverses.",
            "Low-volatility periods lasting too long, causing the strategy to go dormant.",
        ],
        "no_trade": ["N/A — no-trade regime, strategy is intentionally idle."],
    }
    return common + template_specific.get(template, [])


def format_output(result: dict, verbose: bool = True) -> str:
    """Format the full result as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("ALPHAFORGE — Strategy Generation Report")
    lines.append("=" * 60)

    lines.append("\n## STEP 1 — Parsed Intent")
    for k, v in result["intent"].items():
        lines.append(f"  {k}: {v}")

    v = result.get("validation", {})
    if v:
        status = "PASS ✓" if v["valid"] else "FAIL ✗"
        lines.append(f"\n## Spec Validation: {status}")
        for e in v.get("errors", []):
            lines.append(f"  ERROR: {e}")
        for w in v.get("warnings", []):
            lines.append(f"  WARN:  {w}")

    lines.append("\n## STEP 2 — Live CMC Market Context")
    mc = result["market_context"]
    lines.append(f"  Asset: {mc['asset']} @ ${mc['price']:,.4f}")
    lines.append(f"  24h change: {mc['price_change_24h']:+.2f}%  |  7d: {mc['price_change_7d']:+.2f}%")
    lines.append(f"  Fear & Greed: {mc['fear_greed_score']} — {mc['fear_greed_label']}")
    lines.append(f"  BTC Dominance: {mc['btc_dominance']:.1f}%")
    lines.append(f"  OHLCV data points loaded: {mc['data_points']}")

    lines.append("\n## STEP 3 — Feature Engineering")
    sig = result["regime"]["signals"]
    lines.append(f"  EMA20: {sig.get('ema_20', 'N/A'):.4f}  |  EMA50: {sig.get('ema_50', 'N/A'):.4f}")
    lines.append(f"  RSI14: {sig.get('rsi_14', 'N/A'):.1f}  |  MACD Hist: {sig.get('macd_histogram', 'N/A')}")
    lines.append(f"  Volume Z-score: {sig.get('volume_zscore', 'N/A')}")
    lines.append(f"  Realized Volatility: {sig.get('realized_volatility', 'N/A')}")

    lines.append("\n## STEP 4 — Market Regime Detection")
    r = result["regime"]
    lines.append(f"  Primary Regime: {r['primary'].replace('_', ' ').upper()}")
    if r["secondary"]:
        lines.append(f"  Secondary: {', '.join(r['secondary'])}")
    lines.append(f"  Confidence: {r['confidence'] * 100:.0f}%")
    lines.append(f"  {r['explanation']}")

    lines.append("\n## STEP 5 — Strategy Spec (YAML)")
    spec = result["spec"]
    lines.append(f"  strategy_type: {spec['strategy_type']}")
    if "entry_rules" in spec:
        lines.append("  entry_rules:")
        for rule in spec.get("entry_rules", {}).get("all", []):
            lines.append(f"    - {rule}")
    if "exit_rules" in spec:
        lines.append("  exit_rules:")
        for rule in spec.get("exit_rules", {}).get("any", []):
            lines.append(f"    - {rule}")
    rm = spec["risk_management"]
    lines.append(f"  risk: max_pos={rm.get('max_position_size_pct')}%, stop={rm.get('stop_loss_pct')}%, max_dd={rm.get('max_strategy_drawdown_pct')}%")

    lines.append("\n## STEP 6 — Backtest Results")
    bt = result["backtest"]
    lines.append(f"  Total Return:       {bt['total_return_pct']:+.2f}%")
    lines.append(f"  Buy & Hold Return:  {bt['buy_and_hold_return_pct']:+.2f}%")
    lines.append(f"  Max Drawdown:       -{bt['max_drawdown_pct']:.2f}%")
    lines.append(f"  Sharpe Ratio:       {bt['sharpe_ratio']:.2f}")
    lines.append(f"  Win Rate:           {bt['win_rate_pct']:.1f}%")
    lines.append(f"  Profit Factor:      {bt['profit_factor']:.2f}")
    lines.append(f"  Number of Trades:   {bt['number_of_trades']}")
    lines.append(f"  Exposure Time:      {bt['exposure_time_pct']:.1f}%")
    lines.append(f"  Final Equity:       ${bt['final_equity']:,.2f}")

    lines.append("\n## STEP 7 — Strategy Explanation")
    lines.append(result["explanation"])

    lines.append("\n## STEP 8 — Known Failure Modes")
    for i, fm in enumerate(result["failure_modes"], 1):
        lines.append(f"  {i}. {fm}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
