"""
Three-layer Strategy Review Agent chain for AlphaForge.

Each agent has a distinct, non-overlapping responsibility:
  RiskAgent    — evaluates risk parameter calibration vs live market conditions
  RegimeAgent  — independently re-validates regime classification and strategy alignment
  Gatekeeper   — synthesizes both verdicts with backtest + Monte Carlo evidence

The chain always runs to completion (no short-circuit on warn) so the Gatekeeper
has the full picture before issuing its final verdict.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


Verdict = Literal["pass", "warn", "reject"]
FinalVerdict = Literal["APPROVED", "APPROVED_WITH_WARNINGS", "CONDITIONALLY_APPROVED", "REJECTED"]


@dataclass
class AgentCheck:
    name: str
    verdict: Verdict
    message: str


@dataclass
class AgentReview:
    agent: str
    verdict: Verdict
    checks: list[AgentCheck] = field(default_factory=list)
    confidence: float = 1.0  # 0–1

    def summary_lines(self) -> list[str]:
        return [f"[{c.verdict.upper()}] {c.name}: {c.message}" for c in self.checks]


@dataclass
class GatekeeperReview:
    final_verdict: FinalVerdict
    confidence: int          # 0–100
    risk_review: AgentReview
    regime_review: AgentReview
    summary: str
    warnings: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)


# ── Risk Agent ─────────────────────────────────────────────────────────────────

def run_risk_agent(
    spec: dict,
    features: dict,
    backtest: dict,
    intent_risk_profile: str = "moderate",
) -> AgentReview:
    """
    Evaluates whether the strategy's risk parameters are well-calibrated
    against the current market environment.

    Three checks:
    1. Stop-loss vs realized volatility — a stop tighter than daily noise fires constantly
    2. Position size vs declared risk profile — mismatches reduce expected utility
    3. Backtest drawdown vs spec limit — did the backtest actually respect its own rules
    """
    checks: list[AgentCheck] = []
    rm = spec.get("risk_management", {})
    stop_pct = rm.get("stop_loss_pct", 7.0)
    max_pos = rm.get("max_position_size_pct", 25.0)
    spec_max_dd = rm.get("max_strategy_drawdown_pct", 15.0)

    realized_vol = features.get("realized_volatility") or 0.0
    bt_max_dd = backtest.get("max_drawdown_pct", 0.0)
    n_trades = backtest.get("number_of_trades", 0)

    # Check 1: Stop calibration vs volatility
    # Annualized vol → approximate daily vol for comparison
    daily_vol_pct = realized_vol * 100 / (365 ** 0.5) if realized_vol else 0.0
    min_viable_stop = daily_vol_pct * 3  # stop should absorb at least 3 daily moves
    if daily_vol_pct > 0 and stop_pct < min_viable_stop:
        checks.append(AgentCheck(
            name="stop_calibration",
            verdict="warn",
            message=(
                f"Stop {stop_pct}% is tighter than 3× daily vol "
                f"({min_viable_stop:.1f}%) — likely to trigger on noise rather than signal. "
                f"Consider widening to ≥{min_viable_stop:.1f}%."
            ),
        ))
    else:
        checks.append(AgentCheck(
            name="stop_calibration",
            verdict="pass",
            message=f"Stop {stop_pct}% is adequate relative to realized vol {realized_vol:.2f} (daily ≈{daily_vol_pct:.1f}%).",
        ))

    # Check 2: Position size vs risk profile
    profile_ranges = {
        "conservative": (5, 20),
        "moderate": (15, 35),
        "aggressive": (25, 60),
    }
    lo, hi = profile_ranges.get(intent_risk_profile, (5, 60))
    if max_pos < lo:
        checks.append(AgentCheck(
            name="position_size_alignment",
            verdict="warn",
            message=(
                f"Max position {max_pos}% is below the {intent_risk_profile} profile "
                f"lower bound ({lo}%). Strategy may be too conservative for declared intent."
            ),
        ))
    elif max_pos > hi:
        checks.append(AgentCheck(
            name="position_size_alignment",
            verdict="warn",
            message=(
                f"Max position {max_pos}% exceeds the {intent_risk_profile} profile "
                f"upper bound ({hi}%). Strategy carries more risk than declared intent."
            ),
        ))
    else:
        checks.append(AgentCheck(
            name="position_size_alignment",
            verdict="pass",
            message=f"Position size {max_pos}% is consistent with {intent_risk_profile} risk profile ({lo}–{hi}%).",
        ))

    # Check 3: Backtest drawdown vs spec drawdown limit
    if n_trades > 0 and bt_max_dd > spec_max_dd * 1.5:
        checks.append(AgentCheck(
            name="drawdown_breach",
            verdict="reject",
            message=(
                f"Backtest max drawdown {bt_max_dd:.1f}% exceeded spec limit "
                f"{spec_max_dd}% by {bt_max_dd - spec_max_dd:.1f}pp. "
                f"Risk parameters are not achievable under historical conditions."
            ),
        ))
    elif n_trades > 0 and bt_max_dd > spec_max_dd * 0.85:
        checks.append(AgentCheck(
            name="drawdown_breach",
            verdict="warn",
            message=(
                f"Backtest max drawdown {bt_max_dd:.1f}% is approaching spec limit "
                f"{spec_max_dd}% ({bt_max_dd / spec_max_dd * 100:.0f}% of limit consumed)."
            ),
        ))
    else:
        checks.append(AgentCheck(
            name="drawdown_breach",
            verdict="pass",
            message=f"Backtest max drawdown {bt_max_dd:.1f}% is within spec limit {spec_max_dd}%.",
        ))

    worst = (
        "reject" if any(c.verdict == "reject" for c in checks)
        else "warn" if any(c.verdict == "warn" for c in checks)
        else "pass"
    )
    n_warns = sum(1 for c in checks if c.verdict in ("warn", "reject"))
    confidence = max(0.0, 1.0 - n_warns * 0.25)

    return AgentReview(agent="RiskAgent", verdict=worst, checks=checks, confidence=confidence)


# ── Regime Agent ───────────────────────────────────────────────────────────────

_REGIME_STRATEGY_MAP: dict[str, list[str]] = {
    "bullish_trend":              ["regime_aware_momentum"],
    "bearish_trend":              ["sentiment_divergence", "no_trade"],
    "panic_reversal":             ["panic_reversal"],
    "sentiment_overheated":       ["sentiment_divergence", "no_trade"],
    "high_volatility_chop":       ["no_trade"],
    "low_volatility_accumulation":["volatility_breakout", "regime_aware_momentum"],
    "derivatives_crowded_long":   ["sentiment_divergence"],
    "neutral":                    ["regime_aware_momentum", "sentiment_divergence"],
}

_ENTRY_FEASIBILITY: dict[str, tuple[str, ...]] = {
    # strategy_type → (feature_key, operator, threshold, description)
    "panic_reversal":    ("rsi_14",           "<",  30, "RSI < 30 required for panic_reversal entries"),
    "regime_aware_momentum": ("rsi_14",       ">",  45, "RSI > 45 signals momentum condition"),
    "volatility_breakout":   ("realized_volatility", "<", 0.5, "Low vol < 0.5 required for breakout setup"),
}


def run_regime_agent(
    regime_primary: str,
    strategy_type: str,
    features: dict,
    intent: dict,
) -> AgentReview:
    """
    Independently re-validates whether the selected strategy is coherent
    with the detected regime and whether entry conditions are currently feasible.

    Three checks:
    1. Strategy-regime alignment — is this the right tool for this market?
    2. Entry condition feasibility — can the entry rules actually fire right now?
    3. User intent vs regime — does the user's declared style make sense here?
    """
    checks: list[AgentCheck] = []
    style = intent.get("style", "momentum")
    risk_profile = intent.get("risk_profile", "moderate")

    # Check 1: Strategy-regime alignment
    valid_strategies = _REGIME_STRATEGY_MAP.get(regime_primary, [])
    if valid_strategies and strategy_type not in valid_strategies:
        checks.append(AgentCheck(
            name="strategy_regime_alignment",
            verdict="warn",
            message=(
                f"Strategy '{strategy_type}' is not the canonical choice for "
                f"'{regime_primary}' regime. Recommended: {valid_strategies}. "
                f"May perform sub-optimally in this environment."
            ),
        ))
    else:
        checks.append(AgentCheck(
            name="strategy_regime_alignment",
            verdict="pass",
            message=f"'{strategy_type}' is a valid strategy for '{regime_primary}' regime.",
        ))

    # Check 2: Entry condition feasibility
    rsi = features.get("rsi_14")
    rv = features.get("realized_volatility")

    if strategy_type == "panic_reversal" and rsi is not None and rsi > 40:
        checks.append(AgentCheck(
            name="entry_feasibility",
            verdict="warn",
            message=(
                f"Panic reversal requires RSI < 30; current RSI is {rsi:.1f}. "
                f"Entry conditions are unlikely to trigger in the near term."
            ),
        ))
    elif strategy_type == "volatility_breakout" and rv is not None and rv > 0.6:
        checks.append(AgentCheck(
            name="entry_feasibility",
            verdict="warn",
            message=(
                f"Volatility breakout requires compressed vol < 0.5; "
                f"current realized vol is {rv:.2f}. Breakout setup not in place."
            ),
        ))
    elif strategy_type == "no_trade":
        checks.append(AgentCheck(
            name="entry_feasibility",
            verdict="pass",
            message="No-trade regime correctly identified — strategy holds cash. No entry conditions needed.",
        ))
    else:
        checks.append(AgentCheck(
            name="entry_feasibility",
            verdict="pass",
            message=f"Entry conditions for '{strategy_type}' are feasible in the current market state.",
        ))

    # Check 3: User intent vs regime
    bearish_regimes = {"bearish_trend", "high_volatility_chop", "panic_reversal"}
    if style in ("momentum", "breakout") and regime_primary in bearish_regimes and risk_profile == "aggressive":
        checks.append(AgentCheck(
            name="intent_regime_conflict",
            verdict="warn",
            message=(
                f"User intent ({style}, {risk_profile}) conflicts with regime "
                f"({regime_primary}). Aggressive momentum in a bearish regime "
                f"carries elevated tail risk."
            ),
        ))
    else:
        checks.append(AgentCheck(
            name="intent_regime_conflict",
            verdict="pass",
            message=f"User intent ({style}, {risk_profile}) is consistent with the detected regime.",
        ))

    worst = (
        "reject" if any(c.verdict == "reject" for c in checks)
        else "warn" if any(c.verdict == "warn" for c in checks)
        else "pass"
    )
    n_warns = sum(1 for c in checks if c.verdict in ("warn", "reject"))
    confidence = max(0.0, 1.0 - n_warns * 0.2)

    return AgentReview(agent="RegimeAgent", verdict=worst, checks=checks, confidence=confidence)


# ── Gatekeeper ─────────────────────────────────────────────────────────────────

def run_gatekeeper(
    risk_review: AgentReview,
    regime_review: AgentReview,
    backtest: dict,
    walk_forward: list[dict],
    monte_carlo: dict,
) -> GatekeeperReview:
    """
    Final synthesis agent. Weighs both upstream reviews against quantitative
    evidence (backtest, walk-forward, Monte Carlo) to issue a binding verdict.

    Verdict ladder:
      APPROVED              — all checks pass, MC confidence strong
      APPROVED_WITH_WARNINGS — warnings present but strategy is viable
      CONDITIONALLY_APPROVED — significant concerns; deploy only with reduced size
      REJECTED               — hard failure in risk checks or MC evidence
    """
    warnings: list[str] = []
    rejections: list[str] = []

    # Collect upstream verdicts
    if risk_review.verdict == "reject":
        rejections.append(f"RiskAgent rejected: {[c.message for c in risk_review.checks if c.verdict == 'reject']}")
    elif risk_review.verdict == "warn":
        warnings.extend([c.message for c in risk_review.checks if c.verdict == "warn"])

    if regime_review.verdict == "reject":
        rejections.append(f"RegimeAgent rejected: {[c.message for c in regime_review.checks if c.verdict == 'reject']}")
    elif regime_review.verdict == "warn":
        warnings.extend([c.message for c in regime_review.checks if c.verdict == "warn"])

    # Monte Carlo evidence
    mc_prob_positive = monte_carlo.get("probability_positive_return_pct", 50.0)
    mc_p50_sharpe = monte_carlo.get("sharpe_ratio", {}).get("p50", 0.0)
    mc_p95_dd = monte_carlo.get("max_drawdown_pct", {}).get("p95", 0.0)

    if mc_prob_positive < 30:
        rejections.append(
            f"Monte Carlo: only {mc_prob_positive:.0f}% of 1000 simulations produce positive returns. "
            f"Strategy lacks a reliable edge under bootstrapped conditions."
        )
    elif mc_prob_positive < 50:
        warnings.append(
            f"Monte Carlo: {mc_prob_positive:.0f}% probability of positive return — "
            f"below 50% threshold. Edge is weak; consider reducing position size."
        )

    if mc_p95_dd > 35:
        warnings.append(
            f"Monte Carlo worst-case (p95) max drawdown is {mc_p95_dd:.1f}% — "
            f"tail risk is elevated. Size accordingly."
        )

    # Walk-forward consistency
    if len(walk_forward) >= 2:
        wf_returns = [p["total_return_pct"] for p in walk_forward if "total_return_pct" in p]
        if len(wf_returns) >= 2:
            spread = max(wf_returns) - min(wf_returns)
            if spread > 25:
                warnings.append(
                    f"Walk-forward period spread is {spread:.1f}pp — "
                    f"strategy performance is inconsistent across historical windows. "
                    f"May be environment-dependent."
                )

    # Trade count sanity
    n_trades = backtest.get("number_of_trades", 0)
    if n_trades == 0:
        warnings.append(
            "Zero trades executed. Strategy is intentionally idle in this regime — "
            "backtest statistics are not meaningful. This is correct disciplined behavior."
        )
    elif n_trades < 3:
        warnings.append(
            f"Only {n_trades} trade(s) executed. Statistical metrics (Sharpe, win rate) "
            f"are not reliable at this sample size."
        )

    # Determine final verdict
    combined_confidence = (risk_review.confidence + regime_review.confidence) / 2

    if rejections:
        final_verdict: FinalVerdict = "REJECTED"
        confidence = int(combined_confidence * 30)
        summary = (
            f"Strategy REJECTED. Hard failures detected by upstream agents. "
            f"Do not deploy without addressing: {'; '.join(rejections[:1])}."
        )
    elif len(warnings) >= 3:
        final_verdict = "CONDITIONALLY_APPROVED"
        confidence = int(combined_confidence * 55)
        summary = (
            f"Conditionally approved with {len(warnings)} warnings. "
            f"Consider reducing position size by 30–50% until conditions improve. "
            f"Key concern: {warnings[0]}"
        )
    elif warnings:
        final_verdict = "APPROVED_WITH_WARNINGS"
        confidence = int(combined_confidence * 75)
        summary = (
            f"Approved with {len(warnings)} warning(s). Strategy is viable but non-ideal. "
            f"Monte Carlo: {mc_prob_positive:.0f}% probability of positive return, "
            f"median Sharpe {mc_p50_sharpe:.2f}."
        )
    else:
        final_verdict = "APPROVED"
        confidence = int(combined_confidence * 95)
        summary = (
            f"Strategy approved. All agent checks passed. "
            f"Monte Carlo: {mc_prob_positive:.0f}% probability of positive return, "
            f"median Sharpe {mc_p50_sharpe:.2f}, p95 max drawdown {mc_p95_dd:.1f}%."
        )

    return GatekeeperReview(
        final_verdict=final_verdict,
        confidence=min(confidence, 95),
        risk_review=risk_review,
        regime_review=regime_review,
        summary=summary,
        warnings=warnings,
        rejections=rejections,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

def review_strategy(
    spec: dict,
    features: dict,
    regime_primary: str,
    intent: dict,
    backtest: dict,
    walk_forward: list[dict],
    monte_carlo: dict,
) -> dict:
    """
    Run the full three-agent review chain and return a serializable result dict.
    """
    risk_review = run_risk_agent(
        spec=spec,
        features=features,
        backtest=backtest,
        intent_risk_profile=intent.get("risk_profile", "moderate"),
    )
    regime_review = run_regime_agent(
        regime_primary=regime_primary,
        strategy_type=spec.get("strategy_type", ""),
        features=features,
        intent=intent,
    )
    gate = run_gatekeeper(
        risk_review=risk_review,
        regime_review=regime_review,
        backtest=backtest,
        walk_forward=walk_forward,
        monte_carlo=monte_carlo,
    )

    return {
        "final_verdict": gate.final_verdict,
        "confidence": gate.confidence,
        "summary": gate.summary,
        "warnings": gate.warnings,
        "rejections": gate.rejections,
        "risk_agent": {
            "verdict": risk_review.verdict,
            "confidence": round(risk_review.confidence, 2),
            "checks": [{"name": c.name, "verdict": c.verdict, "message": c.message}
                       for c in risk_review.checks],
        },
        "regime_agent": {
            "verdict": regime_review.verdict,
            "confidence": round(regime_review.confidence, 2),
            "checks": [{"name": c.name, "verdict": c.verdict, "message": c.message}
                       for c in regime_review.checks],
        },
    }
