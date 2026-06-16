"""
AlphaForge Visualizer — generates regime + equity curve charts.
Requires matplotlib (pip install matplotlib).
"""
import os


def _build_figure(result: dict, ohlcv: list[dict]):
    """
    Build the 3-panel chart figure:
      Panel 1: Price + EMA20 + EMA50 with regime shading
      Panel 2: RSI14 + Fear & Greed
      Panel 3: Strategy equity curve vs Buy-and-Hold

    Returns the matplotlib Figure (caller is responsible for saving/closing).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    closes = [c["close"] for c in ohlcv]
    times = list(range(len(closes)))

    regime = result["regime"]["primary"]
    bt = result["backtest"]
    equity_curve_sampled = bt.get("equity_curve", [])
    feat_signals = result["regime"]["signals"]
    fg_score = result["market_context"]["fear_greed_score"]
    initial_capital = result["spec"]["backtest"]["initial_capital"]

    # Reconstruct full equity curve from sampled (step=5 in backtester)
    # For the chart we interpolate linearly between sample points
    equity_full = []
    if equity_curve_sampled:
        for i, v in enumerate(equity_curve_sampled):
            equity_full.append(v)
            if i < len(equity_curve_sampled) - 1:
                next_v = equity_curve_sampled[i + 1]
                for j in range(1, 5):
                    equity_full.append(v + (next_v - v) * j / 5)

    # Buy-and-hold curve (start from warm-up bar 50)
    start = min(50, len(closes) - 1)
    bah = []
    if len(closes) > start:
        base = closes[start]
        for c in closes[start:]:
            bah.append(initial_capital * c / base)

    # EMA reconstruction from signals (approximate — use stored value for last bar)
    from .features import compute_features
    feat_series = compute_features(ohlcv)
    ema20_series = feat_series["ema_20"]
    ema50_series = feat_series["ema_50"]
    rsi_series = feat_series["rsi_14"]

    # ── Colors ──
    REGIME_COLORS = {
        "bullish_trend": "#c8f7c5",
        "bearish_trend": "#f7c5c5",
        "panic_reversal": "#f7e2c5",
        "sentiment_overheated": "#f7c5f0",
        "high_volatility_chop": "#e0e0e0",
        "low_volatility_accumulation": "#c5e8f7",
        "neutral": "#f5f5f5",
        "derivatives_crowded_long": "#f7d4c5",
        "derivatives_crowded_short": "#d4c5f7",
    }
    regime_color = REGIME_COLORS.get(regime, "#f5f5f5")

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), facecolor="#0f1117")
    fig.suptitle(
        f"AlphaForge — {result['intent']['asset']}/{result['intent']['timeframe']}  |  "
        f"Regime: {regime.replace('_', ' ').title()}  |  "
        f"Strategy: {result['spec']['strategy_type'].replace('_', ' ').title()}",
        color="white", fontsize=13, fontweight="bold", y=0.98,
    )

    for ax in axes:
        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="#aaaaaa", labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333344")

    # ── Panel 1: Price + EMAs ──
    ax1 = axes[0]
    ax1.plot(times, closes, color="#4fc3f7", linewidth=1.2, label="Price", zorder=3)
    ax1.plot(times, ema20_series, color="#ffb300", linewidth=1.0, linestyle="--", label="EMA20", zorder=2)
    ax1.plot(times, ema50_series, color="#ef5350", linewidth=1.0, linestyle="--", label="EMA50", zorder=2)
    ax1.axhspan(min(closes), max(closes), alpha=0.08, color=regime_color)
    ax1.set_ylabel("Price (USDT)", color="#aaaaaa", fontsize=9)
    ax1.legend(loc="upper left", fontsize=8, facecolor="#1a1d27", labelcolor="white", framealpha=0.8)
    ax1.set_title("Price + EMAs", color="#aaaaaa", fontsize=9, loc="right")
    # Regime label
    ax1.text(
        0.01, 0.92, f"Regime: {regime.replace('_', ' ').upper()}  (conf {result['regime']['confidence']*100:.0f}%)",
        transform=ax1.transAxes, color="white", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", facecolor=regime_color, alpha=0.7, edgecolor="none"),
    )

    # ── Panel 2: RSI + Fear & Greed ──
    ax2 = axes[1]
    rsi_clean = [v if v is not None else 50.0 for v in rsi_series]
    ax2.plot(times, rsi_clean, color="#ab47bc", linewidth=1.2, label="RSI 14", zorder=3)
    ax2.axhline(70, color="#ef5350", linewidth=0.7, linestyle=":", alpha=0.7)
    ax2.axhline(30, color="#66bb6a", linewidth=0.7, linestyle=":", alpha=0.7)
    ax2.axhline(50, color="#555566", linewidth=0.5, linestyle="-", alpha=0.5)
    ax2.fill_between(times, rsi_clean, 70, where=[r > 70 for r in rsi_clean],
                     alpha=0.25, color="#ef5350", label="Overbought")
    ax2.fill_between(times, rsi_clean, 30, where=[r < 30 for r in rsi_clean],
                     alpha=0.25, color="#66bb6a", label="Oversold")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI 14", color="#aaaaaa", fontsize=9)
    ax2.legend(loc="upper left", fontsize=8, facecolor="#1a1d27", labelcolor="white", framealpha=0.8)
    # Fear & Greed annotation
    fg_color = "#ef5350" if fg_score > 75 else "#66bb6a" if fg_score < 25 else "#ffb300"
    ax2.text(
        0.99, 0.87, f"Fear & Greed: {fg_score}",
        transform=ax2.transAxes, color=fg_color, fontsize=9, fontweight="bold",
        ha="right", bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1d27", alpha=0.8, edgecolor=fg_color),
    )
    ax2.set_title("RSI 14 + Sentiment", color="#aaaaaa", fontsize=9, loc="right")

    # ── Panel 3: Equity Curve vs Buy-and-Hold ──
    ax3 = axes[2]
    if equity_full and len(equity_full) > 1:
        eq_times = list(range(len(equity_full)))
        ax3.plot(eq_times, equity_full, color="#4caf50", linewidth=1.5,
                 label=f"AlphaForge ({bt['total_return_pct']:+.1f}%)", zorder=3)
    if bah and len(bah) > 1:
        bah_times = list(range(len(bah)))
        ax3.plot(bah_times, bah, color="#78909c", linewidth=1.2, linestyle="--",
                 label=f"Buy & Hold ({bt['buy_and_hold_return_pct']:+.1f}%)", zorder=2)
    ax3.axhline(initial_capital, color="#555566", linewidth=0.5, linestyle="-", alpha=0.6)
    ax3.set_ylabel("Portfolio Value (USDT)", color="#aaaaaa", fontsize=9)
    ax3.set_xlabel("Trading Days", color="#aaaaaa", fontsize=9)
    ax3.legend(loc="upper left", fontsize=8, facecolor="#1a1d27", labelcolor="white", framealpha=0.8)
    ax3.set_title("Equity Curve vs Buy-and-Hold", color="#aaaaaa", fontsize=9, loc="right")

    # Stats box on panel 3
    stats_text = (
        f"Sharpe: {bt['sharpe_ratio']:.2f}  |  "
        f"Max DD: -{bt['max_drawdown_pct']:.1f}%  |  "
        f"Win Rate: {bt['win_rate_pct']:.1f}%  |  "
        f"Trades: {bt['number_of_trades']}  |  "
        f"Exposure: {bt['exposure_time_pct']:.0f}%"
    )
    ax3.text(
        0.5, 0.04, stats_text, transform=ax3.transAxes,
        color="#aaaaaa", fontsize=8, ha="center",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#0f1117", alpha=0.9, edgecolor="#333344"),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def plot_results(result: dict, ohlcv: list[dict], output_path: str = None) -> str:
    """Render the chart and save it to disk. Returns the saved file path."""
    import matplotlib.pyplot as plt

    fig = _build_figure(result, ohlcv)
    if output_path is None:
        asset = result["intent"]["asset"]
        tf = result["intent"]["timeframe"]
        regime = result["regime"]["primary"]
        output_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "demo",
            f"alphaforge_{asset}_{tf}_{regime}.png",
        )
    output_path = os.path.abspath(output_path)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#0f1117")
    plt.close(fig)
    return output_path


def plot_results_bytes(result: dict, ohlcv: list[dict]) -> bytes:
    """
    Render the chart entirely in memory and return PNG bytes — used by
    serverless deployments (e.g. Vercel) where the filesystem is ephemeral
    and a saved file can't be relied on to still exist on the next request.
    """
    import io
    import matplotlib.pyplot as plt

    fig = _build_figure(result, ohlcv)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0f1117")
    plt.close(fig)
    return buf.getvalue()
