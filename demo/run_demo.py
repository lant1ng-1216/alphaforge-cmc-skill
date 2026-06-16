#!/usr/bin/env python3
"""
AlphaForge Demo
From natural language to backtestable crypto strategy in seconds.

Usage:
    python demo/run_demo.py
    python demo/run_demo.py --input "Generate a BTC panic reversal strategy"
    python demo/run_demo.py --json        # machine-readable JSON output
    python demo/run_demo.py --chart       # save PNG chart
    python demo/run_demo.py --all         # run all demo examples
    python demo/run_demo.py --all --chart # run all + save charts
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alphaforge import generate_strategy, format_output

CMC_API_KEY = os.getenv("CMC_API_KEY")
if not CMC_API_KEY:
    sys.exit("Error: set the CMC_API_KEY environment variable before running the demo.")

DEMO_INPUTS = [
    "Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.",
    "Create a BTC panic reversal strategy for extreme fear conditions with conservative risk.",
    "Build an ETH volatility breakout strategy for low volatility accumulation phases.",
]


def main():
    parser = argparse.ArgumentParser(description="AlphaForge Strategy Generator Demo")
    parser.add_argument("--input", "-i", type=str, help="Strategy request (natural language)")
    parser.add_argument("--json", "-j", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--chart", "-c", action="store_true", help="Generate and save PNG chart")
    parser.add_argument("--all", "-a", action="store_true", help="Run all demo examples")
    args = parser.parse_args()

    inputs = DEMO_INPUTS if args.all else [args.input or DEMO_INPUTS[0]]

    for user_input in inputs:
        print(f"\n>>> User Input: {user_input}\n")
        try:
            result = generate_strategy(user_input, CMC_API_KEY)

            if args.json:
                export = {k: v for k, v in result.items() if k != "_ohlcv"}
                export["backtest"] = {k: v for k, v in export["backtest"].items() if k != "equity_curve"}
                print(json.dumps(export, indent=2))
            else:
                print(format_output(result))

            if args.chart:
                try:
                    from alphaforge.visualizer import plot_results
                    ohlcv = result.get("_ohlcv", [])
                    if ohlcv:
                        chart_path = plot_results(result, ohlcv)
                        print(f"\n  Chart saved → {chart_path}")
                    else:
                        print("  (No OHLCV data for chart)")
                except ImportError:
                    print("  Install matplotlib to generate charts: pip install matplotlib")

        except Exception as e:
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    main()
