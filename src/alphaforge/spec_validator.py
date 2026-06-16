"""
Strategy spec validator — checks a generated spec against the JSON Schema
and applies additional semantic rules that JSON Schema cannot express.
"""
import json
import os
from dataclasses import dataclass, field

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "schemas", "strategy_spec.schema.json"
)

REQUIRED_TOP_KEYS = [
    "version", "generated_by", "asset", "quote_asset", "timeframe",
    "strategy_type", "market_regime", "features", "risk_management",
    "backtest", "evaluation_metrics",
]

VALID_STRATEGY_TYPES = {
    "regime_aware_momentum", "panic_reversal", "sentiment_divergence",
    "volatility_breakout", "no_trade",
}

VALID_REGIMES = {
    "bullish_trend", "bearish_trend", "low_volatility_accumulation",
    "high_volatility_chop", "panic_reversal", "sentiment_overheated",
    "derivatives_crowded_long", "derivatives_crowded_short", "neutral",
}

VALID_TIMEFRAMES = {"15m", "1h", "4h", "1d", "1w"}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [f"Validation: {'PASS' if self.valid else 'FAIL'}"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate_spec(spec: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Required top-level keys
    for key in REQUIRED_TOP_KEYS:
        if key not in spec:
            errors.append(f"Missing required field: '{key}'")

    if errors:
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # 2. Enum checks
    if spec["strategy_type"] not in VALID_STRATEGY_TYPES:
        errors.append(f"Invalid strategy_type: '{spec['strategy_type']}'")

    regime = spec.get("market_regime", {})
    if regime.get("primary") not in VALID_REGIMES:
        errors.append(f"Invalid market_regime.primary: '{regime.get('primary')}'")

    if spec["timeframe"] not in VALID_TIMEFRAMES:
        errors.append(f"Invalid timeframe: '{spec['timeframe']}'")

    if spec.get("quote_asset") != "USDT":
        errors.append("quote_asset must be 'USDT'")

    if spec.get("generated_by") != "AlphaForge":
        warnings.append("generated_by is not 'AlphaForge'")

    # 3. Risk management sanity checks
    rm = spec.get("risk_management", {})
    max_pos = rm.get("max_position_size_pct", 0)
    stop = rm.get("stop_loss_pct", 0)
    max_dd = rm.get("max_strategy_drawdown_pct", 0)

    if not (1 <= max_pos <= 100):
        errors.append(f"max_position_size_pct out of range [1, 100]: {max_pos}")
    if not (0.5 <= stop <= 50):
        errors.append(f"stop_loss_pct out of range [0.5, 50]: {stop}")
    if not (1 <= max_dd <= 50):
        errors.append(f"max_strategy_drawdown_pct out of range [1, 50]: {max_dd}")
    if stop >= max_dd:
        warnings.append(
            f"stop_loss_pct ({stop}%) >= max_strategy_drawdown_pct ({max_dd}%) — "
            "a single stop-out would breach strategy drawdown limit"
        )

    # 4. Entry/exit rules must exist (except no_trade)
    if spec["strategy_type"] != "no_trade":
        has_entry = "entry_rules" in spec or "long_setup" in spec
        has_exit = "exit_rules" in spec
        if not has_entry:
            errors.append("Missing entry_rules (or long_setup for sentiment_divergence)")
        if not has_exit and spec["strategy_type"] != "sentiment_divergence":
            warnings.append("Missing exit_rules — spec is incomplete")

    # 5. Backtest config checks
    bt = spec.get("backtest", {})
    if bt.get("initial_capital", 0) < 100:
        errors.append("backtest.initial_capital must be >= 100")
    start = bt.get("start_date", "")
    end = bt.get("end_date", "")
    if start and end and start >= end:
        errors.append(f"backtest.start_date ({start}) must be before end_date ({end})")

    # 6. Features must include at least one technical indicator
    feats = spec.get("features", {})
    if not feats.get("technical"):
        warnings.append("No technical features listed — spec may be underspecified")

    # 7. Evaluation metrics
    required_metrics = {"total_return", "max_drawdown", "sharpe_ratio"}
    listed = set(spec.get("evaluation_metrics", []))
    missing = required_metrics - listed
    if missing:
        warnings.append(f"Recommended evaluation metrics missing: {missing}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_spec_file(path: str) -> ValidationResult:
    """Load a JSON or YAML spec file and validate it."""
    with open(path) as f:
        content = f.read()
    if path.endswith(".json"):
        spec = json.loads(content)
    else:
        # Minimal YAML parser for simple key: value structures
        import re
        spec = {}
        # Just load via json after basic conversion isn't reliable — use a simple approach
        try:
            import importlib.util
            if importlib.util.find_spec("yaml"):
                import yaml
                spec = yaml.safe_load(content)
            else:
                raise ImportError
        except ImportError:
            raise RuntimeError("Install pyyaml to validate YAML spec files: pip install pyyaml")
    return validate_spec(spec)
