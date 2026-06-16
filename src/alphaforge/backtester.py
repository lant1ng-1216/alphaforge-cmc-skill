"""
Minimal backtester — reads a strategy spec + OHLCV data, runs simulated trades,
returns performance metrics comparable to buy-and-hold.
"""
import math
from typing import Optional
from .features import compute_features, ema as calc_ema


def _safe(v, default=0.0):
    return v if v is not None else default


def run_backtest(
    ohlcv: list[dict],
    spec: dict,
    initial_capital: float = 10_000,
    transaction_cost_bps: float = 10,
    slippage_bps: float = 5,
) -> dict:
    """
    Runs a simplified rule-based backtest on OHLCV data using strategy spec rules.
    Returns a performance summary dict.
    """
    closes = [c["close"] for c in ohlcv]
    volumes = [c["volume"] for c in ohlcv]
    feat = compute_features(ohlcv)
    strategy_type = spec.get("strategy_type", "regime_aware_momentum")
    rm = spec.get("risk_management", {})
    max_pos_pct = rm.get("max_position_size_pct", 25) / 100
    stop_loss_pct = rm.get("stop_loss_pct", 7) / 100
    trailing_stop_pct = rm.get("trailing_stop_pct", 9) / 100
    max_drawdown_limit = rm.get("max_strategy_drawdown_pct", 15) / 100
    cost_factor = 1 - (transaction_cost_bps + slippage_bps) / 10_000

    equity = initial_capital
    position = 0.0       # units held
    entry_price = 0.0
    peak_price = 0.0
    peak_equity = initial_capital
    trades: list[dict] = []
    equity_curve: list[float] = [initial_capital]
    exposure_bars = 0

    ema20 = feat["ema_20"]
    ema50 = feat["ema_50"]
    rsi14 = feat["rsi_14"]
    macd_data = feat["macd"]
    vol_z = feat["volume_zscore"]
    rv = feat["realized_volatility"]
    rh20 = feat["rolling_high_20"]

    start = 50  # warm-up period

    for i in range(start, len(ohlcv)):
        price = closes[i]
        e20 = _safe(ema20[i])
        e50 = _safe(ema50[i])
        r14 = _safe(rsi14[i], 50)
        mhist = _safe(macd_data[i]["histogram"] if macd_data[i] else None)
        vz = _safe(vol_z[i])
        rvol = _safe(rv[i], 0.5)
        rh = _safe(rh20[i], price)

        in_position = position > 0

        if in_position:
            exposure_bars += 1
            # Trailing stop
            if price > peak_price:
                peak_price = price
            trailing_stop_level = peak_price * (1 - trailing_stop_pct)
            stop_level = entry_price * (1 - stop_loss_pct)
            effective_stop = max(trailing_stop_level, stop_level)

            # Check exit conditions
            should_exit = False
            if strategy_type == "regime_aware_momentum":
                should_exit = (
                    price < e20
                    or mhist < 0
                    or r14 > 80
                    or price < effective_stop
                )
            elif strategy_type == "panic_reversal":
                holding_bars = len(trades[-1:]) and i - trades[-1].get("entry_bar", i)
                should_exit = (
                    price >= e20
                    or r14 >= 55
                    or (price - entry_price) / entry_price >= 0.12
                    or price < effective_stop
                )
            elif strategy_type == "sentiment_divergence":
                should_exit = price < e20 or r14 > 78 or price < effective_stop
            elif strategy_type == "volatility_breakout":
                should_exit = price < entry_price * 0.95 or mhist < 0 or price < effective_stop
            else:
                should_exit = price < e20 or price < effective_stop

            if should_exit:
                proceeds = position * price * cost_factor
                pnl = proceeds - position * entry_price
                equity += proceeds
                trades[-1]["exit_price"] = price
                trades[-1]["exit_bar"] = i
                trades[-1]["pnl"] = pnl
                trades[-1]["return_pct"] = (price - entry_price) / entry_price * 100
                position = 0.0

        # Check entry (only if flat)
        if not in_position:
            should_enter = False
            if strategy_type == "regime_aware_momentum":
                should_enter = (
                    price > e20 > e50
                    and mhist > 0
                    and 50 <= r14 <= 70
                    and vz > 0.8
                )
            elif strategy_type == "panic_reversal":
                should_enter = (
                    r14 < 30
                    and (price - e50) / e50 < -0.10
                    and vz > 1.5
                    and (i > 0 and price > closes[i - 1])
                )
            elif strategy_type == "sentiment_divergence":
                should_enter = (
                    price > e20
                    and vz > 0.7
                    and 40 <= r14 <= 65
                )
            elif strategy_type == "volatility_breakout":
                should_enter = (
                    rvol < 0.5
                    and price > rh * 1.001
                    and vz > 1.2
                )
            elif strategy_type == "no_trade":
                should_enter = False
            else:
                should_enter = price > e20 and mhist > 0

            if should_enter and equity > 0:
                capital_to_deploy = equity * max_pos_pct
                units = (capital_to_deploy / price) * cost_factor
                cost = units * price / cost_factor
                if cost <= equity:
                    position = units
                    entry_price = price
                    peak_price = price
                    equity -= cost
                    trades.append({"entry_price": price, "entry_bar": i, "units": units})

        # Mark-to-market equity
        portfolio_value = equity + position * price
        equity_curve.append(portfolio_value)

        # Max drawdown guard
        if portfolio_value > peak_equity:
            peak_equity = portfolio_value
        drawdown = (peak_equity - portfolio_value) / peak_equity
        if drawdown > max_drawdown_limit:
            # Force exit and stop trading
            if position > 0:
                proceeds = position * price * cost_factor
                equity += proceeds
                if trades:
                    trades[-1]["exit_price"] = price
                    trades[-1]["exit_bar"] = i
                    trades[-1]["pnl"] = proceeds - position * entry_price
                    trades[-1]["return_pct"] = (price - entry_price) / entry_price * 100
                position = 0.0
            break

    # Final liquidation
    final_price = closes[-1]
    if position > 0:
        proceeds = position * final_price * cost_factor
        equity += proceeds
        if trades and "exit_price" not in trades[-1]:
            trades[-1]["exit_price"] = final_price
            trades[-1]["exit_bar"] = len(ohlcv) - 1
            trades[-1]["pnl"] = proceeds - position * entry_price
            trades[-1]["return_pct"] = (final_price - entry_price) / entry_price * 100
        equity_curve[-1] = equity

    # Performance metrics
    total_return = (equity - initial_capital) / initial_capital * 100
    bah_return = (closes[-1] - closes[start]) / closes[start] * 100

    completed_trades = [t for t in trades if "pnl" in t]
    wins = [t for t in completed_trades if t["pnl"] > 0]
    losses = [t for t in completed_trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(completed_trades) * 100 if completed_trades else 0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    exposure_time = exposure_bars / (len(ohlcv) - start) * 100 if len(ohlcv) > start else 0

    # Sharpe (daily returns, annualized)
    daily_returns = []
    for j in range(1, len(equity_curve)):
        if equity_curve[j - 1] > 0:
            daily_returns.append((equity_curve[j] - equity_curve[j - 1]) / equity_curve[j - 1])
    if len(daily_returns) > 1:
        mean_r = sum(daily_returns) / len(daily_returns)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1))
        sharpe = (mean_r / std_r * math.sqrt(365)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "total_return_pct": round(total_return, 2),
        "buy_and_hold_return_pct": round(bah_return, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        "number_of_trades": len(completed_trades),
        "exposure_time_pct": round(exposure_time, 1),
        "final_equity": round(equity, 2),
        "equity_curve": [round(v, 2) for v in equity_curve[::5]],  # downsample for output
    }
