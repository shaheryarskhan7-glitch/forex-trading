"""
GBP/USD Dashboard — Setups S1 + S2 + S3
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
PAIR     = "GBP_USD"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forex_signal_log_GBPUSD.csv")
PIP      = 0.0001


def _body_ratio(candle: pd.Series) -> float:
    total = candle["high"] - candle["low"]
    if total == 0:
        return 0.0
    return abs(candle["close"] - candle["open"]) / total


def _asian_range(df_1h: pd.DataFrame) -> tuple[float, float] | None:
    today  = datetime.now(EST).date()
    mask   = df_1h.index.tz_convert(EST)
    subset = df_1h[(mask.date == today) & (mask.hour >= 0) & (mask.hour < 6)]
    if len(subset) < 3:
        return None
    rh = float(subset["high"].max())
    rl = float(subset["low"].min())
    if not (20 <= (rh - rl) / PIP <= 60):
        return None
    return rh, rl


def _london_range(df_5m: pd.DataFrame) -> tuple[float, float, float] | None:
    today = datetime.now(EST).date()
    mask  = df_5m.index.tz_convert(EST)
    subset = df_5m[
        (mask.date == today) &
        ((mask.hour > 3) | ((mask.hour == 3) & (mask.minute >= 0))) &
        ((mask.hour < 8) | ((mask.hour == 8) & (mask.minute < 30)))
    ]
    if len(subset) < 10:
        return None
    lh = float(subset["high"].max())
    ll = float(subset["low"].min())
    return lh, ll, (lh + ll) / 2


def _pdh_pdl(df_1h: pd.DataFrame) -> tuple[float, float] | None:
    today  = datetime.now(EST).date()
    mask   = df_1h.index.tz_convert(EST)
    subset = df_1h[mask.date < today]
    if subset.empty:
        return None
    prev_dates = mask[mask.date < today].date
    prev_day_bars = subset[prev_dates == prev_dates.max()]
    if prev_day_bars.empty:
        return None
    return float(prev_day_bars["high"].max()), float(prev_day_bars["low"].min())


def check_s1(ind: dict) -> dict | None:
    now = datetime.now(EST)
    if not (9 <= now.hour < 11):
        return None
    ar = _asian_range(ind["df_1h"])
    if ar is None:
        return None
    rh, rl  = ar
    atr14   = ind["atr14"]
    last    = ind["df_1h"].iloc[-1]
    range_w = rh - rl
    body_r  = _body_ratio(last)

    direction = entry = sl = tp1 = tp2 = None
    if last["close"] > rh:
        direction = "LONG";  entry = rh
        sl  = rl  - 0.5 * atr14
        tp1 = entry + range_w;  tp2 = entry + 1.618 * range_w
    elif last["close"] < rl:
        direction = "SHORT"; entry = rl
        sl  = rh  + 0.5 * atr14
        tp1 = entry - range_w;  tp2 = entry - 1.618 * range_w
    if direction is None:
        return None

    score, factors = score_common(ind, direction, body_r)
    if score < SCORE_GATE_MIN:
        return None
    return {
        "pair": PAIR, "setup": "S1-AsianBreak", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5), "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


def check_s2(ind: dict) -> dict | None:
    now = datetime.now(EST)
    if not (9 <= now.hour < 10 or (now.hour == 10 and now.minute < 30)):
        return None
    df_5m = fetch_candles(PAIR, "M5", 200)
    if df_5m.empty:
        return None
    lr = _london_range(df_5m)
    if lr is None:
        return None
    lh, ll, lm = lr
    atr14  = ind["atr14"]
    recent = df_5m.iloc[-3:]

    direction = entry = sl = tp1 = tp2 = None
    for _, c in recent.iterrows():
        above = (c["high"] - lh) / PIP
        below = (ll - c["low"]) / PIP
        if 5 <= above <= 25 and c["close"] < lh:
            direction = "SHORT"; entry = lh
            sl = c["high"] + 0.3 * atr14; tp1 = lm; tp2 = ll; break
        if 5 <= below <= 25 and c["close"] > ll:
            direction = "LONG";  entry = ll
            sl = c["low"] - 0.3 * atr14; tp1 = lm; tp2 = lh; break
    if direction is None:
        return None

    score, factors = score_common(ind, direction)
    if score < SCORE_GATE_MIN:
        return None
    return {
        "pair": PAIR, "setup": "S2-LiqSweep", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5), "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


def check_s3(ind: dict) -> dict | None:
    now = datetime.now(EST)
    if not (9 <= now.hour < 14):
        return None
    pdh_pdl = _pdh_pdl(ind["df_1h"])
    if pdh_pdl is None:
        return None
    pdh, pdl = pdh_pdl
    atr14 = ind["atr14"]
    last  = ind["df_1h"].iloc[-1]

    direction = entry = sl = tp1 = tp2 = None
    above = (last["high"] - pdh) / PIP
    below = (pdl - last["low"])  / PIP

    if 3 <= above <= 20 and last["close"] < pdh:
        direction = "SHORT"; entry = pdh
        sl = last["high"] + 0.5 * atr14; risk = abs(entry - sl)
        tp1 = entry - 0.75 * risk; tp2 = pdh - 1.5 * atr14
    elif 3 <= below <= 20 and last["close"] > pdl:
        direction = "LONG";  entry = pdl
        sl = last["low"] - 0.5 * atr14; risk = abs(entry - sl)
        tp1 = entry + 0.75 * risk; tp2 = pdl + 1.5 * atr14
    if direction is None:
        return None

    score, factors = score_common(ind, direction, _body_ratio(last))
    if score < SCORE_GATE_MIN:
        return None
    return {
        "pair": PAIR, "setup": "S3-PDSwoop", "direction": direction,
        "entry": round(entry, 5), "sl": round(sl, 5),
        "tp1": round(tp1, 5), "tp2": round(tp2, 5),
        "score": score, "score_factors": "|".join(factors),
        "atr14": round(atr14, 5), "rsi14": ind["rsi14"],
        "trend_daily": ind["trend_daily"], "trend_4h": ind["trend_4h"],
        "dema_dir": ind["dema_dir"],
    }


_NEWS_SPIKE_MULT    = 2.0
_POST_NEWS_MIN_PIPS = 3
_POST_NEWS_MAX_PIPS = 25


def check_s4_pn(ind: dict) -> dict | None:
    """Post-news sweep. Window 9 AM - 3 PM ET. See EUR/USD for full docstring."""
    now = datetime.now(EST)
    if not (9 <= now.hour < 15):
        return None

    df_1h     = ind["df_1h"]
    atr_sma20 = ind["atr_sma20"]
    if len(df_1h) < 5 or atr_sma20 <= 0:
        return None

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
    sh   = (last["high"] - spike_high) / PIP
    sb   = (spike_low  - last["low"])  / PIP

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


def gbp_usd_main() -> list[dict]:
    spread = fetch_spread_pips(PAIR)
    if spread > MAX_SPREAD[PAIR]:
        print(f"  [GBP/USD] Spread {spread} pips > max {MAX_SPREAD[PAIR]} — blocked")
        return []
    if is_news_blocked():
        print(f"  [GBP/USD] News block active — skipping")
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
