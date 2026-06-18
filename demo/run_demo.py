#!/usr/bin/env python3
"""
AlphaForge Demo — Rich terminal UI
Usage:
    python demo/run_demo.py                     # interactive menu
    python demo/run_demo.py --input "..."       # direct input (skip menu)
    python demo/run_demo.py --json              # machine-readable JSON
    python demo/run_demo.py --chart             # save PNG chart
    python demo/run_demo.py --all               # run all demo examples
    python demo/run_demo.py --lang zh           # Chinese UI
"""
import sys
import os
import json
import argparse
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── .env loader ────────────────────────────────────────────────────────────────
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

def _load_dotenv(path: str) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no third-party deps).
    Overwrites env vars that are set but empty (e.g. CMC_API_KEY="")."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # Set if missing OR explicitly empty in the environment
                if key and (key not in os.environ or not os.environ[key]):
                    os.environ[key] = val
    except FileNotFoundError:
        pass

_load_dotenv(_ENV_PATH)

# ── Key setup wizard ───────────────────────────────────────────────────────────
def _save_to_dotenv(key: str, value: str) -> None:
    """Append or update a KEY=VALUE line in the project .env file."""
    lines = []
    try:
        with open(_ENV_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        pass

    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}\n")

    with open(_ENV_PATH, "w") as f:
        f.writelines(lines)


def _wizard_cmc() -> str:
    """
    Interactive first-run wizard for CMC_API_KEY.
    Returns the key (also sets os.environ and writes .env).
    """
    # Try rich for prettier output, fall back to plain print
    try:
        from rich.console import Console as _C
        from rich.panel import Panel as _P
        from rich.rule import Rule as _R
        _con = _C()
        def _print(msg="", **kw): _con.print(msg, **kw)
        def _input(prompt): return _con.input(prompt)
        def _rule(t): _con.print(_R(f"[bold blue]{t}[/bold blue]", style="blue"))
        def _panel(body, title=""): _con.print(_P(body, title=f"[bold blue]{title}[/bold blue]", border_style="blue", padding=(1, 4)))
        _rich = True
    except ImportError:
        def _print(msg="", **kw): print(msg)
        def _input(prompt): return input(prompt)
        def _rule(t): print(f"\n{'─'*60}\n  {t}\n{'─'*60}")
        def _panel(body, title=""): print(f"\n{title}\n{body}\n")
        _rich = False

    _rule("Welcome to AlphaForge — First Run Setup")
    _print()
    _panel(
        "[bold white]AlphaForge needs a CoinMarketCap API key[/bold white]\n"
        "to fetch live price data, Fear & Greed index, and OHLCV history.\n\n"
        "[cyan]Get your free key (Basic plan is enough):[/cyan]\n"
        "[bold]→  https://coinmarketcap.com/api/[/bold]",
        title="CMC API Key Required"
    ) if _rich else _panel(
        "AlphaForge needs a CoinMarketCap API key.\n"
        "Get your free key at: https://coinmarketcap.com/api/",
        title="CMC API Key Required"
    )
    _print()

    if _rich:
        from rich.table import Table
        from rich import box as _box
        t = Table(box=_box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column(style="bold cyan", width=5)
        t.add_column()
        t.add_row("[1]", "Paste my key now  [dim](saved to .env, loaded automatically next time)[/dim]")
        t.add_row("[2]", "Show me the export command  [dim](I'll set it manually)[/dim]")
        t.add_row("[Q]", "[dim]Quit[/dim]")
        _con.print(t)
    else:
        print("  [1]  Paste my key now (saved to .env)")
        print("  [2]  Show me the export command")
        print("  [Q]  Quit")

    _print()
    choice = _input("  [bold cyan]>[/bold cyan] " if _rich else "  > ").strip().upper()

    if choice == "Q":
        _print("\n[dim]Goodbye.[/dim]") if _rich else print("\nGoodbye.")
        sys.exit(0)

    if choice == "2":
        _print()
        _panel(
            "[bold]Run this command, then restart AlphaForge:[/bold]\n\n"
            "  [bold yellow]export CMC_API_KEY=your_key_here[/bold yellow]\n\n"
            "To make it permanent, add the line above to [cyan]~/.zshrc[/cyan] or [cyan]~/.bash_profile[/cyan].",
            title="Manual Setup"
        ) if _rich else _panel(
            "Run:  export CMC_API_KEY=your_key_here\n"
            "Then restart the demo.",
            title="Manual Setup"
        )
        sys.exit(0)

    # choice == "1" (or anything else → prompt for key)
    _print()
    key_val = _input("  [bold cyan]Paste your CMC API key[/bold cyan]: " if _rich else "  Paste your CMC API key: ").strip()

    if not key_val:
        _print("\n[red]No key entered. Please set CMC_API_KEY and try again.[/red]") if _rich else print("\nNo key entered.")
        sys.exit(1)

    os.environ["CMC_API_KEY"] = key_val
    _save_to_dotenv("CMC_API_KEY", key_val)

    _print()
    _print("[bold green]✓ CMC key saved to .env — you won't be asked again.[/bold green]") if _rich else print("✓ Key saved.")
    _print()
    time.sleep(0.6)
    return key_val


def _wizard_deepseek() -> None:
    """
    Optional second step of first-run wizard: prompt for DeepSeek API key.
    User can skip at any time — AlphaForge works fine without it.
    """
    try:
        from rich.console import Console as _C
        from rich.panel import Panel as _P
        from rich.rule import Rule as _R
        from rich.table import Table as _T
        from rich import box as _box
        _con = _C()
        def _print(msg="", **kw): _con.print(msg, **kw)
        def _input(prompt): return _con.input(prompt)
        def _rule(t): _con.print(_R(f"[bold blue]{t}[/bold blue]", style="blue"))
        def _panel(body, title=""): _con.print(_P(body, title=f"[bold blue]{title}[/bold blue]", border_style="blue", padding=(1, 4)))
        _rich = True
    except ImportError:
        def _print(msg="", **kw): print(msg)
        def _input(prompt): return input(prompt)
        def _rule(t): print(f"\n  {t}\n")
        def _panel(body, title=""): print(f"\n{title}\n{body}\n")
        _rich = False

    _rule("Step 2 of 2 — AI-Powered Intent Parsing (Optional)")
    _print()
    _panel(
        "[bold white]Enable DeepSeek AI for smarter strategy input[/bold white]\n\n"
        "[cyan]Without AI (rule-based only):[/cyan]\n"
        "  • Works great with standard phrases like\n"
        "    \"BTC 4H momentum strategy, conservative risk\"\n\n"
        "[bold green]With DeepSeek AI:[/bold green]\n"
        "  ✦  Write in [bold]any language[/bold] — Chinese, English, mixed\n"
        "  ✦  Use natural expressions — \"我看空 BTC\" or \"I'm bearish\"\n"
        "  ✦  No specific keywords required — the AI understands context\n"
        "  ✦  Terminal shows [bold green]✦ AI parsing active[/bold green] badge\n\n"
        "[dim]Free tier available · No GPU needed · API call per request[/dim]\n"
        "[dim]Get your key: platform.deepseek.com[/dim]",
        title="Optional: DeepSeek AI Parsing"
    ) if _rich else _panel(
        "With DeepSeek AI: write in any language, use natural expressions.\n"
        "Without it: keyword-based parsing still works great.\n"
        "Get a free key at: platform.deepseek.com",
        title="Optional: DeepSeek AI Parsing"
    )
    _print()

    if _rich:
        t = _T(box=_box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column(style="bold cyan", width=5)
        t.add_column()
        t.add_row("[1]", "Paste my DeepSeek key now  [dim](saved to .env)[/dim]")
        t.add_row("[S]", "[dim]Skip for now  (can add later in .env)[/dim]")
        _con.print(t)
    else:
        print("  [1]  Paste my DeepSeek key now")
        print("  [S]  Skip for now\n")

    _print()
    choice = _input("  [bold cyan]>[/bold cyan] " if _rich else "  > ").strip().upper()

    if choice == "1":
        _print()
        key_val = _input(
            "  [bold cyan]Paste your DeepSeek API key[/bold cyan]: " if _rich
            else "  Paste your DeepSeek API key: "
        ).strip()
        if key_val:
            os.environ["DEEPSEEK_API_KEY"] = key_val
            _save_to_dotenv("DEEPSEEK_API_KEY", key_val)
            _print()
            _print("[bold green]✦ DeepSeek AI enabled — saved to .env.[/bold green]") if _rich else print("✦ AI enabled.")
            _print()
            time.sleep(0.6)
        else:
            _print("[dim]No key entered, skipping.[/dim]") if _rich else print("Skipped.")
    else:
        _print()
        _print(
            "[dim]Skipped. You can add DEEPSEEK_API_KEY=your_key to .env any time.[/dim]"
        ) if _rich else print("Skipped. Add DEEPSEEK_API_KEY to .env any time.")
        _print()
        time.sleep(0.4)


# ── Resolve keys ───────────────────────────────────────────────────────────────
CMC_API_KEY = os.getenv("CMC_API_KEY")
if not CMC_API_KEY:
    CMC_API_KEY = _wizard_cmc()
    # Only prompt for DeepSeek on first run (right after CMC wizard)
    if not os.getenv("DEEPSEEK_API_KEY"):
        _wizard_deepseek()

_DEEPSEEK_AVAILABLE = bool(os.getenv("DEEPSEEK_API_KEY"))

# ── Preset demo inputs ─────────────────────────────────────────────────────────
DEMO_INPUTS = [
    "Generate a BNB 4H swing strategy that follows momentum but avoids buying into overheated sentiment.",
    "Create a BTC panic reversal strategy for extreme fear conditions with conservative risk.",
    "Build an ETH volatility breakout strategy for low volatility accumulation phases.",
    "Generate a SOL momentum strategy for bullish trend conditions with aggressive risk.",
    "Create a BTC sentiment divergence strategy that avoids overheated sentiment.",
]

# ── Bilingual string table ──────────────────────────────────────────────────────
STRINGS = {
    "en": {
        "lang_select_title": "Choose your language / 选择语言",
        "lang_en":           "English",
        "lang_zh":           "中文",
        "lang_prompt":       "Your choice",
        "subtitle":       "Quantopian-style crypto strategy engine  ·  Powered by CoinMarketCap",
        "tagline":        "Natural language  →  Backtestable strategy spec  →  Live CMC data",
        "menu_title":     "Select a strategy to generate",
        "menu_custom":    "Custom input",
        "menu_quit":      "Quit",
        "menu_prompt":    "Your choice",
        "custom_prompt":  "Enter your strategy request",
        "custom_hint_llm": (
            "AI-powered parsing is active — describe your strategy in any language or style.\n"
            "  e.g. \"I'm bearish on BTC, want to catch a panic reversal with tight risk\""
        ),
        "custom_hint":    (
            "Tip: include  asset (BTC/ETH/BNB/SOL...)  ·  timeframe (4H/1D/swing)  "
            "·  style (momentum/breakout/reversal)  ·  risk (conservative/aggressive)"
        ),
        "user_input_lbl": "User Input",
        "step_labels": {
            1: "Parse strategy intent",
            2: "Fetch live CMC market data",
            3: "Compute technical features",
            4: "Detect market regime",
            5: "Select & build strategy spec",
            6: "Validate spec schema",
            7: "Run backtest + walk-forward",
            8: "Generate report",
        },
        "step_msgs": {
            1: "Parsing strategy intent…",
            2: "Fetching live CMC market data…",
            3: "Engineering technical features (EMA / RSI / MACD / vol)…",
            4: "Detecting market regime (8 regime types)…",
            5: "Selecting strategy template & building spec…",
            6: "Validating strategy spec schema…",
            7: "Running backtest + walk-forward consistency check…",
            8: "Generating report, explanation & failure modes…",
        },
        "step_done":   "Done",
        "chart_saved": "Chart saved",
        "error_lbl":   "Error",
        "pass":        "PASS ✓",
        "fail":        "FAIL ✗",
        "warn_lbl":    "WARN",
        "err_lbl":     "ERROR",
        "s1_title":    "STEP 1 — Parsed Intent",
        "s2_title":    "STEP 2 — Live CMC Market Context",
        "s3_title":    "STEP 3 — Feature Engineering",
        "s3b_title":   "STEP 3b — Live Cross-Check (CMC Data MCP)",
        "s4_title":    "STEP 4 — Market Regime Detection",
        "s5_title":    "STEP 5 — Strategy Spec",
        "s6_title":    "STEP 6 — Backtest Results",
        "s6b_title":   "STEP 6b — Walk-Forward Consistency Check",
        "s7_title":    "STEP 7 — Strategy Explanation",
        "s8_title":    "STEP 8 — Known Failure Modes",
        "summary_title": "AlphaForge — Executive Summary",
        "val_title":   "Spec Validation",
        "bt_cols":     ["Metric", "Value"],
        "bt_rows": {
            "total_return":    "Total Return",
            "bah_return":      "Buy & Hold Return",
            "alpha":           "Alpha vs B&H",
            "max_dd":          "Max Drawdown",
            "sharpe":          "Sharpe Ratio",
            "win_rate":        "Win Rate",
            "profit_factor":   "Profit Factor",
            "n_trades":        "Number of Trades",
            "exposure":        "Exposure Time",
            "final_equity":    "Final Equity",
        },
        "wf_cols":     ["Period", "Bars", "Return", "vs B&H", "Sharpe", "Max DD", "Trades"],
        "fields": {
            "asset": "Asset", "24h_7d": "24h / 7d", "fg": "Fear & Greed",
            "btc_dom": "BTC Dominance", "ohlcv_bars": "OHLCV bars",
            "ema": "EMA20 / EMA50", "rsi": "RSI14", "macd": "MACD Histogram",
            "vol_z": "Volume Z-score", "real_vol": "Realized Vol",
            "primary_regime": "Primary Regime", "secondary": "Secondary",
            "confidence": "Confidence", "strategy_type": "strategy_type",
            "entry_rules": "entry_rules", "exit_rules": "exit_rules", "risk": "risk",
            "rsi14_cross": "RSI14", "macd_cross": "MACD Hist",
            "funding": "Funding Rate", "oi": "Open Interest",
        },
        "entry_arrow": "▸", "exit_arrow": "◂",
    },
    "zh": {
        "lang_select_title": "Choose your language / 选择语言",
        "lang_en":           "English",
        "lang_zh":           "中文",
        "lang_prompt":       "请选择",
        "subtitle":       "量化策略生成引擎  ·  数据由 CoinMarketCap 提供",
        "tagline":        "自然语言  →  可回测策略规范  →  实时 CMC 数据",
        "menu_title":     "选择要生成的策略",
        "menu_custom":    "自定义输入",
        "menu_quit":      "退出",
        "menu_prompt":    "请输入选项",
        "custom_prompt":  "请输入您的策略需求",
        "custom_hint_llm": (
            "AI 解析已启用 — 可以用任意语言或口语描述您的策略想法。\n"
            "  例如：我看空 BTC，想抓恐慌反转机会，风险要保守"
        ),
        "custom_hint":    (
            "提示：包含  币种 (BTC/ETH/BNB/SOL...)  ·  周期 (4H/1D/swing)  "
            "·  风格 (momentum/breakout/reversal)  ·  风险 (conservative/aggressive)"
        ),
        "user_input_lbl": "用户输入",
        "step_labels": {
            1: "解析策略意图",
            2: "获取实时 CMC 市场数据",
            3: "计算技术指标特征",
            4: "识别市场机制",
            5: "选择模板并构建策略规范",
            6: "验证策略规范格式",
            7: "运行回测 + 滚动验证",
            8: "生成报告",
        },
        "step_msgs": {
            1: "正在解析策略意图…",
            2: "正在获取 CMC 实时市场数据…",
            3: "正在计算技术指标 (EMA / RSI / MACD / 波动率)…",
            4: "正在识别市场机制 (8 种机制类型)…",
            5: "正在选择策略模板并构建规范…",
            6: "正在验证策略规范格式…",
            7: "正在运行回测 + 滚动一致性验证…",
            8: "正在生成报告、解释说明及失败场景…",
        },
        "step_done":   "完成",
        "chart_saved": "图表已保存",
        "error_lbl":   "错误",
        "pass":        "通过 ✓",
        "fail":        "失败 ✗",
        "warn_lbl":    "警告",
        "err_lbl":     "错误",
        "s1_title":    "步骤 1 — 解析意图",
        "s2_title":    "步骤 2 — CMC 实时市场数据",
        "s3_title":    "步骤 3 — 技术特征工程",
        "s3b_title":   "步骤 3b — 实时交叉验证 (CMC Data MCP)",
        "s4_title":    "步骤 4 — 市场机制识别",
        "s5_title":    "步骤 5 — 策略规范",
        "s6_title":    "步骤 6 — 回测结果",
        "s6b_title":   "步骤 6b — 滚动一致性验证",
        "s7_title":    "步骤 7 — 策略说明",
        "s8_title":    "步骤 8 — 已知失败场景",
        "summary_title": "AlphaForge — 执行摘要",
        "val_title":   "规范验证",
        "bt_cols":     ["指标", "数值"],
        "bt_rows": {
            "total_return":    "总收益率",
            "bah_return":      "买入持有收益率",
            "alpha":           "相对 B&H 超额",
            "max_dd":          "最大回撤",
            "sharpe":          "夏普比率",
            "win_rate":        "胜率",
            "profit_factor":   "盈亏比",
            "n_trades":        "交易次数",
            "exposure":        "持仓时间占比",
            "final_equity":    "最终权益",
        },
        "wf_cols":     ["周期", "K线数", "收益率", "vs 买持", "夏普", "最大回撤", "交易数"],
        "fields": {
            "asset": "资产", "24h_7d": "24h / 7d", "fg": "恐贪指数",
            "btc_dom": "BTC 统治力", "ohlcv_bars": "K线数量",
            "ema": "EMA20 / EMA50", "rsi": "RSI14", "macd": "MACD 柱状",
            "vol_z": "成交量 Z 分数", "real_vol": "已实现波动率",
            "primary_regime": "主要机制", "secondary": "次要机制",
            "confidence": "置信度", "strategy_type": "策略类型",
            "entry_rules": "入场条件", "exit_rules": "出场条件", "risk": "风险参数",
            "rsi14_cross": "RSI14", "macd_cross": "MACD 柱状",
            "funding": "资金费率", "oi": "持仓量",
        },
        "entry_arrow": "▸", "exit_arrow": "◂",
    },
}


# ── Rich setup ─────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.rule import Rule
    from rich.live import Live
    from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn, TimeElapsedColumn, TaskProgressColumn
    from rich.columns import Columns
    from rich import box
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None


# ── Banner ─────────────────────────────────────────────────────────────────────
def _build_banner(S: dict) -> str:
    """Compose % logo + ALPHAFORGE title side by side."""
    try:
        import pyfiglet
        logo_lines = pyfiglet.figlet_format("%", font="banner").splitlines()
        text_lines = pyfiglet.figlet_format("ALPHAFORGE", font="slant").splitlines()
    except ImportError:
        logo_lines = [" %%  /", "%%  / ", "   /  ", "  / %%", " /  %%"]
        text_lines = [
            "    ___    __    ____  __  _____    __________  ____  ____________",
            "   /   |  / /   / __ \\/ / / /   |  / ____/ __ \\/ __ \\/ ____/ ____/",
            "  / /| | / /   / /_/ / /_/ / /| | / /_  / / / / /_/ / / __/ __/   ",
            " / ___ |/ /___/ ____/ __  / ___ |/ __/ / /_/ / _, _/ /_/ / /___   ",
            "/_/  |_/_____/_/   /_/ /_/_/  |_/_/    \\____/_/ |_|\\____/_____/   ",
        ]

    # Strip trailing blank lines
    while logo_lines and not logo_lines[-1].strip():
        logo_lines.pop()
    while text_lines and not text_lines[-1].strip():
        text_lines.pop()

    logo_w = max(len(l) for l in logo_lines) if logo_lines else 0
    gap = 4

    # Vertically center the shorter block
    while len(logo_lines) < len(text_lines):
        logo_lines.insert(0, "")
    while len(text_lines) < len(logo_lines):
        text_lines.insert(0, "")

    combined = []
    for l, t in zip(logo_lines, text_lines):
        combined.append(l.ljust(logo_w + gap) + t)

    return "\n".join(combined)


def print_banner(S: dict) -> None:
    if not RICH:
        print(_build_banner(S))
        print(f"\n  {S['subtitle']}")
        print(f"  {S['tagline']}\n")
        return

    banner_text = _build_banner(S)
    console.print(f"\n[bold blue]{banner_text}[/bold blue]")
    console.print(
        Panel(
            f"[bold white]{S['subtitle']}[/bold white]\n"
            f"[dim]{S['tagline']}[/dim]",
            border_style="blue",
            padding=(0, 4),
        )
    )
    console.print()


# ── Language selection (first screen) ─────────────────────────────────────────
def select_language() -> dict:
    """Show a bilingual language picker and return the chosen STRINGS dict."""
    # Use the neutral en strings for the picker itself
    title = STRINGS["en"]["lang_select_title"]

    if not RICH:
        print(f"\n  {title}\n")
        print("  [1]  English")
        print("  [2]  中文\n")
        choice = input("  Your choice: ").strip()
        return STRINGS["zh"] if choice == "2" else STRINGS["en"]

    console.print(Rule(f"[bold blue]{title}[/bold blue]", style="blue"))
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True, width=5)
    t.add_column()
    t.add_row("[1]", "English")
    t.add_row("[2]", "中文")
    console.print(t)
    console.print()

    choice = console.input("  [bold cyan]>[/bold cyan] ").strip()
    lang = "zh" if choice == "2" else "en"
    console.print()
    return STRINGS[lang]


# ── Interactive menu ────────────────────────────────────────────────────────────
def show_menu(S: dict) -> str:
    """Show numbered quick-select menu. Returns the chosen user_input string."""
    if not RICH:
        print(f"\n  {S['menu_title']}:\n")
        for i, inp in enumerate(DEMO_INPUTS, 1):
            print(f"  [{i}]  {inp}")
        print(f"\n  [C]  {S['menu_custom']}")
        print(f"  [Q]  {S['menu_quit']}\n")
        if not _DEEPSEEK_AVAILABLE:
            print("  (AI parsing inactive — set DEEPSEEK_API_KEY to enable)\n")
        choice = input(f"  {S['menu_prompt']}: ").strip()
        return _resolve_choice(choice, S)

    console.print(Rule(f"[bold blue]{S['menu_title']}[/bold blue]", style="blue"))
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True, width=5)
    t.add_column()
    for i, inp in enumerate(DEMO_INPUTS, 1):
        t.add_row(f"[{i}]", inp)
    t.add_row("", "")
    t.add_row(f"[C]", f"[italic]{S['menu_custom']}[/italic]")
    t.add_row(f"[Q]", f"[dim]{S['menu_quit']}[/dim]")
    console.print(t)

    # DeepSeek soft hint (shown once when key is absent)
    if not _DEEPSEEK_AVAILABLE:
        console.print(
            f"  [dim]✧ AI parsing inactive — set [bold]DEEPSEEK_API_KEY[/bold] to enable "
            f"(free tier: platform.deepseek.com)[/dim]"
        )
    else:
        console.print(f"  [bold green]✦ AI parsing active (DeepSeek)[/bold green]")
    console.print()

    choice = console.input(f"  [bold cyan]{S['menu_prompt']}[/bold cyan]: ").strip()
    return _resolve_choice(choice, S)


def _resolve_choice(choice: str, S: dict) -> str:
    if choice.upper() == "Q":
        console.print("\n[dim]Bye.[/dim]\n") if RICH else print("\nBye.\n")
        sys.exit(0)
    if choice.upper() == "C":
        return _custom_input(S)
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(DEMO_INPUTS):
            return DEMO_INPUTS[idx]
    except ValueError:
        pass
    # Anything that isn't a menu command is treated as a direct strategy request
    if choice.strip():
        return choice.strip()
    return DEMO_INPUTS[0]


def _custom_input(S: dict) -> str:
    import os
    has_llm = bool(os.getenv("DEEPSEEK_API_KEY"))
    hint = S["custom_hint_llm"] if has_llm else S["custom_hint"]
    llm_badge = "  [bold green]✦ AI parsing active[/bold green]\n" if has_llm else ""

    if RICH:
        console.print(f"\n{llm_badge}  [dim]{hint}[/dim]\n")
        raw = console.input(f"  [bold cyan]{S['custom_prompt']}[/bold cyan]: ").strip()
    else:
        print(f"\n  {hint}\n")
        raw = input(f"  {S['custom_prompt']}: ").strip()
    return raw or DEMO_INPUTS[0]


# ── Progress tracker (download-bar style) ──────────────────────────────────────
class ProgressRunner:
    """
    Wraps generate_strategy() with a rich Progress bar.
    Looks like a terminal download bar as each step advances.
    """

    def __init__(self, S: dict):
        self.S = S
        self.current_step = 0
        self.current_msg = ""
        self._result = None
        self._error = None
        self._progress: "Progress | None" = None
        self._task_id = None

    def _step_callback(self, step: int, total: int, msg: str):
        self.current_step = step
        self.current_msg = self.S["step_msgs"].get(step, msg)
        label = self.S["step_labels"].get(step, f"Step {step}")
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=step - 1,
                description=f"[bold blue]{step}/{total}[/bold blue]  {label}",
            )

    def run(self, user_input: str, cmc_api_key: str) -> dict:
        from alphaforge import generate_strategy
        from alphaforge.spec_generator import print_rich_output

        if not RICH:
            def cb(s, t, m):
                print(f"  [{s}/{t}] {m}")
            result = generate_strategy(user_input, cmc_api_key, step_callback=cb)
            from alphaforge import format_output
            print(format_output(result))
            return result

        total_steps = 8

        with Progress(
            SpinnerColumn(style="bold blue"),
            TextColumn("{task.description}", justify="left"),
            BarColumn(bar_width=28, style="blue", complete_style="bold blue"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            self._progress = progress
            task_id = progress.add_task(
                f"[bold blue]1/{total_steps}[/bold blue]  {self.S['step_labels'][1]}",
                total=total_steps,
                completed=0,
            )
            self._task_id = task_id

            def worker():
                try:
                    self._result = generate_strategy(
                        user_input, cmc_api_key, step_callback=self._step_callback
                    )
                except Exception as e:
                    self._error = e

            t = threading.Thread(target=worker, daemon=True)
            t.start()
            while t.is_alive():
                time.sleep(0.08)

            # Mark complete
            progress.update(task_id, completed=total_steps, description=f"[bold green]✓ All {total_steps} steps complete[/bold green]")

        console.print()

        if self._error:
            raise self._error

        print_rich_output(self._result, S=self.S)
        return self._result


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AlphaForge Strategy Generator Demo")
    parser.add_argument("--input", "-i",   type=str,   help="Strategy request (skip menu)")
    parser.add_argument("--json",  "-j",   action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--chart", "-c",   action="store_true", help="Generate and save PNG chart")
    parser.add_argument("--all",   "-a",   action="store_true", help="Run all preset demo examples")
    parser.add_argument("--lang",          type=str,   default=None, choices=["en", "zh"],
                        help="Skip language picker and force language (en/zh)")
    args = parser.parse_args()

    # ── Banner first (language-agnostic) ──────────────────────────────────
    # Show banner with neutral English strings, then let user pick language
    print_banner(STRINGS["en"])

    # ── Language selection ─────────────────────────────────────────────────
    # --lang flag skips the interactive picker (useful for scripting / --all)
    if args.lang:
        S = STRINGS[args.lang]
    else:
        S = select_language()
        # Re-print banner in chosen language if it differs
        if S is not STRINGS["en"]:
            print_banner(S)

    # ── Determine inputs ───────────────────────────────────────────────────
    if args.all:
        inputs = DEMO_INPUTS
    elif args.input:
        inputs = [args.input]
    else:
        inputs = [show_menu(S)]

    for idx, user_input in enumerate(inputs):
        if len(inputs) > 1:
            if RICH:
                console.print(Rule(f"[bold]Demo {idx + 1} / {len(inputs)}[/bold]", style="dim"))
            else:
                print(f"\n{'─'*60}\nDemo {idx + 1} / {len(inputs)}")

        if RICH:
            console.print(
                Panel(
                    f"[bold white]{user_input}[/bold white]",
                    title=f"[dim]{S['user_input_lbl']}[/dim]",
                    border_style="dim",
                    padding=(0, 2),
                )
            )
            console.print()
        else:
            print(f"\n>>> {S['user_input_lbl']}: {user_input}\n")

        try:
            if args.json:
                from alphaforge import generate_strategy
                result = generate_strategy(user_input, CMC_API_KEY)
                export = {k: v for k, v in result.items() if k != "_ohlcv"}
                export["backtest"] = {k: v for k, v in export["backtest"].items() if k != "equity_curve"}
                print(json.dumps(export, indent=2))
            else:
                runner = ProgressRunner(S)
                result = runner.run(user_input, CMC_API_KEY)

            if args.chart:
                try:
                    from alphaforge.visualizer import plot_results
                    ohlcv = result.get("_ohlcv", [])
                    if ohlcv:
                        chart_path = plot_results(result, ohlcv)
                        if RICH:
                            console.print(f"  [bold green]{S['chart_saved']} →[/bold green] {chart_path}")
                        else:
                            print(f"  {S['chart_saved']} → {chart_path}")
                    else:
                        print("  (No OHLCV data for chart)")
                except ImportError:
                    print("  Install matplotlib to generate charts: pip install matplotlib")

        except Exception as e:
            if RICH:
                console.print(f"\n[bold red]{S['error_lbl']}:[/bold red] {e}")
            else:
                print(f"{S['error_lbl']}: {e}")
            raise


if __name__ == "__main__":
    main()
