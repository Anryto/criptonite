"""
Integration smoke test: verifies the full pipeline (fetch → analyze → rank →
strategy → report) without any network calls, using patched API responses.
"""

from __future__ import annotations

import math
import time
from typing import Any
from unittest.mock import patch

from criptonite import analyzer, fetcher, ranker, strategy, reporter
from criptonite.config import SELECTED_TOP_N


# ── Fake API data ──────────────────────────────────────────────────────────────

def _fake_top_coins(n: int = SELECTED_TOP_N) -> list[dict]:
    """Generate n fake coins (non-stablecoin IDs)."""
    coins = []
    for i in range(n):
        coins.append({
            "id": f"fake_coin_{i}",
            "symbol": f"FC{i}",
            "name": f"FakeCoin {i}",
            "current_price": 1000.0 + i * 100,
            "market_cap": 1e11 - i * 1e9,
            "total_volume": 1e9,
            "price_change_percentage_24h": 1.0 + i * 0.1,
            "price_change_percentage_7d_in_currency": 5.0 + i * 0.5,
        })
    return coins


def _fake_price_history(coin_id: str) -> dict[str, Any]:
    """Synthetic 90-day price + volume history."""
    idx = int(coin_id.split("_")[-1])
    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000
    base = 1000.0 + idx * 100
    slope = 5.0 + idx * 0.5

    prices = [
        [now_ms - (90 - i) * day_ms, base + i * slope]
        for i in range(90)
    ]
    volumes = [
        [now_ms - (90 - i) * day_ms, 1_000_000.0 + i * 10_000]
        for i in range(90)
    ]
    return {"prices": prices, "total_volumes": volumes}


# ── Smoke test ─────────────────────────────────────────────────────────────────

class TestFullPipeline:
    def test_pipeline_produces_recommendations(self):
        # Patch network calls
        with patch.object(fetcher, "fetch_top_coins", return_value=_fake_top_coins()), \
             patch.object(fetcher, "fetch_price_history", side_effect=_fake_price_history):

            top_coins = fetcher.fetch_top_coins()
            assert len(top_coins) == SELECTED_TOP_N

            coin_names = {c["id"]: c["name"] for c in top_coins}
            bundles = []
            for coin in top_coins:
                history = fetcher.fetch_price_history(coin["id"])
                b = analyzer.compute_indicators(coin["id"], coin["symbol"], history)
                if b is not None:
                    bundles.append(b)

            assert len(bundles) == SELECTED_TOP_N

            ranked = ranker.rank_coins(bundles)
            assert len(ranked) == SELECTED_TOP_N
            assert ranked[0].rank == 1

            recs = strategy.generate_recommendations(
                ranked, coin_names, investment_usd=100.0
            )
            assert len(recs) == SELECTED_TOP_N

            for rec in recs:
                assert rec.signal in list(strategy.Signal)
                assert rec.entry_price <= rec.current_price
                assert rec.target_price > rec.entry_price
                assert rec.stop_loss_price < rec.entry_price
                assert not math.isnan(rec.net_profit_pct)
                assert rec.investment_usd == 100.0

    def test_reporter_does_not_raise(self, capsys):
        """reporter.print_report must run without exceptions."""
        with patch.object(fetcher, "fetch_top_coins", return_value=_fake_top_coins(3)), \
             patch.object(fetcher, "fetch_price_history", side_effect=_fake_price_history):

            top_coins = fetcher.fetch_top_coins()
            coin_names = {c["id"]: c["name"] for c in top_coins}
            bundles = [
                b for c in top_coins
                if (b := analyzer.compute_indicators(
                    c["id"], c["symbol"],
                    fetcher.fetch_price_history(c["id"])
                )) is not None
            ]
            ranked = ranker.rank_coins(bundles)
            recs = strategy.generate_recommendations(ranked, coin_names)

            # Should not raise
            reporter.print_report(recs, investment_usd=100.0, fee_rate=0.001)
