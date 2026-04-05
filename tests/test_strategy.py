"""
Unit tests for the strategy module.

All tests are offline (no network calls).
"""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from criptonite.analyzer import compute_indicators
from criptonite.config import (
    DEFAULT_INVESTMENT_USD,
    DEFAULT_TAKER_FEE,
    INVESTMENT_MIN_USD,
    INVESTMENT_MAX_USD,
)
from criptonite.ranker import rank_coins
from criptonite.strategy import (
    Signal,
    TradeRecommendation,
    generate_recommendations,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_history(prices: list[float]) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000
    pts = [[now_ms - (len(prices) - i) * day_ms, p] for i, p in enumerate(prices)]
    vols = [[now_ms - (len(prices) - i) * day_ms, 1_000_000.0] for i in range(len(prices))]
    return {"prices": pts, "total_volumes": vols}


def _make_ranked(coin_id: str, prices: list[float]):
    b = compute_indicators(coin_id, coin_id[:3], _make_history(prices))
    if b is None:
        return []
    return rank_coins([b])


# ── Tests: generate_recommendations ──────────────────────────────────────────

class TestGenerateRecommendations:
    def _ranked_coins(self):
        b = compute_indicators(
            "bitcoin", "btc",
            _make_history([30_000 + i * 100 for i in range(90)])
        )
        assert b is not None
        return rank_coins([b])

    def test_returns_list_of_trade_recommendations(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert isinstance(recs, list)
        assert len(recs) == 1
        assert isinstance(recs[0], TradeRecommendation)

    def test_investment_clamped_to_minimum(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(
            ranked, {"bitcoin": "Bitcoin"}, investment_usd=10.0
        )
        assert recs[0].investment_usd == INVESTMENT_MIN_USD

    def test_investment_clamped_to_maximum(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(
            ranked, {"bitcoin": "Bitcoin"}, investment_usd=9_999.0
        )
        assert recs[0].investment_usd == INVESTMENT_MAX_USD

    def test_investment_within_range_used_as_is(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(
            ranked, {"bitcoin": "Bitcoin"}, investment_usd=250.0
        )
        assert recs[0].investment_usd == 250.0

    def test_signal_is_valid_enum(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert recs[0].signal in list(Signal)

    def test_entry_price_at_or_below_current(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        rec = recs[0]
        assert rec.entry_price <= rec.current_price

    def test_target_above_entry(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert recs[0].target_price > recs[0].entry_price

    def test_stop_loss_below_entry(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert recs[0].stop_loss_price < recs[0].entry_price

    def test_units_positive(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert recs[0].units > 0

    def test_buy_and_sell_fees_positive(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        rec = recs[0]
        assert rec.buy_fee > 0
        assert rec.sell_fee > 0

    def test_net_profit_pct_finite(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        assert not math.isnan(recs[0].net_profit_pct)

    def test_signals_are_lists(self):
        ranked = self._ranked_coins()
        recs = generate_recommendations(ranked, {"bitcoin": "Bitcoin"})
        rec = recs[0]
        assert isinstance(rec.buy_signals, list)
        assert isinstance(rec.sell_signals, list)


# ── Tests: fee accounting ────────────────────────────────────────────────────

class TestFeeAccounting:
    """Verify that fees are properly deducted."""

    def test_zero_fee_increases_net_profit(self):
        b = compute_indicators(
            "eth", "eth",
            _make_history([2_000 + i * 10 for i in range(90)])
        )
        assert b is not None
        ranked = rank_coins([b])

        rec_with_fee = generate_recommendations(
            ranked, {"eth": "Ethereum"},
            investment_usd=100.0, fee_rate=DEFAULT_TAKER_FEE
        )[0]
        rec_no_fee = generate_recommendations(
            ranked, {"eth": "Ethereum"},
            investment_usd=100.0, fee_rate=0.0
        )[0]
        assert rec_no_fee.net_profit_usd > rec_with_fee.net_profit_usd

    def test_higher_fee_reduces_net_profit(self):
        b = compute_indicators(
            "sol", "sol",
            _make_history([100 + i for i in range(90)])
        )
        assert b is not None
        ranked = rank_coins([b])

        rec_low_fee = generate_recommendations(
            ranked, {"sol": "Solana"},
            investment_usd=100.0, fee_rate=0.001
        )[0]
        rec_high_fee = generate_recommendations(
            ranked, {"sol": "Solana"},
            investment_usd=100.0, fee_rate=0.01
        )[0]
        assert rec_low_fee.net_profit_usd > rec_high_fee.net_profit_usd
