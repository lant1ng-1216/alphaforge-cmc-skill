"""
User intent parser — extracts structured strategy intent from natural language.
"""
import re
from dataclasses import dataclass, field


TIMEFRAME_MAP = {
    "1h": "1h", "4h": "4h", "daily": "1d", "1d": "1d",
    "weekly": "1w", "1w": "1w", "15m": "15m", "swing": "4h", "scalp": "1h",
}

STYLE_KEYWORDS = {
    "momentum": "momentum",
    "trend": "momentum",
    "mean reversion": "mean_reversion",
    "reversal": "mean_reversion",
    "breakout": "breakout",
    "dca": "dca",
    "swing": "momentum",
    "scalp": "momentum",
    "contrarian": "contrarian",
    "bearish": "contrarian",
    "short": "contrarian",
    "hedge": "contrarian",
    "看空": "contrarian",
    "做空": "contrarian",
    "反弹": "mean_reversion",
    "动量": "momentum",
    "突破": "breakout",
}

CONSTRAINT_KEYWORDS = {
    "avoid overheated": "avoid_overheated_sentiment",
    "avoids overheated": "avoid_overheated_sentiment",
    "avoiding overheated": "avoid_overheated_sentiment",
    "overheated sentiment": "avoid_overheated_sentiment",
    "sentiment guard": "avoid_overheated_sentiment",
    "no overheated": "avoid_overheated_sentiment",
    "control drawdown": "control_drawdown",
    "low drawdown": "control_drawdown",
    "limit drawdown": "control_drawdown",
    "avoid crowded": "avoid_crowded_longs",
    "crowded long": "avoid_crowded_longs",
    "panic": "panic_reversal",
    "extreme fear": "panic_reversal",
    "volatile": "high_volatility_filter",
    "low volatility": "low_volatility_accumulation",
    "volatility spike": "reduce_exposure_on_volatility",
    "spike in volatility": "reduce_exposure_on_volatility",
    "cuts exposure": "reduce_exposure_on_volatility",
    "cut exposure": "reduce_exposure_on_volatility",
    "reduce exposure": "reduce_exposure_on_volatility",
    "reduces exposure": "reduce_exposure_on_volatility",
    "cuts risk": "reduce_exposure_on_volatility",
}

RISK_MAP = {
    "aggressive": "aggressive",
    "conservative": "conservative",
    "moderate": "moderate",
    "low risk": "conservative",
    "high risk": "aggressive",
}

COMMON_SYMBOLS = {
    "bnb": "BNB", "btc": "BTC", "bitcoin": "BTC",
    "eth": "ETH", "ethereum": "ETH", "sol": "SOL", "solana": "SOL",
    "xrp": "XRP", "ripple": "XRP", "ada": "ADA", "cardano": "ADA",
    "doge": "DOGE", "dogecoin": "DOGE", "avax": "AVAX", "avalanche": "AVAX",
    "sui": "SUI", "ltc": "LTC", "litecoin": "LTC", "dot": "DOT",
    "polkadot": "DOT", "link": "LINK", "chainlink": "LINK",
    "trx": "TRX", "tron": "TRX", "ton": "TON", "shib": "SHIB",
    "pepe": "PEPE", "near": "NEAR", "apt": "APT", "aptos": "APT",
    "arb": "ARB", "arbitrum": "ARB", "op": "OP", "optimism": "OP",
    "uni": "UNI", "uniswap": "UNI", "atom": "ATOM", "cosmos": "ATOM",
    "fil": "FIL", "filecoin": "FIL", "icp": "ICP", "inj": "INJ",
    "injective": "INJ", "tia": "TIA", "celestia": "TIA",
}

# Words that look like 2-6 letter tickers but are common English/strategy
# vocabulary, not assets — excluded when extracting a candidate symbol from
# free text. CMC validation (see spec_generator.resolve_asset) is the real
# safety net; this just keeps obvious noise out of the candidate list.
_TICKER_STOPWORDS = {
    "a", "an", "the", "that", "this", "but", "and", "or", "for", "with",
    "into", "avoid", "avoids", "avoiding", "swing", "trend", "daily",
    "weekly", "hourly", "scalp", "short", "long", "entry", "exit",
    "value", "price", "prices", "close", "above", "below", "under",
    "over", "high", "highs", "low", "lows", "risk", "cuts", "cut", "spike",
    "spikes", "quickly", "style", "build", "create", "make", "please",
    "using", "based", "target", "targets", "follow", "follows",
    "is", "are", "of", "on", "in", "to", "at", "it", "be", "do", "if",
    "by", "rsi", "macd", "atr", "ema", "usd", "usdt", "controls",
    "control", "during", "while", "when", "from", "strong", "weak",
    "buying", "selling", "buy", "sell", "holds", "hold", "cash",
    "up", "down", "not", "coin", "coins", "token", "tokens", "crypto",
    "asset", "assets", "market", "markets", "trade", "trades", "trading",
    "made", "does", "exist", "some", "any", "all", "no", "yes", "can",
}

_TICKER_PATTERN = re.compile(r"\b[A-Za-z]{2,6}\b")


@dataclass
class StrategyIntent:
    asset: str = "BNB"
    timeframe: str = "4h"
    style: str = "momentum"
    constraints: list[str] = field(default_factory=list)
    risk_profile: str = "moderate"
    raw_input: str = ""
    asset_candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "style": self.style,
            "constraints": self.constraints,
            "risk_profile": self.risk_profile,
        }


def extract_asset_candidates(raw_input: str) -> list[str]:
    """
    Best-effort, ordered list of plausible ticker symbols mentioned in free text.
    Not validated against CMC here — callers (see spec_generator.resolve_asset)
    should confirm the symbol actually exists before trusting it, so any
    CMC-listed asset works, not just the ones in COMMON_SYMBOLS.
    """
    text_lower = raw_input.lower()
    candidates: list[str] = []

    # Friendly full-name matches first (e.g. "bitcoin" -> BTC)
    for kw, sym in COMMON_SYMBOLS.items():
        if len(kw) > 3 and kw in text_lower and sym not in candidates:
            candidates.append(sym)

    # Generic short-token extraction, in order of appearance in the sentence
    for match in _TICKER_PATTERN.finditer(raw_input):
        token = match.group(0)
        if token.lower() in _TICKER_STOPWORDS:
            continue
        sym = token.upper()
        if sym not in candidates:
            candidates.append(sym)

    return candidates


def parse_intent(user_input: str) -> StrategyIntent:
    text = user_input.lower()
    intent = StrategyIntent(raw_input=user_input)

    # Asset detection — keep a best-effort default; the real symbol is
    # confirmed against live CMC data in spec_generator.resolve_asset.
    intent.asset_candidates = extract_asset_candidates(user_input)
    intent.asset = intent.asset_candidates[0] if intent.asset_candidates else "BNB"

    # Timeframe detection
    for kw, tf in TIMEFRAME_MAP.items():
        if kw in text:
            intent.timeframe = tf
            break

    # Style detection
    for kw, style in STYLE_KEYWORDS.items():
        if kw in text:
            intent.style = style
            break

    # Constraints
    for kw, constraint in CONSTRAINT_KEYWORDS.items():
        if kw in text:
            if constraint not in intent.constraints:
                intent.constraints.append(constraint)

    # Risk profile
    for kw, risk in RISK_MAP.items():
        if kw in text:
            intent.risk_profile = risk
            break

    return intent


# ── LLM-powered intent parser ──────────────────────────────────────────────────

_LLM_SYSTEM = """\
You are a crypto trading strategy parser. Extract structured intent from the user's natural-language strategy request.

Output ONLY a JSON object with these exact keys:
{
  "asset": "<ticker symbol, e.g. BTC / ETH / BNB / SOL>",
  "asset_candidates": ["<primary>", "<alt1>", ...],
  "timeframe": "<one of: 15m / 1h / 4h / 1d / 1w>",
  "style": "<one of: momentum / mean_reversion / breakout / contrarian / dca>",
  "constraints": ["<zero or more from: avoid_overheated_sentiment / panic_reversal / control_drawdown / avoid_crowded_longs / high_volatility_filter / low_volatility_accumulation / reduce_exposure_on_volatility>"],
  "risk_profile": "<one of: conservative / moderate / aggressive>"
}

Rules:
- If the user says "I'm bearish / short / 看空 / hedge / avoid longs" → style: contrarian
- If the user says "mean reversion / bounce / 反弹 / 超卖反弹 / reversal" → style: mean_reversion
- If the user says "follow the trend / breakout / 动量 / 趋势" → style: momentum or breakout
- If the user says "panic / capitulation / extreme fear / 恐慌 / 极度恐慌" → style: mean_reversion AND add panic_reversal to constraints
- IMPORTANT: "bearish / 看空 / short bias" is NOT the same as "mean reversion" — bearish means expecting further decline (contrarian to bullish), mean_reversion means expecting a bounce
- If timeframe is unclear, default to 4h
- If asset is unclear, default to BNB
- If the user mentions "overheated / FOMO / greed / 过热 / 贪婪" → add avoid_overheated_sentiment to constraints
- If the user mentions "low risk / safe / conservative / 保守" → risk_profile: conservative
- If the user mentions "aggressive / 激进 / 大仓位" → risk_profile: aggressive
- If the user writes in Chinese, English, or any language — still output the same JSON
- Output ONLY the JSON, no explanation, no markdown fences
"""


def parse_intent_llm(user_input: str) -> "StrategyIntent | None":
    """
    Use DeepSeek (OpenAI-compatible API) to extract structured strategy intent.
    Returns None if DEEPSEEK_API_KEY is not set or the call fails —
    callers should fall back to parse_intent() in that case.
    """
    import os
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return None

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        msg = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user",   "content": user_input},
            ],
        )
        raw = msg.choices[0].message.content.strip()

        import json
        data = json.loads(raw)

        intent = StrategyIntent(raw_input=user_input)
        intent.asset = str(data.get("asset", "BNB")).upper()
        intent.asset_candidates = [str(s).upper() for s in data.get("asset_candidates", [intent.asset])]
        if intent.asset not in intent.asset_candidates:
            intent.asset_candidates.insert(0, intent.asset)

        tf = str(data.get("timeframe", "4h")).lower()
        intent.timeframe = tf if tf in {"15m", "1h", "4h", "1d", "1w"} else "4h"

        style = str(data.get("style", "momentum")).lower()
        intent.style = style if style in {"momentum", "mean_reversion", "breakout", "contrarian", "dca"} else "momentum"

        valid_constraints = {
            "avoid_overheated_sentiment", "panic_reversal", "control_drawdown",
            "avoid_crowded_longs", "high_volatility_filter",
            "low_volatility_accumulation", "reduce_exposure_on_volatility",
        }
        intent.constraints = [c for c in data.get("constraints", []) if c in valid_constraints]

        risk = str(data.get("risk_profile", "moderate")).lower()
        intent.risk_profile = risk if risk in {"conservative", "moderate", "aggressive"} else "moderate"

        return intent

    except Exception:
        return None


def parse_intent_auto(user_input: str) -> "tuple[StrategyIntent, str]":
    """
    Try LLM first; fall back to regex.
    Returns (intent, method) where method is 'llm' or 'regex'.
    """
    llm_result = parse_intent_llm(user_input)
    if llm_result is not None:
        return llm_result, "llm"
    return parse_intent(user_input), "regex"

    return intent
