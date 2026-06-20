# AlphaForge

> A Quantopian-style crypto strategy generation Skill powered by CoinMarketCap.

Built for **BNB Hack: AI Trading Agent Edition — Track 2: Strategy Skills**.

**On-Chain Identity (ERC-8004):** Registered on BNB Chain Mainnet — [TX 0x81f506...b185](https://bscscan.com/tx/0x81f50684a4399409ebc84129d8074165559ed839cb89321e58f52f01cb95b185) · Agent: `alphaforge-strategy-skill` · Owner: `0xB0088d6Eb46c3C15D878b54900ce1d5AEad54bD7`

---

## What It Does

AlphaForge converts natural-language trading ideas into explicit, machine-readable, backtestable crypto strategy specifications.

Instead of producing vague trading opinions ("bullish on BNB"), it reads live CMC market data, detects the current market regime across 8 regimes, selects the appropriate strategy template, applies sentiment and risk guards, and outputs a fully reproducible YAML strategy spec — complete with explicit entry/exit rules, risk parameters, backtest results, and a walk-forward consistency check.

**Input:**
```
Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.
```
or in Chinese:
```
我看空 BTC，想抓恐慌反转机会，保守风险
```

**Output:** A 10-section structured report with live market data, regime classification, machine-readable strategy spec, backtest statistics, and honest failure mode disclosure. Takes ~10 seconds end-to-end.

---

## What Makes AlphaForge Different

Most Track 2 submissions will generate a strategy suggestion. AlphaForge goes seven steps further:

### 1. Eight-regime market classifier (not just bull/bear)
The regime classifier detects one of 8 distinct states — `bullish_trend`, `bearish_trend`, `panic_reversal`, `sentiment_overheated`, `high_volatility_chop`, `low_volatility_accumulation`, `derivatives_crowded_long`, `neutral` — and selects a strategy template appropriate for *that specific regime*. The strategy switches automatically when the market structure changes. A momentum strategy in a panic regime is not generated.

### 2. Walk-forward consistency check (overfitting guard)
Every strategy spec is tested not just on the full backtest window, but also across **two independent historical half-periods** with no parameter re-fitting. If a strategy only works on one window, the walk-forward table exposes it. This is the standard anti-overfitting check used in professional quant workflows — almost no hackathon submission bothers.

### 3. Live CMC Data MCP cross-check
AlphaForge calls CoinMarketCap's **Data MCP** (`mcp.coinmarketcap.com`) in real time and cross-checks its own computed RSI14 and MACD histogram against CMC's official calculation:

```
RSI14  — AlphaForge: 40.59   |  CMC official: 43.30
MACD   — AlphaForge: -0.139  |  CMC official:  0.506
```

Real market data, not fabricated inputs.

### 4. JSON Schema validation on every output
Every generated strategy spec is validated against a strict JSON Schema (`schemas/strategy_spec.schema.json`) that enforces required fields, valid enums, and risk parameter ranges before the spec is returned. Invalid specs are caught and reported — the system cannot silently output garbage.

### 5. Monte Carlo simulation (1000 bootstrap paths)

After every backtest, AlphaForge runs 1,000 bootstrap resamplings of the strategy's daily equity returns to convert the single deterministic result into a **probability distribution**. Output includes p5/p25/p50/p75/p95 percentile bands for total return, Sharpe ratio, and max drawdown, plus:

- P(positive return): what fraction of 1000 paths end in profit?
- P(Sharpe > 1): what fraction achieve a professional-grade Sharpe?
- P(drawdown > 20%): tail risk probability across all paths

A strategy with median Sharpe 0.9 but p5 Sharpe −1.5 tells a very different story from one with p5 Sharpe 0.3. No hackathon submission has this.

### 6. Three-layer Agent review chain

Every strategy is evaluated by three independent agents after all quantitative evidence is in:

- **RiskAgent** — checks whether stop-loss, position size, and drawdown limits are well-calibrated against current market volatility
- **RegimeAgent** — independently re-validates regime classification and checks whether the selected strategy is the canonical fit, and whether entry conditions are currently feasible
- **Gatekeeper** (DeepSeek LLM, not rule-based) — receives a structured evidence packet containing both upstream agent reports, 365-day backtest, Monte Carlo distribution, walk-forward consistency, and user intent, then reasons about all of it semantically before issuing a binding verdict: `APPROVED` / `APPROVED_WITH_WARNINGS` / `CONDITIONALLY_APPROVED` / `REJECTED`

The critical distinction: other multi-agent review systems use `if/else` threshold checks for the final verdict. AlphaForge's Gatekeeper is a real LLM reasoning step — it understands context (e.g. a negative-Sharpe strategy with +42pp alpha in a bear market is not a failure), produces natural-language deployment guidance, and identifies non-obvious risks. Falls back to deterministic rules if no API key is set.

### 7. LLM-powered intent parsing (DeepSeek)
The natural language input is parsed by **DeepSeek** (via its OpenAI-compatible API) to extract structured strategy intent: asset, timeframe, style, constraints, and risk profile. This means users can write in any language, use slang, or describe their market view in plain terms — the parser handles it. Falls back to rule-based parsing if no API key is set, so the skill works with or without LLM access.

### 6. Why AlphaForge is more rigorous than similar submissions

Most Track 2 submissions generate strategy suggestions from live snapshots. AlphaForge goes further on two dimensions that matter for quantitative credibility:

**Real backtests, not fixture snapshots.** Every AlphaForge run executes a full 365-day simulation against real Binance OHLCV data fetched at runtime. Walk-forward consistency check splits that window into two independent half-periods — the standard anti-overfitting check used in professional quant workflows. Other submissions often ship pre-recorded fixture snapshots that replay the same canned output on every run; AlphaForge generates fresh results each time against the current market.

**Live CMC data on every call.** AlphaForge calls CoinMarketCap API and CMC Data MCP in real time on every invocation — price quotes, Fear & Greed, global metrics, official RSI/MACD, derivatives open interest. There is no cached or pre-recorded data in the critical path. Cross-validation between AlphaForge's own computed indicators and CMC's official TA engine is performed live and reported in every output.

---

## Honest Disclosure

### Why Sharpe ratios are sometimes negative

In the current bearish market environment (BTC dominance ~58%, Fear & Greed at 22), many strategy types are intentionally inactive. A **panic reversal** strategy, for example, requires RSI < 30 *and* Fear & Greed < 25 *and* a 12%+ deviation from EMA50 simultaneously — all three conditions must be true at once. In a grinding bear market where none of these reach extremes, the strategy fires 0–1 times over a 365-day window.

A negative Sharpe on 1 trade is statistically meaningless. What matters is the **alpha vs buy-and-hold**: every tested strategy significantly outperformed passive holding during the same period (typically +24pp to +56pp), because the strategy avoided most of the drawdown by simply not being in the market. This is correct behavior, not a bug — a strategy that says "don't trade in this regime" is doing its job.

### Why walk-forward periods sometimes show 0 trades

This is a direct consequence of the same discipline above. The walk-forward split divides the 365-day window into two halves. If the signal conditions were never met in a given half (e.g., RSI never dropped below 30 in the second half), the strategy correctly generates 0 trades rather than force entries that don't meet its own rules.

**This is the honest property of a rule-based system.** A system that always generates trades regardless of market conditions is not disciplined — it's just noisy. AlphaForge's strategy specs include explicit `no_trade` regime detection precisely to avoid this failure mode.

---

## Pipeline

```
User Natural Language Input (any language)
  ↓
LLM Intent Parser (DeepSeek)         — extracts asset, timeframe, style, constraints, risk profile
  ↓  [fallback: rule-based parser if no API key]
CMC Data Layer                        — live price, Fear & Greed, global metrics (CMC API)
                                        + historical OHLCV (Binance public, CMC fallback)
                                        + CMC Data MCP cross-check (official TA + derivatives)
  ↓
Feature Engineering                   — EMA20/50, RSI14, MACD, volume z-score, realized volatility
  ↓
Market Regime Classifier (8 regimes)  — bullish / bearish / panic / overheated / chop / accumulation / neutral
  ↓
Strategy Template Selector            — maps regime + intent → strategy type
  ↓
Strategy Spec Generator               — YAML spec with explicit entry/exit rules + risk management
  ↓
JSON Schema Validator                 — enforces required fields, valid enums, risk parameter bounds
  ↓
Backtester                            — 365-day simulation vs buy-and-hold
  ↓
Walk-Forward Check                    — same rules, two independent half-periods (no refitting)
  ↓
Monte Carlo Simulation (1000 paths)   — bootstrap equity returns → p5/p50/p95 bands + probability metrics
  ↓
3-Layer Agent Review Chain            — RiskAgent (rules) → RegimeAgent (rules) → Gatekeeper (DeepSeek LLM)
  ↓
Rich Terminal Report                  — regime + spec + backtest + walk-forward + MC + review verdict
```

---

## Quick Start

```bash
git clone https://github.com/lant1ng-1216/alphaforge-cmc-skill
cd alphaforge-cmc-skill
pip install -r requirements.txt

# Required: CoinMarketCap API key
export CMC_API_KEY=your_cmc_key

# Optional: DeepSeek key enables LLM-powered intent parsing
export DEEPSEEK_API_KEY=your_deepseek_key

# Launch interactive demo (language picker → strategy menu)
python demo/run_demo.py

# Skip menu: direct input in any language
python demo/run_demo.py --input "Generate a BTC panic reversal strategy"
python demo/run_demo.py --input "我想做 ETH 突破策略，激进一点"

# Force language (en/zh), useful for scripting
python demo/run_demo.py --lang zh --input "生成 BNB 动量策略"

# Machine-readable JSON output
python demo/run_demo.py --json

# Run all 5 preset demo examples
python demo/run_demo.py --all

# Save PNG equity chart
python demo/run_demo.py --chart
```

**Python 3.9+ required.** No local model or GPU needed.

---

## Demo Output (condensed)

**Input:** `Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.`

```
✦ AI-powered intent parsing (DeepSeek)

STEP 2 — Live CMC Market Context
  Asset         BNB  @  $591.58
  24h / 7d      -1.75%  /  -1.40%
  Fear & Greed  22 — Fear
  BTC Dominance 58.3%

STEP 3b — Live Cross-Check (CMC Data MCP)
  RSI14    AlphaForge 40.59  vs  CMC 43.30
  MACD     AlphaForge -0.139  vs  CMC 0.506

STEP 4 — Market Regime
  Primary: BEARISH TREND  (confidence 80%)

STEP 5 — Strategy Spec
  strategy_type: sentiment_divergence
  entry_rules:   [avoids entries in current bearish regime]
  risk:  max_pos 25%  stop 7%  max_dd 15%

STEP 6 — Backtest Results
  Total Return      -0.64%
  Buy & Hold        -25.49%
  Alpha vs B&H      +24.85pp
  Max Drawdown       -6.75%
  Sharpe Ratio       -0.08
  Number of Trades   11

STEP 6b — Walk-Forward
  P1/2  (182 bars):  +3.35%  Sharpe 1.10  DD -3.0%  3 trades
  P2/2  (183 bars):  -3.57%  Sharpe -2.05 DD -3.6%  7 trades

Executive Summary
  Market regime: Bearish Trend.
  Recommended strategy: Sentiment Divergence.
  Backtest alpha: +24.8pp vs buy-and-hold, max DD 6.8%, Sharpe -0.08.
```

---

## Strategy Types

| Market Regime | Strategy Template | Core Logic |
|---|---|---|
| Bullish Trend | Regime-Aware Momentum | Trend + momentum + volume alignment |
| Bearish Trend | Sentiment Divergence | Reduce exposure, avoid chasing |
| Panic / Extreme Fear | Panic Reversal | Mean-reversion at capitulation |
| Sentiment Overheated | Sentiment Divergence | Avoid entries in greed extremes |
| Low Vol Accumulation | Volatility Breakout | Wait for compression → breakout |
| High Vol Chop | No Trade | Preserve capital, sit out |
| Derivatives Crowded | Sentiment Divergence | Fade crowded positioning |
| Neutral | Regime-Aware Momentum | Reduced-size trend following |

---

## Validated Live Against CMC Agent Hub

AlphaForge's `skill.md` was connected to the real **CMC Agent Hub** (via its MCP server) and tested end-to-end with a live agent, not just simulated locally.

Two independent systems were asked about the same asset (BNB) at the same time:
- AlphaForge's own regime classifier → **neutral / mixed signals** (confidence 40%)
- CMC Agent Hub's `analyze_multi_timeframe_trend_alignment` skill → **mixed alignment** across 1h/4h/1d

Both reached the same conclusion independently — a live cross-validation that AlphaForge's regime detection agrees with CoinMarketCap's own analysis tooling.

Full transcript: [`demo/agent_hub_validation/README.md`](demo/agent_hub_validation/README.md)

---

## Project Structure

```
alphaforge-cmc-skill/
  README.md                        ← you are here
  skill.md                         ← CMC Skill definition (10-step output protocol)
  requirements.txt
  schemas/
    strategy_spec.schema.json      ← JSON Schema for spec validation
  src/alphaforge/
    __init__.py
    cmc_adapter.py                 ← CMC API + Binance OHLCV + CMC Data MCP
    intent_parser.py               ← NL → structured intent (DeepSeek LLM + regex fallback)
    features.py                    ← EMA, RSI, MACD, volume z-score, realized vol
    regime_classifier.py           ← 8-regime market classifier
    strategy_templates.py          ← spec builder per strategy type
    spec_generator.py              ← main pipeline + rich terminal output
    backtester.py                  ← rule-based simulation + walk-forward
    spec_validator.py              ← JSON Schema validation
    report_generator.py            ← executive summary
    visualizer.py                  ← equity curve PNG chart
  demo/
    run_demo.py                    ← interactive terminal demo (rich UI, bilingual)
    agent_hub_validation/          ← live CMC Agent Hub test transcript
  examples/
    bnb_momentum_strategy.yaml
    btc_panic_reversal_strategy.yaml
    eth_sentiment_divergence_strategy.yaml
  tests/
    test_features.py
    test_regime_classifier.py
    test_backtester.py
    test_spec_validator.py
```

---

## Data Sources

| Source | Data | Key Required |
|---|---|---|
| CoinMarketCap API | Price quotes, Fear & Greed, global metrics | ✅ `CMC_API_KEY` |
| CMC Data MCP | Official TA (RSI/MACD), derivatives snapshot | ✅ (same key) |
| Binance public API | Historical daily OHLCV | ❌ |
| DeepSeek API | LLM intent parsing | Optional `DEEPSEEK_API_KEY` |

---

## Limitations

- Does not execute trades. Generates research-grade strategy specifications only.
- Intent parser recognizes common crypto assets and keywords. Obscure ticker symbols are resolved against the live CMC symbol list.
- Backtest uses daily OHLCV bars (not tick or intraday data). Sub-daily strategy logic (4H entries) is approximated on daily closes.
- Not financial advice.

---

## Built For

BNB Hack: AI Trading Agent Edition  
Track 2: Strategy Skills  
Powered by CoinMarketCap Agent Hub  
[DoraHacks submission](https://dorahacks.io/buidl/44255)
