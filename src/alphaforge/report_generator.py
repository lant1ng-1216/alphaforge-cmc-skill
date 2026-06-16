"""
Report generator — formats AlphaForge pipeline output into human-readable text.
Thin wrapper around the formatting logic; kept as a separate module per architecture spec.
"""
from .spec_generator import format_output


def generate_report(result: dict) -> str:
    """
    Generate a full human-readable strategy report from a pipeline result dict.
    Delegates to spec_generator.format_output for consistent formatting.
    """
    return format_output(result)


def generate_executive_summary(result: dict) -> str:
    """
    Generate a 3-line executive summary (Section 9.1 of architecture doc).
    """
    regime = result["regime"]["primary"].replace("_", " ").title()
    strategy = result["spec"]["strategy_type"].replace("_", " ").title()
    explanation = result["regime"]["explanation"].split(".")[0]

    return (
        f"Market regime: {regime}.\n"
        f"Recommended strategy: {strategy}.\n"
        f"Reason: {explanation}."
    )
