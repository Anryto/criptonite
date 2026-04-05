"""
Unit tests for the ranker module.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from criptonite.analyzer import compute_indicators
from criptonite.ranker import RankedCoin, rank_coins


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_history(prices: list[float]) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000
    pts = [[now_ms - (len(prices) - i) * day_ms, p] for i, p in enumerate(prices)]
    vols = [[now_ms - (len(prices) - i) * day_ms, 1_000_000.0] for i in range(len(prices))]
    return {"prices": pts, "total_volumes": vols}


def _build_bundle(coin_id: str, symbol: str, prices: list[float]):
    return compute_indicators(coin_id, symbol, _make_history(prices))


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRankCoins:
    def _make_bundles(self):
        # Three synthetic coins: trending up, flat, trending down
        up = _build_bundle("coin_up", "UP", [100 + i * 2 for i in range(90)])
        flat = _build_bundle("coin_flat", "FL", [500.0] * 90)
        down = _build_bundle("coin_down", "DN", [1000 - i * 5 for i in range(90)])
        return [b for b in [up, flat, down] if b is not None]

    def test_returns_list_of_ranked_coins(self):
        bundles = self._make_bundles()
        ranked = rank_coins(bundles)
        assert isinstance(ranked, list)
        assert all(isinstance(r, RankedCoin) for r in ranked)

    def test_rank_numbers_are_sequential(self):
        bundles = self._make_bundles()
        ranked = rank_coins(bundles)
        ranks = [r.rank for r in ranked]
        assert ranks == list(range(1, len(ranked) + 1))

    def test_scores_are_between_0_and_100(self):
        bundles = self._make_bundles()
        ranked = rank_coins(bundles)
        for r in ranked:
            assert 0 <= r.score <= 100

    def test_coins_sorted_by_score_descending(self):
        bundles = self._make_bundles()
        ranked = rank_coins(bundles)
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input_returns_empty(self):
        assert rank_coins([]) == []

    def test_single_bundle_ranked_first(self):
        b = _build_bundle("btc", "btc", [100 + i for i in range(90)])
        assert b is not None
        ranked = rank_coins([b])
        assert len(ranked) == 1
        assert ranked[0].rank == 1

    def test_at_most_selected_top_n_returned(self):
        from criptonite.config import SELECTED_TOP_N
        # Create more bundles than SELECTED_TOP_N
        bundles = []
        for i in range(SELECTED_TOP_N + 5):
            b = _build_bundle(f"coin_{i}", f"C{i}", [100 + i + j for j in range(90)])
            if b:
                bundles.append(b)
        ranked = rank_coins(bundles)
        assert len(ranked) <= SELECTED_TOP_N
