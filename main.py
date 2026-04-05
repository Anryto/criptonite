"""
Criptonite – main entry point.

Usage:
    python main.py [--investment AMOUNT] [--fee RATE] [--dry-run]

Options:
    --investment AMOUNT   Capital per position in USD [default: 100]
    --fee RATE            Exchange taker-fee fraction [default: 0.001 = 0.10 %]
    --dry-run             Analyse only; do not persist portfolio changes
    --verbose             Enable debug logging
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from rich.console import Console

from criptonite import fetcher, analyzer, ranker, strategy, reporter
from criptonite.portfolio import Portfolio
from criptonite.config import (
    DEFAULT_INVESTMENT_USD,
    DEFAULT_TAKER_FEE,
    INVESTMENT_MIN_USD,
    INVESTMENT_MAX_USD,
)

console = Console()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="criptonite",
        description=(
            "Analyse the top 10 cryptocurrencies and generate buy/sell "
            "signals with profitability estimates."
        ),
    )
    parser.add_argument(
        "--investment",
        type=float,
        default=DEFAULT_INVESTMENT_USD,
        metavar="USD",
        help=(
            f"Capital to deploy per position in USD "
            f"(range ${INVESTMENT_MIN_USD:.0f}–${INVESTMENT_MAX_USD:.0f}, "
            f"default ${DEFAULT_INVESTMENT_USD:.0f})"
        ),
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=DEFAULT_TAKER_FEE,
        metavar="RATE",
        help="Exchange taker-fee fraction, e.g. 0.001 for 0.1 %% (default %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Do not write portfolio.json (analysis only).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    console.rule("[bold cyan]CRIPTONITE  –  Crypto Signal Engine[/bold cyan]")

    # ── 1. Fetch top-coin listing ─────────────────────────────────────────────
    console.print("[dim]Fetching top-coin listing from CoinGecko …[/dim]")
    try:
        top_coins = fetcher.fetch_top_coins()
    except RuntimeError as exc:
        console.print(f"[red]Error fetching coins:[/red] {exc}")
        return 1

    coin_names: dict[str, str] = {c["id"]: c["name"] for c in top_coins}
    console.print(f"[green]✓[/green] Retrieved {len(top_coins)} coins.")

    # ── 2. Fetch price history for each coin ─────────────────────────────────
    bundles: list[analyzer.IndicatorBundle] = []
    for coin in top_coins:
        cid = coin["id"]
        sym = coin.get("symbol", cid)
        console.print(f"[dim]  Fetching history for {sym.upper()} …[/dim]")
        try:
            history = fetcher.fetch_price_history(cid)
        except RuntimeError as exc:
            console.print(f"  [yellow]⚠ Skipping {sym.upper()}: {exc}[/yellow]")
            continue

        bundle = analyzer.compute_indicators(cid, sym, history)
        if bundle is not None:
            bundles.append(bundle)

        # Be polite to the free API – small delay between requests
        time.sleep(1.5)

    if not bundles:
        console.print("[red]No indicator data available. Aborting.[/red]")
        return 1

    # ── 3. Rank coins ─────────────────────────────────────────────────────────
    console.print("[dim]Ranking coins …[/dim]")
    ranked = ranker.rank_coins(bundles)

    # ── 4. Generate buy/sell recommendations ─────────────────────────────────
    console.print("[dim]Generating trade recommendations …[/dim]")
    recommendations = strategy.generate_recommendations(
        ranked_coins=ranked,
        coin_names=coin_names,
        investment_usd=args.investment,
        fee_rate=args.fee,
    )

    # ── 5. Print report ───────────────────────────────────────────────────────
    reporter.print_report(recommendations, args.investment, args.fee)

    # ── 6. Optionally update paper portfolio ──────────────────────────────────
    if not args.dry_run:
        portfolio = Portfolio(fee_rate=args.fee)
        current_prices = {c["id"]: c.get("current_price", 0.0) for c in top_coins}

        for rec in recommendations:
            if rec.signal == strategy.Signal.BUY:
                if rec.coin_id not in portfolio.positions:
                    portfolio.open_position(
                        coin_id=rec.coin_id,
                        symbol=rec.symbol,
                        entry_price=rec.entry_price,
                        investment_usd=rec.investment_usd,
                        target_price=rec.target_price,
                        stop_loss_price=rec.stop_loss_price,
                    )
            elif rec.signal == strategy.Signal.SELL:
                if rec.coin_id in portfolio.positions:
                    portfolio.close_position(
                        coin_id=rec.coin_id,
                        exit_price=float(
                            ranked[0].bundle.prices.iloc[-1]
                            if ranked else rec.current_price
                        ),
                    )

        portfolio.save()
        summary = portfolio.summary()
        console.print(
            f"\n[bold]Portfolio summary:[/bold]  "
            f"{summary['open_positions']} open positions  |  "
            f"Invested: ${summary['total_invested_usd']:,.2f}  |  "
            f"Realised P&L: ${summary['realised_pnl_usd']:,.2f}  |  "
            f"Closed trades: {summary['closed_trades']}"
        )

    console.print("\n[bold cyan]Done.[/bold cyan]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
