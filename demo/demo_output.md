# AlphaForge Demo Output
## Sample outputs from `python demo/run_demo.py --all`
## Generated: 2026-06-15 | Data: Live CMC + Binance

---

## Example 1 — BNB Momentum Strategy (Sentiment Guard)

**Input:**
```
Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.
```

**Output:**

```
STEP 1 — Parsed Intent
  asset: BNB | timeframe: 4h | style: momentum
  constraints: ['avoid_overheated_sentiment'] | risk_profile: moderate

Spec Validation: PASS ✓

STEP 2 — Live CMC Market Context
  Asset: BNB @ $616.12
  24h change: +0.91%  |  7d: +3.50%
  Fear & Greed: 23 — Fear
  BTC Dominance: 58.7%
  OHLCV data points loaded: 365

STEP 3 — Feature Engineering
  EMA20: 619.57  |  EMA50: 631.48
  RSI14: 47.5    |  MACD Hist: +0.43
  Volume Z-score: -1.17  |  Realized Volatility: 0.61

STEP 4 — Market Regime Detection
  Primary Regime: NEUTRAL (confidence 40%)
  No dominant regime detected. Mixed signals — reduce position size.

STEP 5 — Strategy Spec
  strategy_type: regime_aware_momentum
  entry_rules: close > ema_20, ema_20 > ema_50, macd > 0, rsi [50-70], vol_z > 0.8
  exit_rules: close < ema_20 OR macd < 0 OR rsi > 80
  risk: max_pos=25%, stop=7%, trailing=9%, max_dd=15%

STEP 6 — Backtest Results (365 days)
  Total Return:      -1.54%
  Buy & Hold Return: -18.36%   ← strategy outperformed by 16.8pp
  Max Drawdown:      -7.59%
  Sharpe Ratio:      -0.23
  Win Rate:          28.6% | Trades: 7 | Exposure: 13.7%
  Final Equity:      $9,846.10

STEP 7 — Explanation
  Strategy enters only when trend, momentum, and volume align.
  In a neutral/bearish regime it correctly reduced exposure,
  avoiding the -18.4% drawdown of passive holding.

STEP 8 — Failure Modes
  1. Sudden news-driven gap reversals
  2. Liquidity crises with elevated slippage
  3. Regime misclassification during transitions
  4. Low-volume false momentum signals
  5. MACD false crossovers in sideways markets
```

---

## Example 2 — BTC Panic Reversal (Conservative)

**Input:**
```
Create a BTC panic reversal strategy for extreme fear conditions with conservative risk.
```

**Output:**

```
STEP 1 — Parsed Intent
  asset: BTC | timeframe: 4h | style: mean_reversion
  constraints: ['panic_reversal'] | risk_profile: conservative

Spec Validation: PASS ✓

STEP 2 — Live CMC Market Context
  Asset: BTC @ $65,713.81
  24h change: +1.95%  |  7d: +4.06%
  Fear & Greed: 23 — Fear | BTC Dominance: 58.7%

STEP 4 — Market Regime Detection
  Primary Regime: BEARISH TREND (confidence 60%)
  Price below EMA20 < EMA50, RSI 41.6. Bearish trend in effect.

STEP 5 — Strategy Spec
  strategy_type: panic_reversal
  entry_rules: rsi < 30, fear_greed < 25, distance_ema50 < -12%, vol_z > 1.5
  exit_rules: close >= ema_20 OR rsi >= 55 OR take_profit >= 12%
  risk: max_pos=12%, stop=4%, max_dd=8%

STEP 6 — Backtest Results (365 days)
  Total Return:      -0.88%
  Buy & Hold Return: -42.42%   ← strategy outperformed by 41.5pp
  Max Drawdown:      -0.88%
  Sharpe: -1.55 | Trades: 1 | Exposure: 0.6%
  Final Equity: $9,911.73

Key insight: Strategy avoided 97% of the BTC drawdown by refusing to hold
through a sustained bearish trend. 1 trade entered near capitulation conditions.
```

---

## Example 3 — ETH Volatility Breakout (No-Trade in Chop)

**Input:**
```
Build an ETH volatility breakout strategy for low volatility accumulation phases.
```

**Output:**

```
STEP 4 — Market Regime Detection
  Primary Regime: HIGH VOLATILITY CHOP (confidence 14%)
  Realized volatility at 0.86 — choppy environment detected.

STEP 5 — Strategy Spec
  strategy_type: volatility_breakout
  entry_rules: realized_vol_percentile < 30, close > rolling_high_20, vol_z > 1.2
  NOTE: Entry conditions NOT met — strategy correctly declines to trade.

STEP 6 — Backtest Results (365 days)
  Total Return:      +0.00%   ← capital preserved
  Buy & Hold Return: -52.40%  ← passive holder lost half
  Max Drawdown:      -0.00%
  Trades: 0 | Exposure: 0%
  Final Equity: $10,000.00

Key insight: AlphaForge detected that ETH has been in sustained high-volatility chop
for the past year. The volatility breakout strategy correctly went dormant,
preserving 100% of capital vs -52% buy-and-hold.
This is regime-aware strategy generation working as designed.
```

---

## Running the Demo

```bash
# Default (BNB momentum)
python demo/run_demo.py

# All examples + charts
python demo/run_demo.py --all --chart

# Custom input
python demo/run_demo.py --input "Generate a SOL 1D breakout strategy" --chart

# Machine-readable JSON
python demo/run_demo.py --json
```

---

*Not financial advice. AlphaForge generates research-grade strategy specifications only.*
