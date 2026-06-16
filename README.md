# AlphaForge

> A Quantopian-style crypto strategy generation Skill powered by CoinMarketCap.

Built for **BNB Hack: AI Trading Agent Edition — Track 2: Strategy Skills**.

## What It Does

AlphaForge converts natural-language trading ideas into explicit, machine-readable, backtestable crypto strategy specifications.

Instead of producing vague trading opinions, it detects the current market regime using live CMC data, selects the appropriate strategy template, applies sentiment and risk guards, and outputs a reproducible YAML strategy spec that can be validated and backtested.

## Why It Matters

Most AI trading tools generate opinions. AlphaForge generates auditable strategy rules.

> "Good trading agents should start as good strategy researchers."

## How It Works

```
User Natural Language Input
  ↓
Intent Parser          — extracts asset, timeframe, style, constraints, risk profile
  ↓
CMC Data Layer         — live price, Fear & Greed, global metrics (CoinMarketCap API)
                         + historical OHLCV (Binance public API)
  ↓
Feature Engineering    — EMA20/50, RSI14, MACD, volume z-score, realized volatility, ATR
  ↓
Market Regime Classifier — detects: bullish trend / panic / overheated / breakout / chop
  ↓
Strategy Template Selector — maps regime + intent → strategy type
  ↓
Strategy Spec Generator — outputs machine-readable YAML spec with full rules + risk mgmt
  ↓
Backtester             — runs historical simulation, compares vs buy-and-hold
  ↓
Report                 — regime explanation + strategy explanation + failure modes
```

## Validated Live Against CMC Agent Hub

AlphaForge's `skill.md` was connected to the real **CMC Agent Hub** (via its MCP server) and tested end-to-end with a live agent, not just simulated locally.

Two independent systems were asked about the same asset (BNB) at the same time:
- AlphaForge's own regime classifier → **neutral / mixed signals** (confidence 40%)
- CMC Agent Hub's `analyze_multi_timeframe_trend_alignment` skill → **mixed alignment** across 1h/4h/1d, "confirm long frame before adding risk"

Both reached the same conclusion independently — a useful cross-validation signal, and a real-data confirmation that AlphaForge's regime detection isn't just internally self-consistent, it agrees with CoinMarketCap's own live analysis tooling.

Full transcript and verification checklist: [`demo/agent_hub_validation/README.md`](demo/agent_hub_validation/README.md)

**A genuine architectural finding from this test:** CMC Agent Hub's skill-hub does not expose raw data primitives (price, EMA, raw Fear & Greed score) to agents directly — it exposes pre-packaged "evidence pack" analyses (sentiment regime, trend alignment, volatility risk, etc.). This confirms why AlphaForge needs its own deterministic engine rather than delegating everything to the Agent Hub: the Agent Hub is the right place for an LLM agent to gather market *narrative* and cross-validation, while AlphaForge's Python pipeline is what actually computes the precise indicators, generates the schema-valid YAML spec, and runs the historical backtest that `skill.md` requires. The two are complementary, not redundant — an agent in production would use Agent Hub skills for context and AlphaForge for the quantitative, reproducible output.

## Quick Start

```bash
# Clone and run
git clone https://github.com/yourname/alphaforge-cmc-skill
cd alphaforge-cmc-skill

# Set your CMC API key
export CMC_API_KEY=your_api_key_here

# Run the demo
python demo/run_demo.py

# Custom strategy request
python demo/run_demo.py --input "Generate a BTC panic reversal strategy for extreme fear"

# Machine-readable JSON output
python demo/run_demo.py --json

# Run all demo examples
python demo/run_demo.py --all
```

No dependencies beyond Python 3.9+ standard library + Binance/CMC public APIs.

## Example

**Input:**
```
Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.
```

**Output includes:**

```
Market Regime: NEUTRAL (confidence 40%)
Strategy Type: regime_aware_momentum

Entry Rules:
  - close > ema_20
  - ema_20 > ema_50
  - macd_histogram > 0
  - rsi_14 >= 50 AND rsi_14 <= 70
  - volume_zscore > 0.8

Exit Rules:
  - close < ema_20
  - macd_histogram < 0
  - rsi_14 > 80 AND rsi_14_declining == true

Risk Management:
  - max_position_size: 25%
  - stop_loss: 7%
  - trailing_stop: 9%
  - max_strategy_drawdown: 15%

Backtest (90 days):
  - Total Return: -3.0% vs Buy-and-hold -3.3%
  - Sharpe: -5.11 | Max DD: 3.3% | Win Rate: 0.0%
```

## Strategy Types

| Market Regime | Strategy |
|---|---|
| Bullish Trend | Regime-Aware Momentum |
| Panic / Extreme Fear | Panic Reversal |
| Sentiment Overheated | Sentiment Divergence (reduce/avoid) |
| Low Volatility Accumulation | Volatility Breakout |
| High Volatility Chop | No Trade |

## Project Structure

```
alphaforge-cmc-skill/
  README.md                        ← you are here
  skill.md                         ← CMC Skill definition
  schemas/
    strategy_spec.schema.json      ← JSON Schema for strategy spec validation
  src/alphaforge/
    __init__.py
    cmc_adapter.py                 ← CoinMarketCap API + Binance OHLCV
    intent_parser.py               ← natural language → structured intent
    features.py                    ← EMA, RSI, MACD, volume z-score, ATR, realized vol
    regime_classifier.py           ← market regime detection (core differentiator)
    strategy_templates.py          ← spec builder for each strategy type
    spec_generator.py              ← main pipeline orchestration
    backtester.py                  ← rule-based historical simulation
  demo/
    run_demo.py                    ← end-to-end demo script
  examples/
    bnb_momentum_strategy.yaml     ← example strategy spec output
  tests/
    test_features.py
    test_regime_classifier.py
```

## Data Sources

- **CoinMarketCap API** (key required): Fear & Greed index, price quotes, global metrics
- **Binance public API** (no key): Historical daily OHLCV

## Limitations

This project does not execute trades. It generates research-grade strategy specifications intended for further backtesting and validation before any live deployment.

Not financial advice.

## Built for

BNB Hack: AI Trading Agent Edition  
Track 2: Strategy Skills  
Powered by CoinMarketCap Agent Hub
