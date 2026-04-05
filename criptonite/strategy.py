"""
Trading-signal and position-sizing engine.

Generates BUY / SELL / HOLD recommendations with entry/exit prices,
expected profitability, and commission-adjusted targets.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

import numpy as np

from .analyzer import (
    IndicatorBundle,
    is_golden_cross,
    is_macd_bullish,
    is_price_near_bb_lower,
    is_price_near_bb_upper,
    is_rsi_overbought,
    is_rsi_oversold,
)
from .config import (
    DEFAULT_INVESTMENT_USD,
    DEFAULT_TAKER_FEE,
    INVESTMENT_MAX_USD,
    INVESTMENT_MIN_USD,
    MIN_PROFIT_TARGET,
)
from .ranker import RankedCoin

logger = logging.getLogger(__name__)


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeRecommendation:
    coin_id: str
    symbol: str
    name: str
    rank: int
    score: float
    signal: Signal

    current_price: float
    entry_price: float           # suggested limit-buy price
    target_price: float          # suggested take-profit price
    stop_loss_price: float       # suggested stop-loss price

    investment_usd: float        # capital to deploy
    units: float                 # how many coins to buy
    total_cost_usd: float        # including buy fee

    expected_gross_profit: float
    buy_fee: float
    sell_fee: float
    net_profit_usd: float
    net_profit_pct: float        # after both fees

    # Underlying indicator summary
    rsi: float = float("nan")
    sharpe: float = float("nan")
    volatility: float = float("nan")
    change_30d: float = float("nan")
    max_drawdown: float = float("nan")

    buy_signals: list[str] = field(default_factory=list)
    sell_signals: list[str] = field(default_factory=list)


# ── Main signal factory ───────────────────────────────────────────────────────

def generate_recommendations(
    ranked_coins: Sequence[RankedCoin],
    coin_names: dict[str, str],
    investment_usd: float = DEFAULT_INVESTMENT_USD,
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> list[TradeRecommendation]:
    """
    Generate a :class:`TradeRecommendation` for each ranked coin.

    Parameters
    ----------
    ranked_coins:
        Output of :func:`ranker.rank_coins`.
    coin_names:
        Mapping of ``coin_id → human-readable name``.
    investment_usd:
        Capital to allocate per position (clamped to
        ``[INVESTMENT_MIN_USD, INVESTMENT_MAX_USD]``).
    fee_rate:
        Taker fee fraction (e.g. 0.001 = 0.10 %).
    """
    investment_usd = max(INVESTMENT_MIN_USD, min(INVESTMENT_MAX_USD, investment_usd))

    recommendations: list[TradeRecommendation] = []
    for rc in ranked_coins:
        rec = _build_recommendation(
            rc, coin_names.get(rc.bundle.coin_id, rc.bundle.coin_id),
            investment_usd, fee_rate
        )
        recommendations.append(rec)

    return recommendations


# ── Private helpers ───────────────────────────────────────────────────────────

def _buy_signals(b: IndicatorBundle) -> list[str]:
    signals = []
    if is_rsi_oversold(b):
        signals.append(f"RSI oversold ({b.rsi:.1f} < 35)")
    if is_macd_bullish(b):
        signals.append("MACD bullish crossover")
    if is_price_near_bb_lower(b):
        signals.append("Price near lower Bollinger Band")
    if is_golden_cross(b):
        signals.append("Golden cross (SMA20 > SMA50)")
    if not math.isnan(b.change_30d) and b.change_30d < -0.10:
        signals.append(f"30d dip ({b.change_30d * 100:.1f} %)")
    return signals


def _sell_signals(b: IndicatorBundle) -> list[str]:
    signals = []
    if is_rsi_overbought(b):
        signals.append(f"RSI overbought ({b.rsi:.1f} > 65)")
    if not is_macd_bullish(b) and not math.isnan(b.macd_hist):
        signals.append("MACD bearish crossover")
    if is_price_near_bb_upper(b):
        signals.append("Price near upper Bollinger Band")
    if not is_golden_cross(b):
        signals.append("Death cross (SMA20 < SMA50)")
    return signals


def _determine_signal(buy_sigs: list[str], sell_sigs: list[str]) -> Signal:
    if len(buy_sigs) > len(sell_sigs):
        return Signal.BUY
    if len(sell_sigs) > len(buy_sigs):
        return Signal.SELL
    return Signal.HOLD


def _entry_price(b: IndicatorBundle, signal: Signal) -> float:
    """
    Suggest a limit-order entry price.

    For BUY: slightly below current price (0.5 % discount) to avoid buying
    at the top of a micro-rally.
    For SELL / HOLD: current price.
    """
    current = float(b.prices.iloc[-1])
    if signal == Signal.BUY:
        return round(current * 0.995, 8)
    return round(current, 8)


def _target_price(entry: float, b: IndicatorBundle, fee_rate: float) -> float:
    """
    Take-profit target: at least ``MIN_PROFIT_TARGET`` net after two fees,
    capped loosely at the upper Bollinger Band if that gives a higher target.
    """
    min_target = entry * (1 + MIN_PROFIT_TARGET + 2 * fee_rate)
    bb_target = b.bb_upper if not math.isnan(b.bb_upper) else 0.0
    return round(max(min_target, bb_target), 8)


def _stop_loss_price(entry: float, b: IndicatorBundle) -> float:
    """
    Stop-loss: lower Bollinger Band or 5 % below entry, whichever is higher
    (so we never set the stop above entry).
    """
    five_pct = entry * 0.95
    bb_stop = b.bb_lower if not math.isnan(b.bb_lower) else 0.0
    candidate = max(five_pct, bb_stop)
    return round(min(candidate, entry * 0.98), 8)  # never >2 % above entry


def _build_recommendation(
    rc: RankedCoin,
    name: str,
    investment_usd: float,
    fee_rate: float,
) -> TradeRecommendation:
    b = rc.bundle
    buy_sigs = _buy_signals(b)
    sell_sigs = _sell_signals(b)
    signal = _determine_signal(buy_sigs, sell_sigs)

    current = float(b.prices.iloc[-1])
    entry = _entry_price(b, signal)
    target = _target_price(entry, b, fee_rate)
    stop = _stop_loss_price(entry, b)

    # Position sizing
    buy_fee_abs = investment_usd * fee_rate
    units = (investment_usd - buy_fee_abs) / entry
    total_cost = investment_usd  # fee already included

    gross_proceed = units * target
    sell_fee_abs = gross_proceed * fee_rate
    net_proceed = gross_proceed - sell_fee_abs
    net_profit = net_proceed - total_cost
    net_profit_pct = net_profit / total_cost * 100 if total_cost else float("nan")

    return TradeRecommendation(
        coin_id=b.coin_id,
        symbol=b.symbol.upper(),
        name=name,
        rank=rc.rank,
        score=rc.score,
        signal=signal,
        current_price=current,
        entry_price=entry,
        target_price=target,
        stop_loss_price=stop,
        investment_usd=investment_usd,
        units=units,
        total_cost_usd=total_cost,
        expected_gross_profit=gross_proceed - total_cost,
        buy_fee=buy_fee_abs,
        sell_fee=sell_fee_abs,
        net_profit_usd=net_profit,
        net_profit_pct=net_profit_pct,
        rsi=b.rsi,
        sharpe=b.sharpe_ratio,
        volatility=b.annualised_volatility,
        change_30d=b.change_30d,
        max_drawdown=b.max_drawdown,
        buy_signals=buy_sigs,
        sell_signals=sell_sigs,
    )
