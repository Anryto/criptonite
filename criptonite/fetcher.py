"""
Market-data fetcher.

Retrieves coin listings, current prices, and OHLC price history from
the CoinGecko public API (no API key required for the free tier).
"""

from __future__ import annotations

import time
import logging
from typing import Any

import requests

from .config import (
    COINGECKO_API_BASE,
    API_TIMEOUT,
    API_RETRY_DELAY,
    FETCH_TOP_N,
    HISTORY_DAYS,
    PRICE_VS_CURRENCY,
    EXCLUDED_COIN_IDS,
    SELECTED_TOP_N,
)

logger = logging.getLogger(__name__)


# ── Low-level HTTP helper ────────────────────────────────────────────────────

def _get(endpoint: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    """GET *endpoint* from CoinGecko, retrying on rate-limit (HTTP 429)."""
    url = f"{COINGECKO_API_BASE}{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=API_TIMEOUT)
            if resp.status_code == 429:
                logger.warning("Rate-limited by CoinGecko. Waiting %s s …", API_RETRY_DELAY)
                time.sleep(API_RETRY_DELAY)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Request error (attempt %s/%s): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(5)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_top_coins() -> list[dict[str, Any]]:
    """
    Return the top ``SELECTED_TOP_N`` coins by market cap, excluding
    stablecoins and wrapped tokens.

    Each dict contains at minimum:
    ``id``, ``symbol``, ``name``, ``current_price``, ``market_cap``,
    ``total_volume``, ``price_change_percentage_24h``,
    ``price_change_percentage_7d_in_currency``.
    """
    data: list[dict] = _get(
        "/coins/markets",
        params={
            "vs_currency": PRICE_VS_CURRENCY,
            "order": "market_cap_desc",
            "per_page": FETCH_TOP_N,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "7d,30d",
        },
    )

    filtered = [
        coin for coin in data if coin.get("id") not in EXCLUDED_COIN_IDS
    ][:SELECTED_TOP_N]

    logger.info("Fetched %d coins (after filtering).", len(filtered))
    return filtered


def fetch_price_history(coin_id: str, days: int = HISTORY_DAYS) -> dict[str, Any]:
    """
    Return OHLC + volume data for *coin_id* covering the last *days* days.

    Returns a dict with keys:
    - ``prices``:  list of [timestamp_ms, price]
    - ``volumes``: list of [timestamp_ms, volume]
    """
    data = _get(
        f"/coins/{coin_id}/market_chart",
        params={
            "vs_currency": PRICE_VS_CURRENCY,
            "days": days,
            "interval": "daily",
        },
    )
    return data


def fetch_coin_detail(coin_id: str) -> dict[str, Any]:
    """Return extended metadata for a single coin (description, links, etc.)."""
    return _get(
        f"/coins/{coin_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
        },
    )
