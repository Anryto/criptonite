"""
Technical-analysis engine.

Given a price/volume history (as returned by the fetcher), computes a
comprehensive set of indicators that feed into the signal generator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import ta

from .config import (
    RSI_PERIOD,
    RSI_OVERSOLD,
    RSI_OVERBOUGHT,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
    BB_PERIOD,
    BB_STD,
    SMA_SHORT,
    SMA_LONG,
)

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class IndicatorBundle:
    """All computed indicators for a single coin."""

    coin_id: str
    symbol: str

    # Price series (most-recent last)
    prices: pd.Series = field(repr=False)
    volumes: pd.Series = field(repr=False)

    # Momentum
    rsi: float = float("nan")
    macd: float = float("nan")
    macd_signal: float = float("nan")
    macd_hist: float = float("nan")

    # Trend
    sma_short: float = float("nan")
    sma_long: float = float("nan")
    ema_short: float = float("nan")

    # Volatility / Bollinger Bands
    bb_upper: float = float("nan")
    bb_middle: float = float("nan")
    bb_lower: float = float("nan")
    bb_width: float = float("nan")   # (upper-lower)/middle – normalised width

    # Return / risk statistics
    daily_returns: pd.Series = field(default_factory=pd.Series, repr=False)
    annualised_return: float = float("nan")
    annualised_volatility: float = float("nan")
    sharpe_ratio: float = float("nan")    # risk-free rate assumed ≈ 0
    max_drawdown: float = float("nan")

    # Volume trend
    volume_sma: float = float("nan")
    volume_ratio: float = float("nan")   # current / sma  (>1 means rising)

    # 30-day price change %
    change_30d: float = float("nan")


# ── Main computation ─────────────────────────────────────────────────────────

def compute_indicators(
    coin_id: str,
    symbol: str,
    history: dict[str, Any],
) -> IndicatorBundle | None:
    """
    Build an :class:`IndicatorBundle` from raw CoinGecko market-chart data.

    Returns ``None`` if there is insufficient price history.
    """
    prices_raw = history.get("prices", [])
    volumes_raw = history.get("total_volumes", [])

    if len(prices_raw) < SMA_LONG + 5:
        logger.warning("%s: not enough history (%d days).", coin_id, len(prices_raw))
        return None

    prices = pd.Series(
        [p[1] for p in prices_raw],
        index=pd.to_datetime([p[0] for p in prices_raw], unit="ms", utc=True),
    ).sort_index()

    volumes = pd.Series(
        [v[1] for v in volumes_raw],
        index=pd.to_datetime([v[0] for v in volumes_raw], unit="ms", utc=True),
    ).sort_index()

    bundle = IndicatorBundle(
        coin_id=coin_id,
        symbol=symbol,
        prices=prices,
        volumes=volumes,
    )

    _compute_momentum(bundle)
    _compute_trend(bundle)
    _compute_bollinger(bundle)
    _compute_risk(bundle)
    _compute_volume(bundle)

    return bundle


# ── Private helpers ──────────────────────────────────────────────────────────

def _compute_momentum(b: IndicatorBundle) -> None:
    """RSI and MACD."""
    rsi_series = ta.momentum.RSIIndicator(
        close=b.prices, window=RSI_PERIOD, fillna=False
    ).rsi()
    b.rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else float("nan")

    macd_obj = ta.trend.MACD(
        close=b.prices,
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL,
        fillna=False,
    )
    b.macd = float(macd_obj.macd().iloc[-1])
    b.macd_signal = float(macd_obj.macd_signal().iloc[-1])
    b.macd_hist = float(macd_obj.macd_diff().iloc[-1])


def _compute_trend(b: IndicatorBundle) -> None:
    """Short/long SMAs and short EMA."""
    b.sma_short = float(b.prices.rolling(SMA_SHORT).mean().iloc[-1])
    b.sma_long = float(b.prices.rolling(SMA_LONG).mean().iloc[-1])
    b.ema_short = float(b.prices.ewm(span=SMA_SHORT, adjust=False).mean().iloc[-1])


def _compute_bollinger(b: IndicatorBundle) -> None:
    """Bollinger Bands (middle = SMA 20, width = 2 std)."""
    bb = ta.volatility.BollingerBands(
        close=b.prices,
        window=BB_PERIOD,
        window_dev=BB_STD,
        fillna=False,
    )
    b.bb_upper = float(bb.bollinger_hband().iloc[-1])
    b.bb_middle = float(bb.bollinger_mavg().iloc[-1])
    b.bb_lower = float(bb.bollinger_lband().iloc[-1])
    if b.bb_middle and b.bb_middle != 0:
        b.bb_width = (b.bb_upper - b.bb_lower) / b.bb_middle
    else:
        b.bb_width = float("nan")


def _compute_risk(b: IndicatorBundle) -> None:
    """Daily returns, annualised return, volatility, Sharpe, max drawdown."""
    b.daily_returns = b.prices.pct_change().dropna()

    if b.daily_returns.empty:
        return

    mean_daily = float(b.daily_returns.mean())
    std_daily = float(b.daily_returns.std())

    b.annualised_return = (1 + mean_daily) ** 365 - 1
    b.annualised_volatility = std_daily * (365 ** 0.5)

    if b.annualised_volatility and b.annualised_volatility != 0:
        b.sharpe_ratio = b.annualised_return / b.annualised_volatility
    else:
        b.sharpe_ratio = float("nan")

    # Max drawdown
    cumulative = (1 + b.daily_returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    b.max_drawdown = float(drawdown.min())

    # 30-day change
    if len(b.prices) >= 30:
        b.change_30d = float(
            (b.prices.iloc[-1] - b.prices.iloc[-30]) / b.prices.iloc[-30]
        )


def _compute_volume(b: IndicatorBundle) -> None:
    """Volume SMA and ratio."""
    vol_sma = b.volumes.rolling(20).mean()
    b.volume_sma = float(vol_sma.iloc[-1]) if not vol_sma.empty else float("nan")
    current_vol = float(b.volumes.iloc[-1]) if not b.volumes.empty else float("nan")
    if b.volume_sma and b.volume_sma != 0:
        b.volume_ratio = current_vol / b.volume_sma
    else:
        b.volume_ratio = float("nan")


# ── Quick sanity helpers used by strategy ────────────────────────────────────

def is_rsi_oversold(b: IndicatorBundle) -> bool:
    return not np.isnan(b.rsi) and b.rsi < RSI_OVERSOLD


def is_rsi_overbought(b: IndicatorBundle) -> bool:
    return not np.isnan(b.rsi) and b.rsi > RSI_OVERBOUGHT


def is_macd_bullish(b: IndicatorBundle) -> bool:
    """MACD line crossed above signal (histogram turned positive)."""
    return not np.isnan(b.macd_hist) and b.macd_hist > 0


def is_price_near_bb_lower(b: IndicatorBundle, threshold: float = 0.02) -> bool:
    """Price within *threshold* fraction above the lower Bollinger Band."""
    if np.isnan(b.bb_lower):
        return False
    current = float(b.prices.iloc[-1])
    return current <= b.bb_lower * (1 + threshold)


def is_price_near_bb_upper(b: IndicatorBundle, threshold: float = 0.02) -> bool:
    """Price within *threshold* fraction below the upper Bollinger Band."""
    if np.isnan(b.bb_upper):
        return False
    current = float(b.prices.iloc[-1])
    return current >= b.bb_upper * (1 - threshold)


def is_golden_cross(b: IndicatorBundle) -> bool:
    """Short SMA above long SMA (uptrend)."""
    return (
        not np.isnan(b.sma_short)
        and not np.isnan(b.sma_long)
        and b.sma_short > b.sma_long
    )
