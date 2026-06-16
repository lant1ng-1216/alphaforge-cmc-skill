# AlphaForge Demo Script
## From Natural Language to Backtestable Crypto Strategy in 60 Seconds

---

### Step 1 — User Input

```text
Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.
```

Run:
```bash
python demo/run_demo.py --input "Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment." --chart
```

---

### Step 2 — Parsed Intent

AlphaForge extracts the structured strategy intent:

```yaml
asset: BNB
timeframe: 4h
style: momentum
constraints:
  - avoid_overheated_sentiment
risk_profile: moderate
```

---

### Step 3 — Live CMC Market Context

AlphaForge pulls real-time data from CoinMarketCap Agent Hub:

- Price, 24h/7d change
- Volume and volume change
- Fear & Greed index
- BTC dominance
- 365 days of OHLCV via Binance public API

---

### Step 4 — Feature Engineering

Computed from OHLCV + CMC data:

| Feature | Value |
|---|---|
| EMA20 | ~619 |
| EMA50 | ~631 |
| RSI14 | ~47 |
| MACD Histogram | +0.37 |
| Volume Z-score | -1.17 |
| Realized Volatility | 0.61 |

---

### Step 5 — Market Regime Detection

```
Primary Regime: NEUTRAL (confidence 40%)
Explanation: No dominant regime. Mixed signals — reduce position size.
```

---

### Step 6 — Strategy Spec (YAML)

Machine-readable, backtestable output:

```yaml
strategy_type: regime_aware_momentum
entry_rules:
  all:
    - close > ema_20
    - ema_20 > ema_50
    - macd_histogram > 0
    - rsi_14 >= 50
    - rsi_14 <= 70
    - volume_zscore > 0.8
exit_rules:
  any:
    - close < ema_20
    - macd_histogram < 0
    - rsi_14 > 80 AND rsi_14_declining == true
risk_management:
  max_position_size_pct: 25
  stop_loss_pct: 7
  trailing_stop_pct: 9
  max_strategy_drawdown_pct: 15
```

---

### Step 7 — Backtest Results

```
Total Return:      -1.5%
Buy & Hold Return: -18.5%
Outperformance:    +16.9pp
Max Drawdown:      -7.6%
Sharpe Ratio:      -0.23
Win Rate:          28.6%
Trades:            7
Exposure:          14%
```

**Key insight**: AlphaForge preserved capital by refusing to trade during regime uncertainty. Buy-and-hold lost 18.5%.

---

### Step 8 — Strategy Explanation

```
This strategy enters only when trend, momentum, and volume align.
It avoids entries when sentiment is overheated or volume does not confirm.
In a neutral/bearish regime, the strategy correctly reduced exposure,
avoiding the -18.5% drawdown of passive holding.
```

---

### Risk Disclaimer

This tool generates research-grade strategy specifications for educational and analytical purposes only.
It does not execute trades. Past backtest results do not guarantee future performance.
All output should be independently validated before any live deployment.

Not financial advice.
