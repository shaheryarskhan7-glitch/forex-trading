"""
EUR/USD Dashboard — Setups S1 + S2 + S3
Pure Python, no Claude API.
"""
import os
from datetime import datetime, timezone, timedelta
import pandas as pd

from config import SCORE_GATE_MIN, MAX_SPREAD
from forex_utils import (
    build_indicators, fetch_candles, fetch_spread_pips,
    score_common, log_signal, is_news_blocked,
)

EST      = timezone(timedelta(hours=-4))
PAIR     = "EUR_USD"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forex_signal_log_EURUSD.csv")
PIP      = 0.0001   # 1 pip = 0.0001 for EUR/USD


def _body_ratio(candle: pd.Series) -> float:
    total = candle["high"] - candle["low"]
    if total == 0:
        return 0.0
    return abs(candle["close"] - candle["open"]) / total


def _asian_range(df_1h: pd.DataFrame) -> tuple[float, float] | None:
    """
    Asian range = high/low of 1H bars from 00:00–06:00 ET (midnight to 6 AM).
    Returns (range_high, range_low) or None if not enough data.
    """
    today  = datetime.now(EST).date()
    mask   = df_1h.index.tz_convert(EST)
    subset = df_1h[(mask.date == today) & (mask.hour >= 0) & (mask.hour < 6)]
    if len(subset) < 3:
        return None
    rh = float(subset["high"].max())
    rl = float(subset["low"].min())
    width_pips = (rh - rl) / PIP
    if not (20 <= width_pips <= 60):
        return None
    return rh, rl


def _london_range(df_5m: pd.DataFrame) -> tuple[float, float, float] | None:
    """
    London range = high/low of bars 03:00–08:30 ET.
    Returns (london_high, london_low, london_mid) or None.
    """
    today = datetime.now(EST).date()
    mask  = df_5m.index.tz_convert(EST)
    subset = df_5m[
        (mask.date == today) &
        ((mask.hour > 3) | ((mask.hour == 3) & (mask.minute >= 0))) &
        ((mask.hour < 8) | ((mask.hour == 8) & (mask.minute < 30)))
    ]
    if len(subset) < 10:
        return None
    lh  = float(subset["high"].max())
    ll  = float(subset["low"].min())
    lm  = (lh + ll) / 2
    return lh, ll, lm


def _pdh_pdl(df_1h: pd.DataFrame) -> tuple[float, float] | None:
    """Previous calendar day's high and low."""
    today  = datetime.now(EST).date()
    mask   = df_1h.index.tz_convert(EST)
    subset = df_1h[mask.date < today]
    if subset.empty:
        return None
    prev_day_bars = subset[mask[mask.date < today].date == mask[mask.date < today].date.max()]
    if prev_day_bars.empty:
        return None
    return float(prev_day_bars["high"].max()), float(prev_day_bars["low"].min())


# ─── SETUP 1 — Asian Range Break ──────────────────────────────────────────────

def check_s1(ind: dict) -> dict | None:
    """Returns armed setup dict or None."""
    now = datetime.now(EST)
    # Strict window: 9:00 AM – 11:00 AM ET
    if not (9 <= now.hour < 11):
        return None

    ar = _asian_range(ind["df_1h"])
    if ar is None:
        return None
    rh, rl = ar
    price   = ind["price"]
    atr14   = ind["atr14"]
    df_1h   = ind["df_1h"]
    last    = df_1h.iloc[-1]

    direction = None
    entry     = None
    sl = tp1 = tp2 = None
    body_ratio = _body_ratio(last)
    range_w = rh - rl

    if last["close"] > rh:                  # breakout above
        direction = "LONG"
        entry = rh
        sl    = rl - 0.5 * atr14
        tp1   = entry + range_w
        tp2   = entry + 1.618 * range_w
    elif last["close"] < rl:                # breakout below
        direction = "SHORT"
        entry = rl
        sl    = rh + 0.5 * atr14
        tp1   = entry - range_w
        tp2   = entry - 1.618 * range_w

    if direction is None:
        return None

    score, factors = score_common(ind, direction, body_ratio)
    if score < SCORE_GATE_MIN:
        return None

    return {
        "pair": PAIR, "setup": "S1-AsianBreak", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5),    "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


# ─── SETUP 2 — NY Liquidity Sweep ─────────────────────────────────────────────

def check_s2(ind: dict) -> dict | None:
    """Returns armed setup dict or None."""
    now = datetime.now(EST)
    # Strict window: 9:00 AM – 10:30 AM ET
    if not (9 <= now.hour < 10 or (now.hour == 10 and now.minute < 30)):
        return None

    df_5m = fetch_candles(PAIR, "M5", 200)
    if df_5m.empty:
        return None

    lr = _london_range(df_5m)
    if lr is None:
        return None
    lh, ll, lm = lr
    price  = ind["price"]
    atr14  = ind["atr14"]

    # Look at last 3 five-minute candles for a sweep
    recent = df_5m.iloc[-3:]
    direction = None
    entry = sl = tp1 = tp2 = None

    for _, c in recent.iterrows():
        above_pips = (c["high"] - lh) / PIP
        below_pips = (ll - c["low"])  / PIP
        if 5 <= above_pips <= 25 and c["close"] < lh:   # swept London high, closed back in
            direction = "SHORT"
            entry = lh
            sl    = c["high"] + 0.3 * atr14
            tp1   = lm
            tp2   = ll
            break
        if 5 <= below_pips <= 25 and c["close"] > ll:   # swept London low, closed back in
            direction = "LONG"
            entry = ll
            sl    = c["low"] - 0.3 * atr14
            tp1   = lm
            tp2   = lh
            break

    if direction is None:
        return None

    score, factors = score_common(ind, direction)
    if score < SCORE_GATE_MIN:
        return None

    return {
        "pair": PAIR, "setup": "S2-LiqSweep", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5),    "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


# ─── SETUP 3 — PDH/PDL Sweep ──────────────────────────────────────────────────

def check_s3(ind: dict) -> dict | None:
    """Returns armed setup dict or None."""
    now = datetime.now(EST)
    # Window: 9:00 AM – 2:00 PM ET
    if not (9 <= now.hour < 14):
        return None

    pdh_pdl = _pdh_pdl(ind["df_1h"])
    if pdh_pdl is None:
        return None
    pdh, pdl = pdh_pdl
    atr14  = ind["atr14"]
    df_1h  = ind["df_1h"]
    last   = df_1h.iloc[-1]

    direction = None
    entry = sl = tp1 = tp2 = None

    above_pips = (last["high"] - pdh) / PIP
    below_pips = (pdl - last["low"])  / PIP

    if 3 <= above_pips <= 20 and last["close"] < pdh:   # swept PDH
        direction = "SHORT"
        entry = pdh
        sl    = last["high"] + 0.5 * atr14
        risk  = abs(entry - sl)
        tp1   = entry - 0.75 * risk
        tp2   = pdh - 1.5 * atr14
    elif 3 <= below_pips <= 20 and last["close"] > pdl:  # swept PDL
        direction = "LONG"
        entry = pdl
        sl    = last["low"] - 0.5 * atr14
        risk  = abs(entry - sl)
        tp1   = entry + 0.75 * risk
        tp2   = pdl + 1.5 * atr14

    if direction is None:
        return None

    score, factors = score_common(ind, direction, _body_ratio(last))
    if score < SCORE_GATE_MIN:
        return None

    return {
        "pair": PAIR, "setup": "S3-PDSwoop", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5),    "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


# ─── SETUP 4 — Post-News Sweep ────────────────────────────────────────────────

_NEWS_SPIKE_MULT    = 2.0   # bar range > 2x ATR SMA = news spike
_POST_NEWS_MIN_PIPS = 3
_POST_NEWS_MAX_PIPS = 25


def check_s4_pn(ind: dict) -> dict | None:
    """
    Post-news sweep: detect a news spike (bar range > 2x ATR SMA) in the
    last 1-3 bars, then look for a sweep-and-reverse of the spike high/low
    on the current bar. Window 9 AM - 3 PM ET.
    Uses pre-spike ATR (atr_sma20) for the score ATR-ratio factor.
    """
    now = datetime.now(EST)
    if not (9 <= now.hour < 15):
        return None

    df_1h     = ind["df_1h"]
    atr_sma20 = ind["atr_sma20"]
    if len(df_1h) < 5 or atr_sma20 <= 0:
        return None

    # Scan the last 3 complete bars (before the current bar) for a spike
    spike_high = spike_low = None
    for lookback in range(1, 4):
        bar = df_1h.iloc[-(lookback + 1)]
        if (bar["high"] - bar["low"]) > _NEWS_SPIKE_MULT * atr_sma20:
            spike_high = float(bar["high"])
            spike_low  = float(bar["low"])
            break

    if spike_high is None:
        return None

    last = df_1h.iloc[-1]
    sh   = (last["high"] - spike_high) / PIP   # pips above spike high
    sb   = (spike_low  - last["low"])  / PIP   # pips below spike low

    direction = entry = sl = tp1 = tp2 = None

    if _POST_NEWS_MIN_PIPS <= sh <= _POST_NEWS_MAX_PIPS and last["close"] < spike_high:
        direction = "SHORT"
        entry = spike_high
        sl    = last["high"] + 0.5 * atr_sma20
        risk  = abs(entry - sl)
        tp1   = entry - 0.75 * risk
        tp2   = entry - 1.5  * atr_sma20
    elif _POST_NEWS_MIN_PIPS <= sb <= _POST_NEWS_MAX_PIPS and last["close"] > spike_low:
        direction = "LONG"
        entry = spike_low
        sl    = last["low"] - 0.5 * atr_sma20
        risk  = abs(entry - sl)
        tp1   = entry + 0.75 * risk
        tp2   = entry + 1.5  * atr_sma20

    if direction is None:
        return None

    # Score with pre-spike ATR ratio so F5 isn't blocked by spike volatility
    ind_pn = dict(ind)
    ind_pn["atr_ratio"] = 1.0
    score, factors = score_common(ind_pn, direction, _body_ratio(last))
    if score < SCORE_GATE_MIN:
        return None

    return {
        "pair": PAIR, "setup": "S4-PostNews", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5),    "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr_sma20, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def eur_usd_main() -> list[dict]:
    """
    Run all setups for EUR/USD. Returns list of armed signal dicts.
    Spread check and news block applied before returning.
    """
    # Spread check
    spread = fetch_spread_pips(PAIR)
    if spread > MAX_SPREAD[PAIR]:
        print(f"  [EUR/USD] Spread {spread} pips > max {MAX_SPREAD[PAIR]} — blocked")
        return []

    # News block
    if is_news_blocked():
        print(f"  [EUR/USD] News block active — skipping")
        return []

    ind    = build_indicators(PAIR)
    armed  = []
    now_ts = datetime.now(EST).isoformat()

    for checker in (check_s1, check_s2, check_s3, check_s4_pn):
        sig = checker(ind)
        if sig:
            sig["timestamp"] = now_ts
            log_signal(LOG_FILE, sig)
            armed.append(sig)

    return armed
