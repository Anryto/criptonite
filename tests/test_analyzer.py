"""
Unit tests for the technical-analysis (analyzer) module.

These tests use synthetic price/volume data so they run fully offline
without any network calls.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
import pandas as pd
import pytest

from criptonite import analyzer
from criptonite.analyzer import (
    IndicatorBundle,
    compute_indicators,
    is_golden_cross,
    is_macd_bullish,
    is_price_near_bb_lower,
    is_price_near_bb_upper,
    is_rsi_overbought,
    is_rsi_oversold,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_history(
    prices: list[float],
    volumes: list[float] | None = None,
) -> dict[str, Any]:
    """Build a CoinGecko-style market-chart dict from raw lists."""
    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000

    prices_ts = [[now_ms - (len(prices) - i) * day_ms, p] for i, p in enumerate(prices)]
    if volumes is None:
        volumes = [1_000_000.0] * len(prices)
    volumes_ts = [[now_ms - (len(volumes) - i) * day_ms, v] for i, v in enumerate(volumes)]

    return {"prices": prices_ts, "total_volumes": volumes_ts}


def _make_bundle(
    prices: list[float],
    volumes: list[float] | None = None,
    coin_id: str = "bitcoin",
    symbol: str = "btc",
) -> IndicatorBundle | None:
    history = _make_history(prices, volumes)
    return compute_indicators(coin_id, symbol, history)


def _trending_prices(n: int = 90, start: float = 10_000.0, slope: float = 50.0) -> list[float]:
    """Linearly rising prices."""
    return [start + i * slope for i in range(n)]


def _noisy_prices(n: int = 90, base: float = 50_000.0, noise: float = 500.0) -> list[float]:
    rng = np.random.default_rng(seed=42)
    return (base + rng.normal(0, noise, n)).tolist()


# ── Tests: compute_indicators ─────────────────────────────────────────────────

class TestComputeIndicators:
    def test_returns_bundle_with_enough_data(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert bundle.coin_id == "bitcoin"
        assert bundle.symbol == "btc"

    def test_returns_none_with_insufficient_data(self):
        prices = [100.0] * 20  # fewer than SMA_LONG + 5 = 55
        bundle = _make_bundle(prices)
        assert bundle is None

    def test_rsi_is_finite_for_valid_input(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert not math.isnan(bundle.rsi)
        assert 0 <= bundle.rsi <= 100

    def test_sma_short_less_than_sma_long_for_downtrend(self):
        """Falling prices: SMA20 should be below SMA50."""
        # Prices falling from high to low
        prices = [10_000 - i * 50 for i in range(90)]
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert bundle.sma_short < bundle.sma_long

    def test_sma_short_greater_than_sma_long_for_uptrend(self):
        """Rising prices: SMA20 should be above SMA50."""
        prices = _trending_prices(90, slope=100.0)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert bundle.sma_short > bundle.sma_long

    def test_bollinger_bands_ordering(self):
        prices = _noisy_prices(90)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert bundle.bb_lower < bundle.bb_middle < bundle.bb_upper

    def test_sharpe_ratio_computed(self):
        prices = _noisy_prices(90)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert not math.isnan(bundle.sharpe_ratio)

    def test_max_drawdown_is_negative_or_zero(self):
        prices = _noisy_prices(90)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert bundle.max_drawdown <= 0.0

    def test_volume_ratio_computed(self):
        prices = _trending_prices(90)
        volumes = [1_000_000.0 * (1 + 0.01 * i) for i in range(90)]
        bundle = _make_bundle(prices, volumes)
        assert bundle is not None
        assert not math.isnan(bundle.volume_ratio)
        assert bundle.volume_ratio > 0

    def test_change_30d_computed(self):
        prices = _trending_prices(90, start=100.0, slope=1.0)
        bundle = _make_bundle(prices)
        assert bundle is not None
        assert not math.isnan(bundle.change_30d)
        # 30 days of +1 on base 100 → ~23 % gain
        assert bundle.change_30d > 0


# ── Tests: signal helpers ─────────────────────────────────────────────────────

class TestSignalHelpers:
    """Test the boolean helper functions used by the strategy."""

    def _bundle_with_rsi(self, rsi_value: float) -> IndicatorBundle:
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        bundle.rsi = rsi_value
        return bundle

    def test_rsi_oversold_below_threshold(self):
        b = self._bundle_with_rsi(25.0)
        assert is_rsi_oversold(b)

    def test_rsi_not_oversold_above_threshold(self):
        b = self._bundle_with_rsi(50.0)
        assert not is_rsi_oversold(b)

    def test_rsi_overbought_above_threshold(self):
        b = self._bundle_with_rsi(75.0)
        assert is_rsi_overbought(b)

    def test_rsi_not_overbought_below_threshold(self):
        b = self._bundle_with_rsi(50.0)
        assert not is_rsi_overbought(b)

    def test_rsi_nan_is_not_oversold(self):
        b = self._bundle_with_rsi(float("nan"))
        assert not is_rsi_oversold(b)

    def test_macd_bullish_positive_histogram(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        bundle.macd_hist = 100.0
        assert is_macd_bullish(bundle)

    def test_macd_not_bullish_negative_histogram(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        bundle.macd_hist = -50.0
        assert not is_macd_bullish(bundle)

    def test_golden_cross_sma_short_above_long(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        bundle.sma_short = 200.0
        bundle.sma_long = 100.0
        assert is_golden_cross(bundle)

    def test_no_golden_cross_sma_short_below_long(self):
        prices = _trending_prices(90)
        bundle = _make_bundle(prices)
        bundle.sma_short = 100.0
        bundle.sma_long = 200.0
        assert not is_golden_cross(bundle)

    def test_price_near_bb_lower(self):
        prices = _noisy_prices(90)
        bundle = _make_bundle(prices)
        # Force price to be at lower BB
        current = bundle.bb_lower * 1.005  # 0.5 % above lower → within threshold
        # Update the last price in the series
        bundle.prices.iloc[-1] = current
        assert is_price_near_bb_lower(bundle)

    def test_price_near_bb_upper(self):
        prices = _noisy_prices(90)
        bundle = _make_bundle(prices)
        current = bundle.bb_upper * 0.995  # 0.5 % below upper → within threshold
        bundle.prices.iloc[-1] = current
        assert is_price_near_bb_upper(bundle)
