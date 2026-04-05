"""
Ranking engine.

Scores each coin on four dimensions (Sharpe, momentum, volatility, volume)
and returns the top ``SELECTED_TOP_N`` candidates.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .analyzer import IndicatorBundle
from .config import (
    WEIGHT_SHARPE,
    WEIGHT_MOMENTUM,
    WEIGHT_VOLATILITY,
    WEIGHT_VOLUME,
    SELECTED_TOP_N,
)

logger = logging.getLogger(__name__)


@dataclass
class RankedCoin:
    bundle: IndicatorBundle
    score: float          # composite 0–100 score
    rank: int


# ── Normalisation helpers ─────────────────────────────────────────────────────

def _minmax(values: list[float]) -> list[float]:
    """Normalise a list to [0, 1]; returns zeros if all values equal."""
    finite = [v for v in values if not math.isnan(v) and not math.isinf(v)]
    if not finite:
        return [0.0] * len(values)
    lo, hi = min(finite), max(finite)
    if hi == lo:
        return [0.5] * len(values)
    return [
        (v - lo) / (hi - lo) if (not math.isnan(v) and not math.isinf(v)) else 0.0
        for v in values
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def rank_coins(bundles: Sequence[IndicatorBundle]) -> list[RankedCoin]:
    """
    Score and rank every bundle.

    Scoring dimensions:
    - **Sharpe ratio** – higher is better (risk-adjusted return).
    - **Momentum** – 30-day price change (higher is better).
    - **Volatility** – annualised volatility (lower is better, so we invert).
    - **Volume ratio** – current / SMA-20 volume (higher shows interest).
    """
    sharpe_vals = [b.sharpe_ratio for b in bundles]
    momentum_vals = [b.change_30d for b in bundles]
    volatility_vals = [b.annualised_volatility for b in bundles]
    volume_vals = [b.volume_ratio for b in bundles]

    sharpe_norm = _minmax(sharpe_vals)
    momentum_norm = _minmax(momentum_vals)
    # Invert volatility: high volatility → low score
    vol_norm_raw = _minmax(volatility_vals)
    vol_norm = [1.0 - v for v in vol_norm_raw]
    volume_norm = _minmax(volume_vals)

    ranked: list[RankedCoin] = []
    for i, b in enumerate(bundles):
        score = (
            WEIGHT_SHARPE * sharpe_norm[i]
            + WEIGHT_MOMENTUM * momentum_norm[i]
            + WEIGHT_VOLATILITY * vol_norm[i]
            + WEIGHT_VOLUME * volume_norm[i]
        ) * 100  # scale to 0–100

        ranked.append(RankedCoin(bundle=b, score=round(score, 2), rank=0))

    ranked.sort(key=lambda r: r.score, reverse=True)
    for position, r in enumerate(ranked[:SELECTED_TOP_N], start=1):
        r.rank = position

    top = ranked[:SELECTED_TOP_N]
    logger.info(
        "Top %d coins: %s",
        len(top),
        [f"{r.bundle.symbol.upper()}({r.score:.1f})" for r in top],
    )
    return top
