"""
Unit tests for the Portfolio module.
"""

from __future__ import annotations

import json
import os
import math
import tempfile
import pytest

from criptonite.portfolio import Portfolio, Position, ClosedTrade
from criptonite.config import DEFAULT_TAKER_FEE


class TestPortfolioOpenClose:
    def setup_method(self):
        # Use a temporary file so tests don't touch the real portfolio.json
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.tmp.close()
        # Point the portfolio to the temp file
        import criptonite.portfolio as pm
        self._orig_file = pm._PORTFOLIO_FILE
        pm._PORTFOLIO_FILE = self.tmp.name
        self.portfolio = Portfolio(fee_rate=DEFAULT_TAKER_FEE)

    def teardown_method(self):
        import criptonite.portfolio as pm
        pm._PORTFOLIO_FILE = self._orig_file
        os.unlink(self.tmp.name)

    def test_open_position_adds_to_positions(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        assert "bitcoin" in self.portfolio.positions

    def test_open_position_units_computed_correctly(self):
        fee = 100.0 * DEFAULT_TAKER_FEE
        expected_units = (100.0 - fee) / 30_000.0
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        pos = self.portfolio.positions["bitcoin"]
        assert abs(pos.units - expected_units) < 1e-10

    def test_open_position_reduces_cash(self):
        initial_cash = self.portfolio.cash_usd
        self.portfolio.open_position(
            "ethereum", "ETH", entry_price=2_000.0, investment_usd=100.0
        )
        assert self.portfolio.cash_usd == initial_cash - 100.0

    def test_close_position_removes_from_positions(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        self.portfolio.close_position("bitcoin", exit_price=35_000.0)
        assert "bitcoin" not in self.portfolio.positions

    def test_close_position_adds_to_history(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        trade = self.portfolio.close_position("bitcoin", exit_price=35_000.0)
        assert trade is not None
        assert len(self.portfolio.history) == 1

    def test_close_nonexistent_position_returns_none(self):
        result = self.portfolio.close_position("nonexistent", exit_price=100.0)
        assert result is None

    def test_profitable_trade_positive_pnl(self):
        self.portfolio.open_position(
            "ethereum", "ETH", entry_price=2_000.0, investment_usd=100.0
        )
        trade = self.portfolio.close_position("ethereum", exit_price=2_500.0)
        assert trade is not None
        assert trade.net_profit_usd > 0
        assert trade.net_profit_pct > 0

    def test_losing_trade_negative_pnl(self):
        self.portfolio.open_position(
            "ethereum", "ETH", entry_price=2_000.0, investment_usd=100.0
        )
        trade = self.portfolio.close_position("ethereum", exit_price=1_500.0)
        assert trade is not None
        assert trade.net_profit_usd < 0
        assert trade.net_profit_pct < 0

    def test_total_fees_deducted(self):
        self.portfolio.open_position(
            "solana", "SOL", entry_price=100.0, investment_usd=100.0
        )
        trade = self.portfolio.close_position("solana", exit_price=100.0)
        assert trade is not None
        # Break-even price without fees → with fees we should have a slight loss
        assert trade.net_profit_usd < 0

    def test_total_invested_property(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        self.portfolio.open_position(
            "ethereum", "ETH", entry_price=2_000.0, investment_usd=200.0
        )
        assert self.portfolio.total_invested == 300.0


class TestPortfolioPersistence:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.tmp.close()
        import criptonite.portfolio as pm
        self._orig_file = pm._PORTFOLIO_FILE
        pm._PORTFOLIO_FILE = self.tmp.name

    def teardown_method(self):
        import criptonite.portfolio as pm
        pm._PORTFOLIO_FILE = self._orig_file
        os.unlink(self.tmp.name)

    def test_save_and_reload(self):
        import criptonite.portfolio as pm
        p1 = Portfolio()
        p1.open_position("bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0)
        p1.save()

        p2 = Portfolio()
        assert "bitcoin" in p2.positions
        assert abs(p2.positions["bitcoin"].invested_usd - 100.0) < 1e-6


class TestUnrealisedPnL:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.tmp.close()
        import criptonite.portfolio as pm
        self._orig_file = pm._PORTFOLIO_FILE
        pm._PORTFOLIO_FILE = self.tmp.name
        self.portfolio = Portfolio()

    def teardown_method(self):
        import criptonite.portfolio as pm
        pm._PORTFOLIO_FILE = self._orig_file
        os.unlink(self.tmp.name)

    def test_unrealised_pnl_positive_when_price_rose(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        pnl = self.portfolio.unrealised_pnl({"bitcoin": 40_000.0})
        assert pnl["bitcoin"] > 0

    def test_unrealised_pnl_negative_when_price_fell(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        pnl = self.portfolio.unrealised_pnl({"bitcoin": 20_000.0})
        assert pnl["bitcoin"] < 0

    def test_unrealised_pnl_missing_price_skipped(self):
        self.portfolio.open_position(
            "bitcoin", "BTC", entry_price=30_000.0, investment_usd=100.0
        )
        pnl = self.portfolio.unrealised_pnl({})
        assert "bitcoin" not in pnl
