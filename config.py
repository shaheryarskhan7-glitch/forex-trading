# ─── API KEYS ─────────────────────────────────────────────────────────────────
OANDA_API_KEY    = "440095414e2322158df31299adcdf16e-4e9bae69162b11b2ee82843eab0d6de7"
OANDA_ACCOUNT_ID = "101-002-38796697-001"
FINNHUB_API_KEY  = "d7r0i2pr01qtpsm0krq0d7r0i2pr01qtpsm0krqg"

# ─── OANDA SETTINGS ───────────────────────────────────────────────────────────
OANDA_BASE_URL = "https://api-fxpractice.oanda.com"

# ─── FOREX PAIRS ──────────────────────────────────────────────────────────────
PAIRS = ["EUR_USD", "GBP_USD", "AUD_USD"]

# ─── RISK PARAMETERS ──────────────────────────────────────────────────────────
ACCOUNT_SIZE      = 10_000     # USD
RISK_PCT          = 0.01       # 1% per trade → $100
RISK_PER_TRADE    = ACCOUNT_SIZE * RISK_PCT   # $100
MAX_TRADES_PER_DAY = 3

# ─── SPREAD THRESHOLDS (pips) — reject signal if spread exceeds this ──────────
MAX_SPREAD = {
    "EUR_USD": 1.5,
    "GBP_USD": 2.0,
    "AUD_USD": 1.8,
}

# ─── SESSION WINDOWS (ET hours) ───────────────────────────────────────────────
# NY Open setups (S1, S2, S3):  9:00 AM – 12:00 PM ET
# S1 strict window:             9:00 AM – 11:00 AM ET
# S2 strict window:             9:00 AM – 10:30 AM ET
# Rollover blackout:            4:55 PM – 6:05 PM ET
NY_OPEN_H      = 9
NY_CLOSE_H     = 12
S1_CLOSE_H     = 11
S1_CLOSE_M     = 0
S2_CLOSE_H     = 10
S2_CLOSE_M     = 30
SESSION_KILL_H = 16
SESSION_KILL_M = 55
ROLLOVER_END_H = 18
ROLLOVER_END_M = 5

# ─── NTFY PUSH NOTIFICATIONS ──────────────────────────────────────────────────
# Subscribe to this topic in the ntfy app on your phone
NTFY_TOPIC = "forex-signals-sk7"

# ─── NEWS BLOCK ───────────────────────────────────────────────────────────────
NEWS_BLOCK_ENABLED    = True
NEWS_BLOCK_BEFORE_MIN = 30   # minutes before high-impact event
NEWS_BLOCK_AFTER_MIN  = 15   # minutes after high-impact event

# ─── ATR REGIME THRESHOLDS ────────────────────────────────────────────────────
ATR_TOO_QUIET   = 0.6   # below 0.6× ATR SMA → dead market, block all
ATR_TOO_VOLATILE = 1.5  # above 1.5× ATR SMA → block EMA setups

# ─── TIMEZONE ─────────────────────────────────────────────────────────────────
TIMEZONE_OFFSET = -4    # EDT = UTC-4

# ─── SCORE GATE ───────────────────────────────────────────────────────────────
SCORE_GATE_MIN = 5      # minimum 5/7 to take a trade

# ─── GITHUB ───────────────────────────────────────────────────────────────────
GITHUB_ENABLED = True
GITHUB_REMOTE  = "origin"
GITHUB_BRANCH  = "main"
