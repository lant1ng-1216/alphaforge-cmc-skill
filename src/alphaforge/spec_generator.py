"""
AlphaForge main pipeline — orchestrates the full flow from intent to strategy spec + backtest.
"""
import json
import math
from typing import Optional
from .cmc_adapter import CMCAdapter
from .intent_parser import parse_intent, parse_intent_auto, StrategyIntent
from .features import compute_features, latest_features
from .regime_classifier import classify_regime, RegimeResult
from .strategy_templates import select_template, build_spec
from .backtester import run_backtest, run_walk_forward_backtest
from .spec_validator import validate_spec
from .monte_carlo import run_monte_carlo
from .strategy_reviewer import review_strategy
from .bsc_adapter import get_bsc_ecosystem_signals
from .doctrine import build_doctrine_context, save_doctrine_record


def _round_sig(v: float, sig: int = 6) -> float:
    """
    Round to `sig` significant figures rather than a fixed decimal place —
    plain round(v, 4) collapses sub-cent memecoin prices (e.g. PEPE's
    0.0000028 EMA) to 0.0, destroying the value entirely.
    """
    if v == 0 or not math.isfinite(v):
        return v
    digits = sig - int(math.floor(math.log10(abs(v)))) - 1
    return round(v, max(digits, 0))


def resolve_asset(cmc: CMCAdapter, intent: StrategyIntent) -> dict:
    """
    Try each candidate ticker (in order of likely relevance) against live CMC
    data and use the first one that resolves. This lets AlphaForge handle any
    CMC-listed asset instead of silently defaulting to BNB when the text
    mentions a token outside a hardcoded shortlist.
    """
    candidates = intent.asset_candidates or [intent.asset]

    # Filter against the live CMC symbol list first so we don't burn a
    # get_quote call (and risk rate limits) on every noise word extracted
    # from the sentence — only call get_quote for symbols CMC actually lists.
    try:
        valid_symbols = cmc.get_symbol_set()
        filtered = [c for c in candidates if c in valid_symbols]
    except Exception:
        filtered = candidates  # symbol map unavailable; fall back to trying candidates directly

    to_try = filtered or candidates
    last_error: Optional[Exception] = None
    last_is_network = False
    for candidate in to_try:
        try:
            quote = cmc.get_quote(candidate)
            intent.asset = candidate
            return quote
        except Exception as exc:
            last_error = exc
            # Distinguish network/SSL failures from "symbol not found" so the
            # error message guides the user correctly.
            err_str = str(exc).lower()
            last_is_network = any(k in err_str for k in (
                "ssl", "eof", "timeout", "connection", "urlopen", "network",
                "gaierror", "remotedisconnected",
            ))
            continue

    tried = ", ".join(candidates)
    if last_is_network:
        raise ValueError(
            f"Network error while connecting to CoinMarketCap API "
            f"(SSL/connection failure). Check your internet connection or VPN "
            f"and try again. Last error: {last_error}"
        ) from last_error
    raise ValueError(
        f"Could not find a tradable asset on CoinMarketCap. Tried: {tried}. "
        f"Mention a valid ticker (e.g. BTC, ETH, SOL, SUI)."
    ) from last_error


def generate_strategy(user_input: str, cmc_api_key: str, step_callback=None) -> dict:
    """
    Full AlphaForge pipeline.

    Args:
        user_input: Natural language strategy request
        cmc_api_key: CoinMarketCap API key
        step_callback: optional callable(step_num, total, message) for progress reporting

    Returns:
        dict with keys: intent, market_context, regime, spec, backtest, explanation, failure_modes
    """
    def _step(n, msg):
        if step_callback:
            step_callback(n, 10, msg)

    cmc = CMCAdapter(cmc_api_key)

    # Step 1: Parse intent (LLM if ANTHROPIC_API_KEY is set, else regex)
    _step(1, "Parsing strategy intent…")
    intent, parse_method = parse_intent_auto(user_input)

    # Step 2: Resolve the asset against live CMC data (works for any
    # CMC-listed token, not just a hardcoded shortlist) and pull market context
    _step(2, f"Fetching live CMC market data…")
    quote = resolve_asset(cmc, intent)
    fg = cmc.get_fear_and_greed()
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
    _step(3, "Engineering technical features (EMA / RSI / MACD / vol)…")
    feat_series = compute_features(ohlcv)
    feat = latest_features(feat_series)
    # macd comes back as dict from latest_features
    if isinstance(feat.get("macd"), dict):
        feat["macd_histogram"] = feat["macd"].get("histogram")

    # Step 2b: BSC Ecosystem Layer — only triggers for BNB-native assets.
    # Fetches PancakeSwap DEX activity + BSC chain health from public endpoints
    # and injects a regime_hint that can boost/dampen classifier confidence.
    _step(2, "Fetching BSC ecosystem signals (PancakeSwap + chain health)…")
    bsc_signals = get_bsc_ecosystem_signals(intent.asset, cmc_api_key)

    # Step 3b: Live cross-check against CMC's own official technical analysis
    # and a market-wide derivatives/leverage snapshot, via the CMC Data MCP.
    # This is supplementary — if the MCP call fails (e.g. blocked from a
    # serverless IP, same class of issue as the Binance fallback), the core
    # pipeline still runs unaffected on AlphaForge's own computed features.
    live_cross_check = None
    cmc_ta, cmc_derivatives = cmc.get_live_cross_check_parallel(quote.get("cmc_id"))
    if cmc_ta or cmc_derivatives:
        live_cross_check = {}
        if cmc_ta:
            try:
                live_cross_check["cmc_official_rsi14"] = float(cmc_ta["rsi"]["rsi14"])
                live_cross_check["cmc_official_macd_histogram"] = float(cmc_ta["macd"]["histogram"])
                live_cross_check["alphaforge_rsi14"] = feat.get("rsi_14")
                live_cross_check["alphaforge_macd_histogram"] = feat.get("macd_histogram")
            except (KeyError, TypeError, ValueError):
                pass
        if cmc_derivatives:
            try:
                live_cross_check["market_funding_rate"] = cmc_derivatives.get("fundingRate", {}).get("current")
                live_cross_check["market_open_interest"] = cmc_derivatives.get("totalOpenInterest", {}).get("current")
                live_cross_check["market_oi_change_24h"] = cmc_derivatives.get("totalOpenInterest", {}).get("percentage_change_24h")
            except (KeyError, TypeError):
                pass

    # Step 4: Classify market regime
    _step(4, "Detecting market regime (8 regime types)…")
    bsc_regime_hint = bsc_signals.get("regime_hint") if bsc_signals else None
    bsc_confidence_boost = bsc_signals.get("confidence_boost", 0.0) if bsc_signals else 0.0
    regime_result: RegimeResult = classify_regime(
        feat=feat,
        fear_greed=fg["score"],
        price_change_24h=quote["percent_change_24h"],
        price_change_7d=quote["percent_change_7d"],
        volume_change_24h=quote.get("volume_change_24h"),
        bsc_regime_hint=bsc_regime_hint,
        bsc_confidence_boost=bsc_confidence_boost,
    )

    # Step 5: Select strategy template
    _step(5, "Selecting strategy template & building spec…")
    template_name = select_template(regime_result.primary, intent)

    # Step 6: Build strategy spec
    spec = build_spec(
        template_name=template_name,
        intent=intent,
        regime=regime_result.primary,
        secondary_regimes=regime_result.secondary,
        fear_greed=fg["score"],
    )

    # Step 6b: Validate spec
    _step(6, "Validating strategy spec schema…")
    validation = validate_spec(spec)

    # Step 7: Run backtest
    _step(7, "Running backtest + walk-forward consistency check…")
    backtest_results = run_backtest(
        ohlcv=ohlcv,
        spec=spec,
        initial_capital=spec["backtest"]["initial_capital"],
        transaction_cost_bps=spec["backtest"]["transaction_cost_bps"],
        slippage_bps=spec["backtest"]["slippage_bps"],
    )

    # Step 8b: Walk-forward consistency check — same fixed rules, independent
    # historical periods. Checks the edge isn't an artifact of one window.
    walk_forward_results = run_walk_forward_backtest(
        ohlcv=ohlcv,
        spec=spec,
        initial_capital=spec["backtest"]["initial_capital"],
        transaction_cost_bps=spec["backtest"]["transaction_cost_bps"],
        slippage_bps=spec["backtest"]["slippage_bps"],
        n_periods=2,
    )

    # Step 8c: Monte Carlo simulation (1000 bootstrap paths)
    _step(8, "Running Monte Carlo simulation (1000 paths)…")
    equity_curve_full = backtest_results.get("equity_curve_full", backtest_results.get("equity_curve", []))
    monte_carlo_results = run_monte_carlo(
        equity_curve=equity_curve_full,
        n_simulations=1000,
        initial_capital=spec["backtest"]["initial_capital"],
    )

    # Step 9: Three-layer Agent Review chain
    # Query the doctrine for prior runs in the same regime × strategy combination
    # so the Gatekeeper can reason with historical context, not just current data.
    _step(9, "Running three-layer strategy review (Risk → Regime → Gatekeeper)…")
    doctrine_context = build_doctrine_context(regime_result.primary, template_name)
    review_results = review_strategy(
        spec=spec,
        features=feat,
        regime_primary=regime_result.primary,
        intent=intent.to_dict(),
        backtest=backtest_results,
        walk_forward=walk_forward_results,
        monte_carlo=monte_carlo_results,
        doctrine_context=doctrine_context,
    )

    # Persist this run to the doctrine so future Gatekeeper calls can learn from it.
    try:
        save_doctrine_record(
            asset=intent.asset,
            regime=regime_result.primary,
            strategy_type=template_name,
            timeframe=intent.timeframe,
            style=intent.style,
            backtest=backtest_results,
            monte_carlo=monte_carlo_results,
            gatekeeper_verdict=review_results.get("final_verdict", "UNKNOWN"),
            gatekeeper_confidence=review_results.get("confidence", 0),
        )
    except Exception:
        pass  # doctrine write failure must never break the main pipeline

    # Step 10: Build explanation + failure modes
    _step(10, "Generating report, explanation & failure modes…")
    explanation = _build_explanation(intent, regime_result, template_name, backtest_results)
    failure_modes = _build_failure_modes(template_name, regime_result)

    return {
        "intent": intent.to_dict(),
        "intent_parse_method": parse_method,
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
            "signals": {k: (_round_sig(v) if isinstance(v, float) else v)
                        for k, v in regime_result.signals.items() if v is not None},
        },
        "spec": spec,
        "backtest": backtest_results,
        "walk_forward": walk_forward_results,
        "live_cross_check": live_cross_check,
        "bsc_ecosystem": bsc_signals,
        "monte_carlo": monte_carlo_results,
        "strategy_review": review_results,
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


def _fmt_price(v) -> str:
    """
    Adaptive-precision price formatting. Fixed 4-decimal formatting reads as
    "$0.0000" for sub-cent memecoins (PEPE, SHIB, BONK...) even though the
    real price is e.g. $0.0000089 — show enough decimals to keep significant
    figures instead of always truncating to 4 places.
    """
    if v is None:
        return "N/A"
    v = float(v)
    if v == 0:
        return "0.0000"
    if abs(v) >= 1:
        return f"{v:,.4f}"
    decimals = max(4, -math.floor(math.log10(abs(v))) + 3)
    return f"{v:.{decimals}f}"


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
    lines.append(f"  Asset: {mc['asset']} @ ${_fmt_price(mc['price'])}")
    lines.append(f"  24h change: {mc['price_change_24h']:+.2f}%  |  7d: {mc['price_change_7d']:+.2f}%")
    lines.append(f"  Fear & Greed: {mc['fear_greed_score']} — {mc['fear_greed_label']}")
    lines.append(f"  BTC Dominance: {mc['btc_dominance']:.1f}%")
    lines.append(f"  OHLCV data points loaded: {mc['data_points']}")

    lines.append("\n## STEP 3 — Feature Engineering")
    sig = result["regime"]["signals"]
    lines.append(f"  EMA20: {_fmt_price(sig.get('ema_20'))}  |  EMA50: {_fmt_price(sig.get('ema_50'))}")
    lines.append(f"  RSI14: {sig.get('rsi_14', 'N/A'):.1f}  |  MACD Hist: {sig.get('macd_histogram', 'N/A')}")
    lines.append(f"  Volume Z-score: {sig.get('volume_zscore', 'N/A')}")
    lines.append(f"  Realized Volatility: {sig.get('realized_volatility', 'N/A')}")

    lcc = result.get("live_cross_check")
    if lcc:
        lines.append("\n## STEP 3b — Live Cross-Check (CMC Data MCP)")
        if "cmc_official_rsi14" in lcc:
            lines.append(
                f"  RSI14 — AlphaForge: {lcc.get('alphaforge_rsi14')}  |  "
                f"CMC official: {lcc['cmc_official_rsi14']}"
            )
            lines.append(
                f"  MACD Hist — AlphaForge: {lcc.get('alphaforge_macd_histogram')}  |  "
                f"CMC official: {lcc['cmc_official_macd_histogram']}"
            )
        if "market_funding_rate" in lcc:
            lines.append(
                f"  Market-wide funding rate: {lcc['market_funding_rate']}  |  "
                f"Open interest: {lcc.get('market_open_interest')} "
                f"({lcc.get('market_oi_change_24h')} 24h)"
            )

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

    wf = result.get("walk_forward") or []
    if wf:
        lines.append("\n## STEP 6b — Walk-Forward Consistency Check")
        lines.append("  Same fixed rules, independent historical periods (no re-fitting):")
        for p in wf:
            label = p["period_label"].replace("_", " ").title()
            lines.append(
                f"    {label} ({p['period_bars']} bars): "
                f"return {p['total_return_pct']:+.2f}% vs B&H {p['buy_and_hold_return_pct']:+.2f}%, "
                f"Sharpe {p['sharpe_ratio']:.2f}, max DD {p['max_drawdown_pct']:.1f}%, trades {p['number_of_trades']}"
            )

    lines.append("\n## STEP 7 — Strategy Explanation")
    lines.append(result["explanation"])

    lines.append("\n## STEP 8 — Known Failure Modes")
    for i, fm in enumerate(result["failure_modes"], 1):
        lines.append(f"  {i}. {fm}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def print_rich_output(result: dict, S: dict = None) -> None:
    """
    Print a rich-formatted strategy report to the terminal.
    S: bilingual string dict from run_demo.STRINGS['en'/'zh']. Defaults to English.
    Falls back to plain format_output if rich is unavailable.
    """
    # Default English strings (inline fallback so this module stays self-contained)
    _DEFAULT_S = {
        "pass": "PASS ✓", "fail": "FAIL ✗", "warn_lbl": "WARN", "err_lbl": "ERROR",
        "val_title": "Spec Validation",
        "s1_title": "STEP 1 — Parsed Intent",
        "s2_title": "STEP 2 — Live CMC Market Context",
        "s2b_title": "STEP 2b — BSC Ecosystem Layer (PancakeSwap + Chain Health)",
        "s3_title": "STEP 3 — Feature Engineering",
        "s3b_title": "STEP 3b — Live Cross-Check (CMC Data MCP)",
        "s4_title": "STEP 4 — Market Regime Detection",
        "s5_title": "STEP 5 — Strategy Spec",
        "s6_title": "STEP 6 — Backtest Results",
        "s6b_title": "STEP 6b — Walk-Forward Consistency Check",
        "s7_title": "STEP 7 — Strategy Explanation",
        "s8_title": "STEP 8 — Known Failure Modes",
        "summary_title": "AlphaForge — Executive Summary",
        "bt_cols": ["Metric", "Value"],
        "bt_rows": {
            "total_return": "Total Return", "bah_return": "Buy & Hold Return",
            "alpha": "Alpha vs B&H", "max_dd": "Max Drawdown", "sharpe": "Sharpe Ratio",
            "win_rate": "Win Rate", "profit_factor": "Profit Factor",
            "n_trades": "Number of Trades", "exposure": "Exposure Time",
            "final_equity": "Final Equity",
        },
        "wf_cols": ["Period", "Bars", "Return", "vs B&H", "Sharpe", "Max DD", "Trades"],
        "fields": {
            "asset": "Asset", "24h_7d": "24h / 7d", "fg": "Fear & Greed",
            "btc_dom": "BTC Dominance", "ohlcv_bars": "OHLCV bars",
            "ema": "EMA20 / EMA50", "rsi": "RSI14", "macd": "MACD Histogram",
            "vol_z": "Volume Z-score", "real_vol": "Realized Vol",
            "primary_regime": "Primary Regime", "secondary": "Secondary",
            "confidence": "Confidence", "strategy_type": "strategy_type",
            "entry_rules": "entry_rules", "exit_rules": "exit_rules", "risk": "risk",
            "rsi14_cross": "RSI14", "macd_cross": "MACD Hist",
            "funding": "Funding Rate", "oi": "Open Interest",
        },
        "entry_arrow": "▸", "exit_arrow": "◂",
    }
    if S is None:
        S = _DEFAULT_S

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.rule import Rule
        from rich import box
    except ImportError:
        print(format_output(result))
        return

    console = Console()
    F = S["fields"]

    def section(title: str):
        console.print(Rule(f"[bold blue]{title}[/bold blue]", style="blue"))

    def _ret(v: float) -> str:
        color = "green" if v >= 0 else "red"
        sign = "+" if v >= 0 else ""
        return f"[{color}]{sign}{v:.2f}%[/{color}]"

    # ── 1. Parsed Intent ────────────────────────────────────────────────────
    section(S["s1_title"])
    parse_method = result.get("intent_parse_method", "regex")
    if parse_method == "llm":
        console.print("  [bold green]✦ AI-powered intent parsing (DeepSeek)[/bold green]")
    else:
        console.print("  [dim]✧ Rule-based intent parsing[/dim]")
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim cyan", no_wrap=True)
    t.add_column()
    for k, v in result["intent"].items():
        t.add_row(k, str(v))
    console.print(t)

    val = result.get("validation", {})
    if val:
        status_text = f"[bold green]{S['pass']}[/bold green]" if val["valid"] else f"[bold red]{S['fail']}[/bold red]"
        console.print(f"  {S['val_title']}: {status_text}")
        for e in val.get("errors", []):
            console.print(f"  [red]{S['err_lbl']}:[/red] {e}")
        for w in val.get("warnings", []):
            console.print(f"  [yellow]{S['warn_lbl']}:[/yellow]  {w}")

    # ── 2. Market Context ───────────────────────────────────────────────────
    section(S["s2_title"])
    mc = result["market_context"]
    chg24 = mc["price_change_24h"]
    chg7  = mc["price_change_7d"]
    chg24_str = f"[green]+{chg24:.2f}%[/green]" if chg24 >= 0 else f"[red]{chg24:.2f}%[/red]"
    chg7_str  = f"[green]+{chg7:.2f}%[/green]"  if chg7  >= 0 else f"[red]{chg7:.2f}%[/red]"
    fg_score  = mc["fear_greed_score"]
    fg_color  = "green" if fg_score >= 60 else ("red" if fg_score <= 30 else "yellow")

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim cyan", no_wrap=True)
    t.add_column()
    t.add_row(F["asset"],    f"[bold]{mc['asset']}[/bold]  @  [bold yellow]${_fmt_price(mc['price'])}[/bold yellow]")
    t.add_row(F["24h_7d"],   f"{chg24_str}  /  {chg7_str}")
    t.add_row(F["fg"],       f"[{fg_color}]{fg_score} — {mc['fear_greed_label']}[/{fg_color}]")
    t.add_row(F["btc_dom"],  f"{mc['btc_dominance']:.1f}%")
    t.add_row(F["ohlcv_bars"], str(mc["data_points"]))
    console.print(t)

    # ── 3. Feature Engineering ──────────────────────────────────────────────
    section(S["s3_title"])
    sig = result["regime"]["signals"]
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim cyan", no_wrap=True)
    t.add_column()
    t.add_row(F["ema"],   f"{_fmt_price(sig.get('ema_20'))}  /  {_fmt_price(sig.get('ema_50'))}")
    rsi = sig.get("rsi_14")
    rsi_color = "red" if rsi and rsi > 70 else ("green" if rsi and rsi < 30 else "white")
    t.add_row(F["rsi"],   f"[{rsi_color}]{rsi:.1f}[/{rsi_color}]" if rsi else "N/A")
    t.add_row(F["macd"],  str(sig.get("macd_histogram", "N/A")))
    t.add_row(F["vol_z"], str(sig.get("volume_zscore", "N/A")))
    t.add_row(F["real_vol"], str(sig.get("realized_volatility", "N/A")))
    console.print(t)

    lcc = result.get("live_cross_check")
    if lcc:
        section(S["s3b_title"])
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column(style="dim cyan", no_wrap=True)
        t.add_column()
        if "cmc_official_rsi14" in lcc:
            t.add_row(F["rsi14_cross"], f"AlphaForge {lcc.get('alphaforge_rsi14')}  vs  CMC {lcc['cmc_official_rsi14']}")
            t.add_row(F["macd_cross"],  f"AlphaForge {lcc.get('alphaforge_macd_histogram')}  vs  CMC {lcc['cmc_official_macd_histogram']}")
        if "market_funding_rate" in lcc:
            t.add_row(F["funding"], str(lcc["market_funding_rate"]))
            t.add_row(F["oi"],      f"{lcc.get('market_open_interest')}  ({lcc.get('market_oi_change_24h')} 24h)")
        console.print(t)

    # ── 2b. BSC Ecosystem Layer ─────────────────────────────────────────────
    bsc = result.get("bsc_ecosystem")
    if bsc and bsc.get("bsc_native"):
        section(S.get("s2b_title", "STEP 2b — BSC Ecosystem Layer (PancakeSwap + Chain Health)"))
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column(style="dim cyan", no_wrap=True)
        t.add_column()
        dex = bsc.get("pancakeswap", {})
        chain = bsc.get("bsc_chain", {})
        if dex.get("available"):
            vol = dex.get("pancakeswap_volume_24h_usd", 0)
            vol_str = f"${vol/1e6:.1f}M" if vol >= 1e6 else f"${vol:,}"
            t.add_row("PancakeSwap 24h vol", vol_str)
            t.add_row("DEX activity", f"[bold]{dex.get('dex_activity_label', 'N/A')}[/bold]")
        if chain.get("available"):
            t.add_row("BSC avg block time", f"{chain.get('avg_block_time_sec')}s")
            t.add_row("BSC network health", f"[bold]{chain.get('network_health', 'N/A')}[/bold]")
        signal_color = "green" if bsc.get("bsc_signal") == "ecosystem_active" else ("red" if bsc.get("bsc_signal") == "ecosystem_quiet" else "yellow")
        t.add_row("BSC composite signal", f"[{signal_color}]{bsc.get('bsc_signal', 'N/A')}[/{signal_color}]")
        if bsc.get("regime_hint"):
            t.add_row("Regime hint injected", f"[dim]{bsc['regime_hint']} (confidence boost {bsc['confidence_boost']:+.0%})[/dim]")
        console.print(t)

    # ── 4. Regime ───────────────────────────────────────────────────────────
    section(S["s4_title"])
    r = result["regime"]
    regime_label = r["primary"].replace("_", " ").upper()
    conf_pct = r["confidence"] * 100
    conf_color = "green" if conf_pct >= 70 else ("yellow" if conf_pct >= 50 else "red")
    console.print(f"  {F['primary_regime']}:  [bold magenta]{regime_label}[/bold magenta]")
    if r["secondary"]:
        console.print(f"  {F['secondary']}:       [dim]{', '.join(r['secondary'])}[/dim]")
    console.print(f"  {F['confidence']}:      [{conf_color}]{conf_pct:.0f}%[/{conf_color}]")
    console.print(f"  [italic]{r['explanation']}[/italic]")
    console.print()

    # ── 5. Strategy Spec ────────────────────────────────────────────────────
    section(S["s5_title"])
    spec = result["spec"]
    console.print(f"  {F['strategy_type']}:  [bold yellow]{spec['strategy_type']}[/bold yellow]")
    ea = S["entry_arrow"]
    xa = S["exit_arrow"]
    if "entry_rules" in spec:
        console.print(f"  [cyan]{F['entry_rules']}:[/cyan]")
        for rule in spec.get("entry_rules", {}).get("all", []):
            console.print(f"    [green]{ea}[/green] {rule}")
    if "exit_rules" in spec:
        console.print(f"  [cyan]{F['exit_rules']}:[/cyan]")
        for rule in spec.get("exit_rules", {}).get("any", []):
            console.print(f"    [red]{xa}[/red] {rule}")
    rm = spec["risk_management"]
    console.print(
        f"  {F['risk']}:  max_pos [bold]{rm.get('max_position_size_pct')}%[/bold]  "
        f"stop [bold red]{rm.get('stop_loss_pct')}%[/bold red]  "
        f"max_dd [bold red]{rm.get('max_strategy_drawdown_pct')}%[/bold red]"
    )

    # Full YAML spec block
    import json as _json
    _yaml_lines = []
    _yaml_lines.append(f"version: {spec.get('version', '1.0')}")
    _yaml_lines.append(f"generated_by: {spec.get('generated_by', 'AlphaForge')}")
    _yaml_lines.append(f"asset: {spec.get('asset', '')}/{spec.get('quote_asset', 'USDT')}")
    _yaml_lines.append(f"timeframe: {spec.get('timeframe', '')}")
    _yaml_lines.append(f"strategy_type: {spec.get('strategy_type', '')}")
    _yaml_lines.append(f"market_regime: {spec.get('market_regime', {}).get('primary', '')}")
    er = spec.get("entry_rules", {}).get("all", [])
    _yaml_lines.append("entry_rules:")
    for _r in er:
        _yaml_lines.append(f"  - {_r}")
    xr = spec.get("exit_rules", {}).get("any", [])
    _yaml_lines.append("exit_rules:")
    for _r in xr:
        _yaml_lines.append(f"  - {_r}")
    _yaml_lines.append("risk_management:")
    for _k, _v in rm.items():
        _yaml_lines.append(f"  {_k}: {_v}")
    bc = spec.get("backtest", {})
    _yaml_lines.append("backtest_config:")
    for _k, _v in bc.items():
        _yaml_lines.append(f"  {_k}: {_v}")
    em = spec.get("evaluation_metrics", [])
    _yaml_lines.append("evaluation_metrics:")
    for _m in em:
        _yaml_lines.append(f"  - {_m}")
    from rich.syntax import Syntax
    console.print(Syntax("\n".join(_yaml_lines), "yaml", theme="monokai", line_numbers=False, background_color="default"))
    console.print()

    # ── 6. Backtest ─────────────────────────────────────────────────────────
    section(S["s6_title"])
    bt = result["backtest"]
    alpha = bt["total_return_pct"] - bt["buy_and_hold_return_pct"]
    BR = S["bt_rows"]

    t = Table(box=box.ROUNDED, show_header=True, header_style="bold blue", padding=(0, 2))
    t.add_column(S["bt_cols"][0], style="dim", no_wrap=True)
    t.add_column(S["bt_cols"][1], justify="right")
    t.add_row(BR["total_return"],  _ret(bt["total_return_pct"]))
    t.add_row(BR["bah_return"],    _ret(bt["buy_and_hold_return_pct"]))
    t.add_row(BR["alpha"],         _ret(alpha))
    t.add_row(BR["max_dd"],        f"[red]-{bt['max_drawdown_pct']:.2f}%[/red]")
    sharpe = bt["sharpe_ratio"]
    s_color = "green" if sharpe >= 1.0 else ("yellow" if sharpe >= 0.5 else "red")
    t.add_row(BR["sharpe"],        f"[{s_color}]{sharpe:.2f}[/{s_color}]")
    t.add_row(BR["win_rate"],      f"{bt['win_rate_pct']:.1f}%")
    t.add_row(BR["profit_factor"], f"{bt['profit_factor']:.2f}")
    t.add_row(BR["n_trades"],      str(bt["number_of_trades"]))
    t.add_row(BR["exposure"],      f"{bt['exposure_time_pct']:.1f}%")
    t.add_row(BR["final_equity"],  f"[bold]${bt['final_equity']:,.2f}[/bold]")
    console.print(t)

    # ── 6b. Walk-Forward ────────────────────────────────────────────────────
    wf = result.get("walk_forward") or []
    if wf:
        section(S["s6b_title"])
        wc = S["wf_cols"]
        wt = Table(box=box.ROUNDED, header_style="bold blue", padding=(0, 2))
        for col in wc:
            wt.add_column(col, justify="right" if col not in (wc[0],) else "left",
                          style="dim" if col == wc[0] else "")
        for p in wf:
            # Compact label: "period_1_of_2" → "P1/2"
            raw = p["period_label"]
            import re as _re
            m = _re.search(r"(\d+)_of_(\d+)", raw)
            label = f"P{m.group(1)}/{m.group(2)}" if m else raw.replace("_", " ").title()
            wt.add_row(
                label,
                str(p["period_bars"]),
                _ret(p["total_return_pct"]),
                _ret(p["buy_and_hold_return_pct"]),
                f"{p['sharpe_ratio']:.2f}",
                f"[red]-{p['max_drawdown_pct']:.1f}%[/red]",
                str(p["number_of_trades"]),
            )
        console.print(wt)

    # ── 6c. Monte Carlo ─────────────────────────────────────────────────────
    mc = result.get("monte_carlo") or {}
    if mc and "error" not in mc:
        mc_title = "STEP 6c — Monte Carlo Simulation (1000 paths)" if not S.get("summary_title", "").startswith("AlphaForge — 执行") else "STEP 6c — 蒙特卡洛模拟（1000 次路径）"
        section(mc_title)
        ret = mc.get("total_return", {})
        sh  = mc.get("sharpe_ratio", {})
        dd  = mc.get("max_drawdown_pct", {})
        prob_pos = mc.get("probability_positive_return_pct", 0)
        prob_sh1 = mc.get("probability_sharpe_gt_1_pct", 0)
        prob_dd  = mc.get("probability_large_drawdown_pct", 0)

        mc_t = Table(box=box.ROUNDED, header_style="bold blue", padding=(0, 2))
        mc_t.add_column("Metric", style="dim", no_wrap=True)
        mc_t.add_column("p5",  justify="right")
        mc_t.add_column("p25", justify="right")
        mc_t.add_column("p50 (median)", justify="right")
        mc_t.add_column("p75", justify="right")
        mc_t.add_column("p95", justify="right")
        mc_t.add_row(
            "Total Return",
            _ret(ret.get("p5", 0)), _ret(ret.get("p25", 0)),
            _ret(ret.get("p50", 0)), _ret(ret.get("p75", 0)),
            _ret(ret.get("p95", 0)),
        )
        sh_p50 = sh.get("p50", 0)
        sh_color = "green" if sh_p50 >= 1 else ("yellow" if sh_p50 >= 0.5 else "red")
        mc_t.add_row(
            "Sharpe Ratio",
            f"{sh.get('p5', 0):.2f}", "—",
            f"[{sh_color}]{sh_p50:.2f}[/{sh_color}]", "—",
            f"{sh.get('p95', 0):.2f}",
        )
        mc_t.add_row(
            "Max Drawdown",
            "—", "—",
            f"[yellow]{dd.get('p50', 0):.1f}%[/yellow]", "—",
            f"[red]{dd.get('p95', 0):.1f}%[/red]",
        )
        console.print(mc_t)
        if prob_pos is not None:
            prob_color = "green" if prob_pos >= 60 else ("yellow" if prob_pos >= 40 else "red")
            console.print(
                f"  P(positive return) [{prob_color}]{prob_pos:.0f}%[/{prob_color}]  |  "
                f"P(Sharpe > 1) {prob_sh1:.0f}%  |  "
                f"P(drawdown > 20%) [red]{prob_dd:.0f}%[/red]"
            )
        else:
            note = mc.get("note", "No trades — Monte Carlo not applicable.")
            console.print(f"  [dim]{note}[/dim]")
        console.print()

    # ── 9. Strategy Review ──────────────────────────────────────────────────
    rev = result.get("strategy_review") or {}
    if rev:
        rev_title = "STEP 9 — Strategy Review (3-Agent Chain)" if not S.get("summary_title", "").startswith("AlphaForge — 执行") else "STEP 9 — 策略审核（三层 Agent 链）"
        section(rev_title)
        final_v = rev.get("final_verdict", "")
        conf = rev.get("confidence", 0)
        verdict_color = {
            "APPROVED": "bold green",
            "APPROVED_WITH_WARNINGS": "bold yellow",
            "CONDITIONALLY_APPROVED": "bold yellow",
            "REJECTED": "bold red",
        }.get(final_v, "white")
        import os as _os
        gk_mode = "[bold green]DeepSeek LLM[/bold green]" if _os.getenv("DEEPSEEK_API_KEY") else "[dim]rule-based fallback[/dim]"
        doctrine_n = rev.get("doctrine_records_consulted", 0)
        doctrine_label = (
            f"  [dim]📚 Doctrine: [bold]{doctrine_n}[/bold] prior run{'s' if doctrine_n != 1 else ''} consulted[/dim]"
            if doctrine_n > 0 else
            "  [dim]📚 Doctrine: first run in this regime × strategy combination[/dim]"
        )
        console.print(f"  [{verdict_color}]{final_v}[/{verdict_color}]  (confidence {conf}%)  [dim]Gatekeeper: {gk_mode}[/dim]")
        console.print(doctrine_label)
        console.print(f"  [italic]{rev.get('summary', '')}[/italic]")
        console.print()

        for agent_key, label in [("risk_agent", "RiskAgent"), ("regime_agent", "RegimeAgent")]:
            agent = rev.get(agent_key, {})
            av = agent.get("verdict", "pass")
            av_color = "green" if av == "pass" else ("yellow" if av == "warn" else "red")
            console.print(f"  [bold]{label}[/bold]  verdict: [{av_color}]{av.upper()}[/{av_color}]  (confidence {agent.get('confidence', 1.0):.0%})")
            for chk in agent.get("checks", []):
                cv = chk.get("verdict", "pass")
                cc = "green" if cv == "pass" else ("yellow" if cv == "warn" else "red")
                icon = "✅" if cv == "pass" else ("⚠️ " if cv == "warn" else "❌")
                console.print(f"    {icon} [{cc}]{chk.get('name', '')}:[/{cc}] {chk.get('message', '')}")
            console.print()

        if rev.get("warnings"):
            console.print("  [yellow]Gatekeeper warnings:[/yellow]")
            for w in rev["warnings"]:
                console.print(f"    [yellow]▸[/yellow] {w}")
        if rev.get("rejections"):
            console.print("  [red]Gatekeeper rejections:[/red]")
            for r in rev["rejections"]:
                console.print(f"    [red]✗[/red] {r}")
        console.print()

    # ── 7. Explanation ──────────────────────────────────────────────────────
    section(S["s7_title"])
    console.print(f"  {result['explanation']}\n")

    # ── 8. Failure Modes ────────────────────────────────────────────────────
    section(S["s8_title"])
    for i, fm in enumerate(result["failure_modes"], 1):
        console.print(f"  [yellow]{i}.[/yellow] {fm}")

    # ── Summary Panel ───────────────────────────────────────────────────────
    console.print()
    r = result["regime"]
    bt = result["backtest"]
    spec = result["spec"]
    regime_label = r["primary"].replace("_", " ").title()
    strategy_label = spec["strategy_type"].replace("_", " ").title()
    explanation_first = r["explanation"].split(".")[0]
    alpha = bt["total_return_pct"] - bt["buy_and_hold_return_pct"]

    is_zh = S.get("summary_title", "").startswith("AlphaForge — 执行")
    if is_zh:
        summary = (
            f"市场机制：{regime_label}。\n"
            f"推荐策略：{strategy_label}。\n"
            f"依据：{explanation_first}。\n"
            f"回测超额收益：{alpha:+.1f}pp vs 买入持有，最大回撤 {bt['max_drawdown_pct']:.1f}%，夏普 {bt['sharpe_ratio']:.2f}。"
        )
    else:
        summary = (
            f"Market regime: {regime_label}.\n"
            f"Recommended strategy: {strategy_label}.\n"
            f"Reason: {explanation_first}.\n"
            f"Backtest alpha: {alpha:+.1f}pp vs buy-and-hold, max DD {bt['max_drawdown_pct']:.1f}%, Sharpe {bt['sharpe_ratio']:.2f}."
        )

    console.print(Panel(
        f"[bold]{summary}[/bold]",
        title=f"[bold blue]{S['summary_title']}[/bold blue]",
        border_style="blue",
        padding=(1, 4),
    ))
    console.print()

    # ── Auto-generate chart ─────────────────────────────────────────────────
    ohlcv = result.get("_ohlcv")
    if ohlcv:
        try:
            from .visualizer import plot_results
            chart_path = plot_results(result, ohlcv)
            chart_label = "图表已保存" if is_zh else "Chart saved"
            chart_hint  = "用图片查看器打开，或在 demo/ 目录下查找" if is_zh else "Open with any image viewer — saved in demo/"
            console.print(
                f"  [bold green]📊 {chart_label}[/bold green]  [cyan]{chart_path}[/cyan]\n"
                f"  [dim]{chart_hint}[/dim]"
            )
            console.print()
        except Exception:
            pass
