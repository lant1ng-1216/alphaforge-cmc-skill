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
    "xrp": "XRP", "ada": "ADA", "doge": "DOGE", "avax": "AVAX",
}


@dataclass
class StrategyIntent:
    asset: str = "BNB"
    timeframe: str = "4h"
    style: str = "momentum"
    constraints: list[str] = field(default_factory=list)
    risk_profile: str = "moderate"
    raw_input: str = ""

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "style": self.style,
            "constraints": self.constraints,
            "risk_profile": self.risk_profile,
        }


def parse_intent(user_input: str) -> StrategyIntent:
    text = user_input.lower()
    intent = StrategyIntent(raw_input=user_input)

    # Asset detection
    for kw, sym in COMMON_SYMBOLS.items():
        if kw in text:
            intent.asset = sym
            break

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
