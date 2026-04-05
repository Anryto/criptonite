"""
Rich terminal reporter.

Renders the analysis results as formatted tables and panels.
"""

from __future__ import annotations

import math
from typing import Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .strategy import Signal, TradeRecommendation

console = Console()


# ── Colour helpers ────────────────────────────────────────────────────────────

def _pct_color(value: float) -> str:
    if math.isnan(value):
        return "dim"
    return "green" if value >= 0 else "red"


def _signal_style(sig: Signal) -> str:
    return {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}[sig.value]


def _fmt_pct(value: float, decimals: int = 2) -> str:
    if math.isnan(value):
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def _fmt_usd(value: float, decimals: int = 4) -> str:
    if math.isnan(value):
        return "N/A"
    if value >= 1_000:
        return f"${value:,.2f}"
    return f"${value:.{decimals}f}"


# ── Main report function ──────────────────────────────────────────────────────

def print_report(
    recommendations: Sequence[TradeRecommendation],
    investment_usd: float,
    fee_rate: float,
) -> None:
    """Print the full analysis report to the terminal."""

    console.print()
    console.print(
        Panel(
            "[bold cyan]CRIPTONITE[/bold cyan]  –  "
            "Cryptocurrency Buy/Sell Signal Engine\n"
            f"[dim]Investment per position: [bold]${investment_usd:,.2f} USD[/bold]  |  "
            f"Fee rate: [bold]{fee_rate * 100:.2f}%[/bold][/dim]",
            expand=False,
            border_style="cyan",
        )
    )

    # ── Ranking overview table ────────────────────────────────────────────────
    overview = Table(
        title="📊  Top Coin Ranking",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white on dark_blue",
    )
    overview.add_column("#", style="dim", justify="right", width=3)
    overview.add_column("Coin", min_width=10)
    overview.add_column("Score", justify="right")
    overview.add_column("Signal", justify="center")
    overview.add_column("Price (USD)", justify="right")
    overview.add_column("RSI", justify="right")
    overview.add_column("Sharpe", justify="right")
    overview.add_column("Volatility", justify="right")
    overview.add_column("30d Change", justify="right")
    overview.add_column("Max DD", justify="right")

    for rec in recommendations:
        overview.add_row(
            str(rec.rank),
            f"[bold]{rec.symbol}[/bold]\n[dim]{rec.name[:20]}[/dim]",
            f"[cyan]{rec.score:.1f}[/cyan]",
            Text(rec.signal.value, style=_signal_style(rec.signal)),
            _fmt_usd(rec.current_price),
            f"{rec.rsi:.1f}" if not math.isnan(rec.rsi) else "N/A",
            f"{rec.sharpe:.2f}" if not math.isnan(rec.sharpe) else "N/A",
            Text(
                _fmt_pct(rec.volatility * 100),
                style="red" if rec.volatility > 1.0 else "green",
            ) if not math.isnan(rec.volatility) else Text("N/A"),
            Text(_fmt_pct(rec.change_30d * 100), style=_pct_color(rec.change_30d * 100))
            if not math.isnan(rec.change_30d) else Text("N/A"),
            Text(
                _fmt_pct(rec.max_drawdown * 100),
                style="red",
            ) if not math.isnan(rec.max_drawdown) else Text("N/A"),
        )

    console.print(overview)

    # ── Per-coin detail panels ────────────────────────────────────────────────
    console.print("\n[bold]📋  Trade Recommendations[/bold]\n")
    for rec in recommendations:
        _print_trade_panel(rec, fee_rate)


def _print_trade_panel(rec: TradeRecommendation, fee_rate: float) -> None:
    sig_style = _signal_style(rec.signal)

    lines = [
        f"[bold]{rec.symbol}[/bold]  [dim]{rec.name}[/dim]  "
        f"[{sig_style}]● {rec.signal.value}[/{sig_style}]",
        "",
        f"  Current price :  {_fmt_usd(rec.current_price)}",
        f"  Entry (limit) :  [green]{_fmt_usd(rec.entry_price)}[/green]",
        f"  Target price  :  [green]{_fmt_usd(rec.target_price)}[/green]",
        f"  Stop-loss     :  [red]{_fmt_usd(rec.stop_loss_price)}[/red]",
        "",
        f"  Investment    :  ${rec.investment_usd:,.2f} USD",
        f"  Units to buy  :  {rec.units:.6f} {rec.symbol}",
        f"  Buy fee       :  {_fmt_usd(rec.buy_fee, 4)}",
        f"  Sell fee      :  {_fmt_usd(rec.sell_fee, 4)}",
        f"  Net profit    :  [{_pct_color(rec.net_profit_pct)}]"
        f"{_fmt_usd(rec.net_profit_usd, 2)}  "
        f"({_fmt_pct(rec.net_profit_pct)})[/{_pct_color(rec.net_profit_pct)}]",
    ]

    if rec.buy_signals:
        lines += ["", "  [green]Buy signals:[/green]"]
        for s in rec.buy_signals:
            lines.append(f"    ✅  {s}")

    if rec.sell_signals:
        lines += ["", "  [red]Sell signals:[/red]"]
        for s in rec.sell_signals:
            lines.append(f"    ⚠️   {s}")

    panel_style = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}[rec.signal.value]
    console.print(
        Panel(
            "\n".join(lines),
            border_style=panel_style,
            expand=False,
        )
    )
