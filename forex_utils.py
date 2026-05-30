"""
Shared OANDA data fetching + indicator calculations for all forex dashboards.
No Claude API — pure Python execution.
"""
import os, time, requests, json
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

from config import OANDA_API_KEY, OANDA_BASE_URL, FINNHUB_API_KEY, NEWS_BLOCK_ENABLED

EST = timezone(timedelta(hours=-4))

# ─── OANDA HELPERS ────────────────────────────────────────────────────────────

def _oanda_headers() -> dict:
    return {"Authorization": f"Bearer {OANDA_API_KEY}", "Content-Type": "application/json"}


def fetch_candles(instrument: str, granularity: str, count: int) -> pd.DataFrame:
    """Fetch the last `count` OANDA candles. Returns OHLC DataFrame."""
    url    = f"{OANDA_BASE_URL}/v3/instruments/{instrument}/candles"
    params = {"granularity": granularity, "count": count, "price": "M"}
    resp   = requests.get(url, headers=_oanda_headers(), params=params, timeout=15)
    resp.raise_for_status()
    candles = resp.json().get("candles", [])
    rows = []
    for c in candles:
        if c.get("complete", True):
            m = c["mid"]
            rows.append({
                "time":  c["time"],
                "open":  float(m["o"]),
                "high":  float(m["h"]),
                "low":   float(m["l"]),
                "close": float(m["c"]),
                "volume": int(c.get("volume", 0)),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time").sort_index()
    return df


def fetch_current_price(instrument: str) -> float:
    """Fetch live mid price from OANDA pricing endpoint."""
    url    = f"{OANDA_BASE_URL}/v3/accounts/{__import__('config').OANDA_ACCOUNT_ID}/pricing"
    params = {"instruments": instrument}
    resp   = requests.get(url, headers=_oanda_headers(), params=params, timeout=10)
    resp.raise_for_status()
    prices = resp.json().get("prices", [])
    if prices:
        bid = float(prices[0]["bids"][0]["price"])
        ask = float(prices[0]["asks"][0]["price"])
        return (bid + ask) / 2
    raise ValueError(f"No price returned for {instrument}")


def fetch_spread_pips(instrument: str) -> float:
    """Return current bid/ask spread in pips."""
    url    = f"{OANDA_BASE_URL}/v3/accounts/{__import__('config').OANDA_ACCOUNT_ID}/pricing"
    params = {"instruments": instrument}
    resp   = requests.get(url, headers=_oanda_headers(), params=params, timeout=10)
    resp.raise_for_status()
    prices = resp.json().get("prices", [])
    if prices:
        bid  = float(prices[0]["bids"][0]["price"])
        ask  = float(prices[0]["asks"][0]["price"])
        mult = 100 if "JPY" in instrument else 10000
        return round((ask - bid) * mult, 2)
    return 999.0   # fail safe — will block the trade


# ─── INDICATOR CALCULATIONS ───────────────────────────────────────────────────

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_dema(series: pd.Series, period: int) -> pd.Series:
    ema1 = calc_ema(series, period)
    ema2 = calc_ema(ema1, period)
    return 2 * ema1 - ema2


def calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def calc_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def build_indicators(instrument: str) -> dict:
    """
    Fetch 1H + Daily candles and compute all indicators needed for score gating.
    Returns a flat dict consumed by each dashboard's scorer.
    """
    df_1h    = fetch_candles(instrument, "H1", 120)
    df_4h    = fetch_candles(instrument, "H4",  80)
    df_daily = fetch_candles(instrument, "D",   60)

    close_1h    = df_1h["close"]
    close_4h    = df_4h["close"]
    close_daily = df_daily["close"]

    ema50_daily = float(calc_ema(close_daily, 50).iloc[-1])
    ema50_4h    = float(calc_ema(close_4h,   50).iloc[-1])
    dema9_1h    = calc_dema(close_1h, 9)
    dema9_prev  = float(dema9_1h.iloc[-2])
    dema9_curr  = float(dema9_1h.iloc[-1])

    rsi14_1h  = calc_rsi(close_1h, 14)
    atr14_1h  = calc_atr(df_1h, 14)
    atr_sma20 = float(calc_atr_series(df_1h, 14).rolling(20).mean().iloc[-1])

    price = float(close_1h.iloc[-1])

    return {
        "price":        price,
        "df_1h":        df_1h,
        "df_4h":        df_4h,
        "df_daily":     df_daily,
        "ema50_daily":  ema50_daily,
        "ema50_4h":     ema50_4h,
        "dema9_curr":   dema9_curr,
        "dema9_prev":   dema9_prev,
        "rsi14":        rsi14_1h,
        "atr14":        atr14_1h,
        "atr_sma20":    atr_sma20,
        "atr_ratio":    atr14_1h / atr_sma20 if atr_sma20 > 0 else 1.0,
        "trend_daily":  "BULL" if price > ema50_daily else "BEAR",
        "trend_4h":     "BULL" if price > ema50_4h    else "BEAR",
        "dema_dir":     "UP"   if dema9_curr > dema9_prev else "DOWN",
    }


# ─── SCORE GATE ───────────────────────────────────────────────────────────────

def score_common(ind: dict, direction: str,
                 breakout_body_ratio: float = None) -> tuple[int, list[str]]:
    """
    Evaluate the 7 common score factors.
    Returns (score, [factor descriptions]).
    direction: "LONG" or "SHORT"
    breakout_body_ratio: body/total_range of the trigger candle (Factor 6).
                         Pass None to skip Factor 6 (auto-award in some setups).
    """
    hits   = []
    score  = 0
    is_long = direction.upper() == "LONG"

    # F1 — Daily EMA50
    if (is_long and ind["trend_daily"] == "BULL") or (not is_long and ind["trend_daily"] == "BEAR"):
        score += 1; hits.append("F1:DailyEMA50 aligned")
    else:
        hits.append("F1:DailyEMA50 AGAINST")

    # F2 — 4H EMA50
    if (is_long and ind["trend_4h"] == "BULL") or (not is_long and ind["trend_4h"] == "BEAR"):
        score += 1; hits.append("F2:4H EMA50 aligned")
    else:
        hits.append("F2:4H EMA50 AGAINST")

    # F3 — 1H DEMA9 direction
    if (is_long and ind["dema_dir"] == "UP") or (not is_long and ind["dema_dir"] == "DOWN"):
        score += 1; hits.append("F3:DEMA9 aligned")
    else:
        hits.append("F3:DEMA9 AGAINST")

    # F4 — RSI not extreme
    rsi = ind["rsi14"]
    if (is_long and rsi < 65) or (not is_long and rsi > 35):
        score += 1; hits.append(f"F4:RSI {rsi:.1f} OK")
    else:
        hits.append(f"F4:RSI {rsi:.1f} EXTREME")

    # F5 — ATR regime
    ratio = ind["atr_ratio"]
    if 0.7 <= ratio <= 1.4:
        score += 1; hits.append(f"F5:ATR ratio {ratio:.2f} OK")
    else:
        hits.append(f"F5:ATR ratio {ratio:.2f} OUT OF RANGE")

    # F6 — Breakout candle body > 60%
    if breakout_body_ratio is not None:
        if breakout_body_ratio > 0.60:
            score += 1; hits.append(f"F6:Body {breakout_body_ratio:.0%} strong")
        else:
            hits.append(f"F6:Body {breakout_body_ratio:.0%} weak")
    else:
        score += 1; hits.append("F6:N/A (auto-pass)")

    # F7 — No conflicting USD exposure (managed by exposure_manager, auto-awarded here)
    score += 1; hits.append("F7:Exposure OK")

    return score, hits


# ─── NEWS BLOCK ───────────────────────────────────────────────────────────────

_NEWS_CACHE: dict = {}
_NEWS_CACHE_TS: float = 0
_NEWS_CACHE_TTL = 1800   # 30 min

def is_news_blocked() -> bool:
    """Return True if a high-impact USD/EUR/GBP/AUD event is within the block window."""
    if not NEWS_BLOCK_ENABLED or not FINNHUB_API_KEY:
        return False
    global _NEWS_CACHE, _NEWS_CACHE_TS
    now_ts = time.time()
    if now_ts - _NEWS_CACHE_TS > _NEWS_CACHE_TTL:
        try:
            today = datetime.now(EST).strftime("%Y-%m-%d")
            url   = f"https://finnhub.io/api/v1/calendar/economic?token={FINNHUB_API_KEY}"
            resp  = requests.get(url, timeout=8)
            _NEWS_CACHE    = resp.json()
            _NEWS_CACHE_TS = now_ts
        except Exception:
            return False

    now_et = datetime.now(EST)
    events = _NEWS_CACHE.get("economicCalendar", [])
    BLOCK_CURRENCIES = {"USD", "EUR", "GBP", "AUD"}
    BLOCK_IMPACTS    = {"high"}

    from config import NEWS_BLOCK_BEFORE_MIN, NEWS_BLOCK_AFTER_MIN
    for ev in events:
        if ev.get("impact", "").lower() not in BLOCK_IMPACTS:
            continue
        if ev.get("currency", "").upper() not in BLOCK_CURRENCIES:
            continue
        try:
            ev_time = datetime.fromisoformat(ev["time"].replace("Z", "+00:00")).astimezone(EST)
        except Exception:
            continue
        delta_min = (ev_time - now_et).total_seconds() / 60
        if -NEWS_BLOCK_AFTER_MIN <= delta_min <= NEWS_BLOCK_BEFORE_MIN:
            print(f"  [NEWS BLOCK] {ev.get('event')} in {delta_min:.0f} min")
            return True
    return False


# ─── SIGNAL LOG ───────────────────────────────────────────────────────────────

def log_signal(log_file: str, row: dict):
    """Append one signal row to the pair's CSV log.

    Deduplicates on (pair, setup, direction, entry, date) so service restarts
    don't re-log a signal that was already written in an earlier run.
    """
    import csv
    headers = [
        "timestamp", "pair", "setup", "direction",
        "entry", "sl", "tp1", "tp2", "score", "score_factors",
        "atr14", "rsi14", "trend_daily", "trend_4h", "dema_dir",
        "outcome", "exit_price", "resolved_time",
    ]
    row_date = str(row.get("timestamp", ""))[:10]
    if os.path.exists(log_file):
        with open(log_file, newline="") as f:
            for existing in csv.DictReader(f):
                if (existing.get("pair")      == str(row.get("pair"))
                        and existing.get("setup")     == str(row.get("setup"))
                        and existing.get("direction") == str(row.get("direction"))
                        and existing.get("entry")     == str(row.get("entry"))
                        and str(existing.get("timestamp", ""))[:10] == row_date):
                    return  # already logged — skip
    file_exists = os.path.exists(log_file)
    with open(log_file, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if not file_exists:
            w.writeheader()
        w.writerow(row)
