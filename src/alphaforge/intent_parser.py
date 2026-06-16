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
