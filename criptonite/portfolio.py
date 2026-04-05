"""
Portfolio tracker.

Maintains open positions, calculates unrealised P&L, and provides a
simple in-memory ledger suitable for paper-trading or dry-run mode.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .config import DEFAULT_TAKER_FEE

logger = logging.getLogger(__name__)

_PORTFOLIO_FILE = os.path.join(
    os.path.dirname(__file__), "..", "portfolio.json"
)


@dataclass
class Position:
    coin_id: str
    symbol: str
    entry_price: float
    units: float
    invested_usd: float
    buy_fee_usd: float
    opened_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    target_price: float = float("nan")
    stop_loss_price: float = float("nan")


@dataclass
class ClosedTrade:
    coin_id: str
    symbol: str
    entry_price: float
    exit_price: float
    units: float
    invested_usd: float
    gross_proceed_usd: float
    total_fees_usd: float
    net_profit_usd: float
    net_profit_pct: float
    opened_at: str
    closed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Portfolio:
    """In-memory portfolio with optional JSON persistence."""

    def __init__(self, fee_rate: float = DEFAULT_TAKER_FEE) -> None:
        self.fee_rate = fee_rate
        self.positions: dict[str, Position] = {}   # keyed by coin_id
        self.history: list[ClosedTrade] = []
        self.cash_usd: float = 0.0
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        path = os.path.abspath(_PORTFOLIO_FILE)
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for p in data.get("positions", []):
                pos = Position(**p)
                self.positions[pos.coin_id] = pos
            for t in data.get("history", []):
                self.history.append(ClosedTrade(**t))
            self.cash_usd = data.get("cash_usd", 0.0)
            logger.info("Portfolio loaded from %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load portfolio file: %s", exc)

    def save(self) -> None:
        path = os.path.abspath(_PORTFOLIO_FILE)
        data = {
            "positions": [asdict(p) for p in self.positions.values()],
            "history": [asdict(t) for t in self.history],
            "cash_usd": self.cash_usd,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        logger.info("Portfolio saved to %s", path)

    # ── Trading actions ───────────────────────────────────────────────────────

    def open_position(
        self,
        coin_id: str,
        symbol: str,
        entry_price: float,
        investment_usd: float,
        target_price: float = float("nan"),
        stop_loss_price: float = float("nan"),
    ) -> Position:
        """Open a new long position (paper trade)."""
        fee = investment_usd * self.fee_rate
        units = (investment_usd - fee) / entry_price
        pos = Position(
            coin_id=coin_id,
            symbol=symbol,
            entry_price=entry_price,
            units=units,
            invested_usd=investment_usd,
            buy_fee_usd=fee,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
        )
        self.positions[coin_id] = pos
        self.cash_usd -= investment_usd
        logger.info(
            "Opened %s position: %.6f units @ $%.4f (fee $%.4f)",
            symbol.upper(), units, entry_price, fee,
        )
        return pos

    def close_position(
        self,
        coin_id: str,
        exit_price: float,
    ) -> Optional[ClosedTrade]:
        """Close an existing position at *exit_price*."""
        pos = self.positions.pop(coin_id, None)
        if pos is None:
            logger.warning("No open position for %s", coin_id)
            return None

        gross = pos.units * exit_price
        sell_fee = gross * self.fee_rate
        net = gross - sell_fee
        pnl = net - pos.invested_usd
        pnl_pct = pnl / pos.invested_usd * 100

        trade = ClosedTrade(
            coin_id=coin_id,
            symbol=pos.symbol,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            units=pos.units,
            invested_usd=pos.invested_usd,
            gross_proceed_usd=gross,
            total_fees_usd=pos.buy_fee_usd + sell_fee,
            net_profit_usd=pnl,
            net_profit_pct=pnl_pct,
            opened_at=pos.opened_at,
        )
        self.history.append(trade)
        self.cash_usd += net
        logger.info(
            "Closed %s position: P&L $%.2f (%.2f %%)",
            pos.symbol.upper(), pnl, pnl_pct,
        )
        return trade

    # ── Unrealised P&L ────────────────────────────────────────────────────────

    def unrealised_pnl(self, current_prices: dict[str, float]) -> dict[str, float]:
        """Return unrealised P&L per open position."""
        result = {}
        for coin_id, pos in self.positions.items():
            price = current_prices.get(coin_id)
            if price is None:
                continue
            gross = pos.units * price
            sell_fee = gross * self.fee_rate
            result[coin_id] = gross - sell_fee - pos.invested_usd
        return result

    # ── Summary ───────────────────────────────────────────────────────────────

    @property
    def total_invested(self) -> float:
        return sum(p.invested_usd for p in self.positions.values())

    @property
    def realised_pnl(self) -> float:
        return sum(t.net_profit_usd for t in self.history)

    def summary(self) -> dict:
        return {
            "open_positions": len(self.positions),
            "total_invested_usd": round(self.total_invested, 2),
            "realised_pnl_usd": round(self.realised_pnl, 2),
            "closed_trades": len(self.history),
        }
