"""
Configuration constants for Criptonite.
"""

# ── Investment parameters ────────────────────────────────────────────────────
INVESTMENT_MIN_USD = 50.0
INVESTMENT_MAX_USD = 500.0
DEFAULT_INVESTMENT_USD = 100.0

# ── Coin universe ────────────────────────────────────────────────────────────
# Number of top-ranked coins to analyse.  We fetch more than 10 so that we
# can filter out stablecoins / wrapped tokens and still end up with 10 solid
# candidates.
FETCH_TOP_N = 30
SELECTED_TOP_N = 10

# IDs of stablecoins and wrapped tokens to exclude from ranking.
EXCLUDED_COIN_IDS = {
    "tether",
    "usd-coin",
    "binance-usd",
    "dai",
    "true-usd",
    "usdd",
    "frax",
    "paxos-standard",
    "gemini-dollar",
    "neutrino",
    "terrausd",
    "wrapped-bitcoin",
    "staked-ether",
    "wrapped-ether",
    "cdai",
    "usdp",
    "husd",
    "usdn",
    "euro-coin",
}

# ── Historical data ──────────────────────────────────────────────────────────
HISTORY_DAYS = 90          # days of OHLC / price history to fetch
PRICE_VS_CURRENCY = "usd"

# ── Technical-analysis thresholds ───────────────────────────────────────────
RSI_OVERSOLD = 35          # buy signal region
RSI_OVERBOUGHT = 65        # sell signal region
RSI_PERIOD = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2.0

SMA_SHORT = 20
SMA_LONG = 50

# ── Risk / ranking weights ───────────────────────────────────────────────────
WEIGHT_SHARPE = 0.35
WEIGHT_MOMENTUM = 0.30
WEIGHT_VOLATILITY = 0.20   # lower volatility → higher score
WEIGHT_VOLUME = 0.15

# ── Exchange fee defaults ────────────────────────────────────────────────────
DEFAULT_TAKER_FEE = 0.001  # 0.1 % (Binance / Coinbase standard)
MIN_PROFIT_TARGET = 0.015  # 1.5 % net gain before recommending sell

# ── CoinGecko API ────────────────────────────────────────────────────────────
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
API_TIMEOUT = 30           # seconds
API_RETRY_DELAY = 60       # seconds between retries when rate-limited
