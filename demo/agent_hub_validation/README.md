# Live CMC Agent Hub Validation

This is a record of a real test, not a simulation: `skill.md` was wired into a live LLM agent
connected to the actual **CMC Agent Hub** MCP server (`https://mcp.coinmarketcap.com/skill-hub/stream`),
and its output was cross-checked against AlphaForge's own deterministic pipeline, asking about
the same asset at the same time.

## Setup

- MCP Server: `cmc-skill-hub` (native Streamable HTTP, not an SSE/stdio bridge)
- Tools used: `find_skill`, `execute_skill`
- Client: Claude Code (local agent with MCP support)

## Step 1 — Verify the connection

```
find_skill(query="btc price")
```

Returned ranked candidates including `btc_cross_asset_correlation`, `btc_etf_institutional_demand`,
and others — confirming the MCP connection and tool discovery work end-to-end.

## Step 2 — Cross-check AlphaForge's regime read against a live Agent Hub skill

**Question asked to AlphaForge (its own deterministic pipeline):**
> "Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment."

**AlphaForge's regime classifier result:**
```
Primary Regime: NEUTRAL (confidence 40%)
"No dominant regime detected. Mixed signals — reduce position size."
```

**Same asset, independently, via CMC Agent Hub's `analyze_multi_timeframe_trend_alignment` skill:**
```
overall_alignment: "mixed_alignment"
dominant_trend: "bullish"
aligned_timeframe_count: 1 of 3 (4h bullish-weak, 1h/1d neutral)
action_guidance.primary_action: "confirm_long_frame_before_adding_risk"
```

**Result: two independent systems, same conclusion** — both read BNB as a mixed/unconfirmed
setup rather than a clean trend, at the same point in time. This is real cross-validation, not
internal consistency within one codebase.

## Step 3 — A genuine architectural finding

A second live call, `monitor_market_sentiment_shift`, returned real sentiment data:

```
sentiment_regime: "neutral_chop_with_crowded_funding"
fear_greed_value: 25.0  (label: "fear")
fear_greed_7d_delta: -22.0
average_funding_bps_7d: 18.15
```

This confirmed something important: **CMC Agent Hub's skill-hub does not expose raw data
primitives** (a plain price, a plain Fear & Greed number, a plain funding rate) to agents.
It exposes pre-packaged "evidence pack" analyses. AlphaForge's `fear_greed_score` is real,
live data pulled from CMC's classic REST API — but the richer derivatives/sentiment fields
declared in the spec (`funding_rate_zscore`, `open_interest_change`, `long_short_crowding`)
are only available, in CMC's current data architecture, through Agent Hub evidence-pack
skills — not a paywalled REST endpoint, as originally assumed.

This is exactly why AlphaForge ships its own deterministic pipeline rather than delegating
everything to the Agent Hub: the Agent Hub is where an LLM agent gathers market narrative
and cross-validation; AlphaForge is what computes the precise indicators, the schema-valid
YAML spec, and the historical backtest that `skill.md` requires. The two layers are
complementary, not redundant — and that division of labor was discovered by actually testing
the integration, not assumed up front.

## Verification checklist (per CMC's own MCP setup doc)

| Check | Result |
|---|---|
| Platform | Claude Code (local agent) |
| Transport | Native Streamable HTTP |
| `find_skill(query="btc price")` | ✅ Success |
| `execute_skill(btc_cross_asset_correlation, {"preview": true})` | ✅ Completed in 26.18s, no client-side timeout |
| Tool timeout configured | 300s (`MCP_TOOL_TIMEOUT=300000`) |
| API key location | User-level config only, never committed to a repo |
