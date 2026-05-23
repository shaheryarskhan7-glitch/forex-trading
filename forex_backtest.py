"""
Gemini V2 Framework — 12-Month Forex Backtest  (V2 — 3 Pairs, S1+S2+S3 Only)
EUR/USD, GBP/USD, AUD/USD
USD/JPY excluded — 27% WR, -$992 over 12 months, Setup 4 EMA50 drove losses.
Setup 4 removed from all pairs.
Backtest period: 2025-05-01 to 2026-05-01
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import time
import sys
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
API_KEY  = "440095414e2322158df31299adcdf16e-4e9bae69162b11b2ee82843eab0d6de7"
BASE_URL = "https://api-fxpractice.oanda.com"

PAIRS = {
    "EUR_USD": {"pip": 0.0001, "max_spread": 1.5},
    "GBP_USD": {"pip": 0.0001, "max_spread": 2.0},
    "AUD_USD": {"pip": 0.0001, "max_spread": 1.8},
    # USD_JPY excluded — 27% WR, -$992 over 12 months. Setup 4 EMA50 drove losses.
}

ACCOUNT_BALANCE  = 10_000.0
RISK_PER_TRADE   = 100.0        # $100 = 1% of $10k
TP1_R            = 0.75
TP2_R            = 2.0
TP2_R_S1         = 1.618
SPREAD_PIPS      = {"EUR_USD": 1.2, "GBP_USD": 1.8, "AUD_USD": 1.5}

BACKTEST_FROM = "2025-05-01T00:00:00Z"
BACKTEST_TO   = "2026-05-01T00:00:00Z"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

# ─────────────────────────────────────────────
#  DATA FETCHING
# ─────────────────────────────────────────────
def fetch_candles(instrument: str, granularity: str,
                  from_dt: str, to_dt: str) -> pd.DataFrame:
    """
    Fetch OANDA candles in chunks of 5000.
    OANDA rejects requests that include both 'from', 'to', AND 'count'.
    Strategy: use 'from' + 'count', paginate via last candle time,
    stop when we pass to_dt.
    """
    all_rows = []
    chunk_from = from_dt
    to_limit = datetime.fromisoformat(to_dt.replace("Z", "+00:00"))
    url = f"{BASE_URL}/v3/instruments/{instrument}/candles"

    while True:
        params = {
            "granularity": granularity,
            "from":        chunk_from,
            "count":       5000,
            "price":       "BA",
        }
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  [WARN] fetch failed for {instrument} {granularity}: {e}")
            break

        data = r.json()
        candles = data.get("candles", [])
        if not candles:
            break

        new_rows = 0
        for c in candles:
            if not c.get("complete", True):
                continue
            try:
                c_time = datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
                if c_time >= to_limit:
                    continue
                row = {
                    "time":        pd.Timestamp(c["time"]),
                    "open_bid":    float(c["bid"]["o"]),
                    "high_bid":    float(c["bid"]["h"]),
                    "low_bid":     float(c["bid"]["l"]),
                    "close_bid":   float(c["bid"]["c"]),
                    "open_ask":    float(c["ask"]["o"]),
                    "high_ask":    float(c["ask"]["h"]),
                    "low_ask":     float(c["ask"]["l"]),
                    "close_ask":   float(c["ask"]["c"]),
                    "volume":      int(c.get("volume", 0)),
                }
                all_rows.append(row)
                new_rows += 1
            except Exception:
                continue

        last_time = candles[-1]["time"]
        last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))

        # Stop if we've gone past the end date
        if last_dt >= to_limit:
            break
        if len(candles) < 5000:
            break

        # Advance by 1 second from last candle
        next_dt  = last_dt + timedelta(seconds=1)
        chunk_from = next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        time.sleep(0.25)   # be kind to the API

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    # mid prices
    df["open"]  = (df["open_bid"]  + df["open_ask"])  / 2
    df["high"]  = (df["high_bid"]  + df["high_ask"])  / 2
    df["low"]   = (df["low_bid"]   + df["low_ask"])   / 2
    df["close"] = (df["close_bid"] + df["close_ask"]) / 2
    return df


# ─────────────────────────────────────────────
#  INDICATOR HELPERS
# ─────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def dema(series: pd.Series, period: int) -> pd.Series:
    e1 = ema(series, period)
    e2 = ema(e1, period)
    return 2 * e1 - e2

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=period - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df["high"], df["low"], df["close"]
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift()).abs(),
        (lo - cl.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()

def compute_indicators(df1h: pd.DataFrame) -> pd.DataFrame:
    """Add all needed indicators to 1H DataFrame."""
    df = df1h.copy()

    # 1H indicators
    df["ema50_1h"]  = ema(df["close"], 50)
    df["dema9_1h"]  = dema(df["close"], 9)
    df["rsi14_1h"]  = rsi(df["close"], 14)
    df["atr14_1h"]  = atr(df, 14)
    df["atr_sma20"]  = df["atr14_1h"].rolling(20).mean()

    # ─ 4H EMA50 (resample) ─
    df_4h = (
        df.set_index("time")
          .resample("4h", closed="left", label="left")
          .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
          .dropna()
    )
    df_4h["ema50_4h"] = ema(df_4h["close"], 50)
    # map back to 1H: forward fill
    df = df.set_index("time")
    df["ema50_4h"] = df_4h["ema50_4h"].reindex(df.index, method="ffill")
    df = df.reset_index()

    # ─ Daily EMA50 (resample) ─
    df_d = (
        df.set_index("time")
          .resample("1D", closed="left", label="left")
          .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
          .dropna()
    )
    df_d["ema50_d"] = ema(df_d["close"], 50)
    df = df.set_index("time")
    df["ema50_d"] = df_d["ema50_d"].reindex(df.index, method="ffill")
    df = df.reset_index()

    return df


# ─────────────────────────────────────────────
#  SESSION / TIME HELPERS
# ─────────────────────────────────────────────
ET_OFFSET = timedelta(hours=-4)   # ET = UTC-4 (approximation)

def to_et_hour(ts: pd.Timestamp) -> float:
    """Return decimal hour in ET for a UTC timestamp."""
    et = ts + ET_OFFSET
    return et.hour + et.minute / 60

def et_date(ts: pd.Timestamp) -> datetime:
    """Return ET date for grouping (date obj)."""
    et = ts + ET_OFFSET
    return et.date()

def is_rollover_blocked(h: float) -> bool:
    # 16:55 – 18:05 ET blocked
    return (h >= 16.917) or (h < 18.083 and h >= 16.917)

def blocked_window(h: float) -> bool:
    """Return True if this hour is in a blocked window."""
    if h >= 16.917 and h < 18.084:   # rollover 16:55–18:05
        return True
    if h >= 3.0 and h < 9.0:         # London 03:00–09:00
        return True
    return False


# ─────────────────────────────────────────────
#  SETUP LOGIC
# ─────────────────────────────────────────────
def score_gate(row, direction, pair_cfg):
    """
    Simplified 7-factor scoring; returns (score, passed).
    direction: 'long' or 'short'
    """
    score = 0
    pip = pair_cfg["pip"]

    # Factor 1: daily EMA50 aligned
    if direction == "long" and row["close"] > row["ema50_d"]:
        score += 1
    elif direction == "short" and row["close"] < row["ema50_d"]:
        score += 1

    # Factor 2: 4H EMA50 aligned
    if direction == "long" and row["close"] > row["ema50_4h"]:
        score += 1
    elif direction == "short" and row["close"] < row["ema50_4h"]:
        score += 1

    # Factor 3: 1H DEMA direction aligned
    if direction == "long" and row["dema9_1h"] > row.get("dema9_1h_prev", row["dema9_1h"]):
        score += 1
    elif direction == "short" and row["dema9_1h"] < row.get("dema9_1h_prev", row["dema9_1h"]):
        score += 1

    # Factor 4: RSI not extreme (longs < 65, shorts > 35)
    rsi_val = row["rsi14_1h"]
    if direction == "long" and rsi_val < 65:
        score += 1
    elif direction == "short" and rsi_val > 35:
        score += 1

    # Factor 5: ATR 0.7–1.4× of 20-bar SMA
    atr_val  = row["atr14_1h"]
    atr_sma  = row["atr_sma20"]
    if pd.notna(atr_sma) and atr_sma > 0:
        ratio = atr_val / atr_sma
        if 0.7 <= ratio <= 1.4:
            score += 1

    # Factor 6: breakout candle body > 60% of ATR (proxy for "range")
    body = abs(row["close"] - row["open"])
    if body > 0.6 * atr_val:
        score += 1

    # Factor 7: no conflicting trade (handled at call site — give +1 by default)
    score += 1

    return score, score >= 5


def find_setups_for_day(pair: str, day_df: pd.DataFrame,
                        pair_cfg: dict, prev_day_df: pd.DataFrame | None,
                        usd_quote_open: bool) -> list:
    """
    Given all 1H bars for a single ET date, return list of trade signals.
    Each signal: dict with keys: setup, direction, entry, sl, tp1, tp2,
                                  entry_time, pair
    """
    signals = []
    pip = pair_cfg["pip"]

    if len(day_df) < 5:
        return signals

    # Convenience: add dema prev column
    day_df = day_df.copy()
    day_df["dema9_1h_prev"] = day_df["dema9_1h"].shift(1)

    # ── Helper: bar index by ET hour ──────────────────────────────────────────
    def bars_in_window(h_start, h_end):
        mask = day_df["et_hour"].apply(
            lambda h: h_start <= h < h_end and not blocked_window(h)
        )
        return day_df[mask]

    # ═══════════════════════════════════════════════════════════════════════════
    #  SETUP 1 — Asian Range Break
    # ═══════════════════════════════════════════════════════════════════════════
    if pair in ("EUR_USD", "GBP_USD", "AUD_USD"):
        asia_bars = day_df[day_df["et_hour"].apply(lambda h: 0 <= h < 6)]
        if len(asia_bars) >= 2:
            range_high = asia_bars["high"].max()
            range_low  = asia_bars["low"].min()
            range_width_pips = (range_high - range_low) / pip
            if 20 <= range_width_pips <= 60:
                exec_bars = bars_in_window(9.0, 11.0)
                for _, row in exec_bars.iterrows():
                    # LONG breakout
                    if row["close"] > range_high:
                        direction = "long"
                        _, passed = score_gate(row, direction, pair_cfg)
                        if passed and not usd_quote_open:
                            atr_val = row["atr14_1h"]
                            entry = range_high
                            sl    = range_low - 0.5 * atr_val
                            tp1   = entry + (range_high - range_low)
                            tp2   = entry + 1.618 * (range_high - range_low)
                            signals.append({
                                "setup": 1, "direction": direction,
                                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                                "entry_time": row["time"],
                                "atr": atr_val,
                            })
                            break
                    # SHORT breakout
                    elif row["close"] < range_low:
                        direction = "short"
                        _, passed = score_gate(row, direction, pair_cfg)
                        if passed and not usd_quote_open:
                            atr_val = row["atr14_1h"]
                            entry = range_low
                            sl    = range_high + 0.5 * atr_val
                            tp1   = entry - (range_high - range_low)
                            tp2   = entry - 1.618 * (range_high - range_low)
                            signals.append({
                                "setup": 1, "direction": direction,
                                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                                "entry_time": row["time"],
                                "atr": atr_val,
                            })
                            break

    # ═══════════════════════════════════════════════════════════════════════════
    #  SETUP 2 — NY Open Liquidity Sweep  (EUR_USD, GBP_USD)
    # ═══════════════════════════════════════════════════════════════════════════
    if pair in ("EUR_USD", "GBP_USD"):
        london_bars = day_df[day_df["et_hour"].apply(lambda h: 3 <= h < 8.5)]
        if len(london_bars) >= 2:
            lon_high = london_bars["high"].max()
            lon_low  = london_bars["low"].min()
            lon_mid  = (lon_high + lon_low) / 2
            exec_bars = day_df[day_df["et_hour"].apply(lambda h: 9 <= h < 10.5)]
            added = False
            for _, row in exec_bars.iterrows():
                if added:
                    break
                atr_val = row["atr14_1h"]
                sweep_pip_h = (row["high"] - lon_high) / pip
                sweep_pip_l = (lon_low  - row["low"])  / pip

                # SHORT: spike above London high then closes back below
                if 5 <= sweep_pip_h <= 25 and row["close"] < lon_high:
                    direction = "short"
                    _, passed = score_gate(row, direction, pair_cfg)
                    if passed:
                        entry = lon_high
                        sl    = row["high"] + 0.3 * atr_val
                        tp1   = lon_mid
                        tp2   = lon_low
                        signals.append({
                            "setup": 2, "direction": direction,
                            "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                            "entry_time": row["time"],
                            "atr": atr_val,
                        })
                        added = True

                # LONG: spike below London low then closes back above
                elif 5 <= sweep_pip_l <= 25 and row["close"] > lon_low:
                    direction = "long"
                    _, passed = score_gate(row, direction, pair_cfg)
                    if passed:
                        entry = lon_low
                        sl    = row["low"] - 0.3 * atr_val
                        tp1   = lon_mid
                        tp2   = lon_high
                        signals.append({
                            "setup": 2, "direction": direction,
                            "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                            "entry_time": row["time"],
                            "atr": atr_val,
                        })
                        added = True

    # ═══════════════════════════════════════════════════════════════════════════
    #  SETUP 3 — PDH/PDL Sweep
    # ═══════════════════════════════════════════════════════════════════════════
    if prev_day_df is not None and len(prev_day_df) > 0:
        pdh = prev_day_df["high"].max()
        pdl = prev_day_df["low"].min()
        exec_bars = bars_in_window(9.0, 12.0)

        added = False
        for _, row in exec_bars.iterrows():
            if added:
                break
            atr_val = row["atr14_1h"]
            sweep_h_pips = (row["high"] - pdh) / pip
            sweep_l_pips = (pdl - row["low"])  / pip

            # SHORT: spike 3–20 pips above PDH, close back below
            if 3 <= sweep_h_pips <= 20 and row["close"] < pdh:
                direction = "short"
                _, passed = score_gate(row, direction, pair_cfg)
                if passed:
                    entry = pdh
                    sl    = row["high"] + 0.5 * atr_val
                    risk  = abs(entry - sl)
                    tp1   = entry - 0.75 * risk
                    tp2   = pdh - 1.5 * atr_val
                    signals.append({
                        "setup": 3, "direction": direction,
                        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "entry_time": row["time"],
                        "atr": atr_val,
                    })
                    added = True

            # LONG: spike 3–20 pips below PDL, close back above
            elif 3 <= sweep_l_pips <= 20 and row["close"] > pdl:
                direction = "long"
                _, passed = score_gate(row, direction, pair_cfg)
                if passed:
                    entry = pdl
                    sl    = row["low"] - 0.5 * atr_val
                    risk  = abs(entry - sl)
                    tp1   = entry + 0.75 * risk
                    tp2   = pdl + 1.5 * atr_val
                    signals.append({
                        "setup": 3, "direction": direction,
                        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "entry_time": row["time"],
                        "atr": atr_val,
                    })
                    added = True

    # Setup 4 (EMA50 Continuation) removed — drove losses on USD/JPY and EUR/USD.
    # Only Setups 1, 2, 3 are active.

    return signals


# ─────────────────────────────────────────────
#  TRADE SIMULATION
# ─────────────────────────────────────────────
def simulate_trade(signal: dict, future_bars: pd.DataFrame,
                   pair: str, setup_num: int,
                   kill_hour: float = 16.917) -> dict:
    """
    Walk future 1H bars; check SL first then TP within each bar (worst case).
    Returns dict with keys: outcome, pnl_r, pnl_usd, entry_time, exit_time, setup
    """
    pip     = PAIRS[pair]["pip"]
    spread  = SPREAD_PIPS[pair] * pip
    entry   = signal["entry"]
    sl      = signal["sl"]
    tp1     = signal["tp1"]
    tp2     = signal["tp2"]
    dirn    = signal["direction"]
    tp2_r   = TP2_R_S1 if setup_num == 1 else TP2_R

    tp1_hit = False
    new_sl  = sl   # after TP1 hit, SL moves to BE (entry)

    for _, bar in future_bars.iterrows():
        et_h = bar["et_hour"]

        # Session kill — all remaining pairs are NY session pairs
        if et_h >= 16.917:
            return _build_result(signal, bar, "flat", 0.0, pair)

        hi = bar["high"]
        lo = bar["low"]

        if dirn == "long":
            # Spread applied on entry (already baked in entry price effectively)
            # Check SL first (worst case)
            if lo <= new_sl:
                if tp1_hit:
                    pnl_r = TP1_R * 0.5 + (-1.0) * 0.5  # TP1 half + SL remaining
                    # but SL is now at BE so remaining is 0R
                    pnl_r = TP1_R * 0.5 + 0.0
                else:
                    pnl_r = -1.0
                pnl_usd = pnl_r * RISK_PER_TRADE - spread / pip * 0.01 * RISK_PER_TRADE
                return _build_result(signal, bar, "sl", pnl_r, pair, pnl_usd)
            # Check TP1
            if not tp1_hit and hi >= tp1:
                tp1_hit = True
                new_sl  = entry  # move to breakeven
            # Check TP2
            if tp1_hit and hi >= tp2:
                pnl_r   = TP1_R * 0.5 + tp2_r * 0.5
                pnl_usd = pnl_r * RISK_PER_TRADE - spread / pip * 0.01 * RISK_PER_TRADE
                return _build_result(signal, bar, "tp2", pnl_r, pair, pnl_usd)

        else:  # short
            if hi >= new_sl:
                if tp1_hit:
                    pnl_r = TP1_R * 0.5 + 0.0
                else:
                    pnl_r = -1.0
                pnl_usd = pnl_r * RISK_PER_TRADE - spread / pip * 0.01 * RISK_PER_TRADE
                return _build_result(signal, bar, "sl", pnl_r, pair, pnl_usd)
            if not tp1_hit and lo <= tp1:
                tp1_hit = True
                new_sl  = entry
            if tp1_hit and lo <= tp2:
                pnl_r   = TP1_R * 0.5 + tp2_r * 0.5
                pnl_usd = pnl_r * RISK_PER_TRADE - spread / pip * 0.01 * RISK_PER_TRADE
                return _build_result(signal, bar, "tp2", pnl_r, pair, pnl_usd)

    # Ran out of bars — close flat
    return _build_result(signal, future_bars.iloc[-1] if len(future_bars) > 0 else None,
                         "flat", 0.0, pair)


def _build_result(signal, bar, outcome, pnl_r, pair, pnl_usd=None):
    if pnl_usd is None:
        pnl_usd = pnl_r * RISK_PER_TRADE
    exit_time = bar["time"] if bar is not None else signal["entry_time"]
    return {
        "pair":       pair,
        "setup":      signal["setup"],
        "direction":  signal["direction"],
        "outcome":    outcome,
        "pnl_r":      pnl_r,
        "pnl_usd":    pnl_usd,
        "entry_time": signal["entry_time"],
        "exit_time":  exit_time,
        "entry":      signal["entry"],
        "sl":         signal["sl"],
        "tp1":        signal["tp1"],
        "tp2":        signal["tp2"],
    }


# ─────────────────────────────────────────────
#  MAIN BACKTEST LOOP PER PAIR
# ─────────────────────────────────────────────
def run_backtest_for_pair(pair: str, df1h: pd.DataFrame) -> list:
    pip = PAIRS[pair]["pip"]
    sp  = PAIRS[pair]["max_spread"]

    # Compute indicators
    print(f"  Computing indicators for {pair}...")
    df = compute_indicators(df1h)

    # Add ET hour
    df["et_hour"] = df["time"].apply(to_et_hour)
    df["et_date"] = df["time"].apply(et_date)

    # Build day groups
    day_groups = {d: grp.reset_index(drop=True)
                  for d, grp in df.groupby("et_date")}
    sorted_days = sorted(day_groups.keys())

    trades = []
    usd_quote_open = False   # exposure manager for EUR/GBP/AUD vs USD

    print(f"  Running signal generation for {pair} ({len(sorted_days)} trading days)...")

    for i, day in enumerate(sorted_days):
        day_df = day_groups[day]
        prev_df = day_groups[sorted_days[i - 1]] if i > 0 else None

        signals = find_setups_for_day(pair, day_df, PAIRS[pair], prev_df, usd_quote_open)

        for sig in signals:
            # Find future bars after entry
            entry_time = sig["entry_time"]
            future = df[df["time"] > entry_time].reset_index(drop=True)
            if future.empty:
                continue

            result = simulate_trade(sig, future, pair, sig["setup"])
            trades.append(result)

            if pair in ("EUR_USD", "GBP_USD", "AUD_USD"):
                if result["outcome"] in ("sl", "tp2", "flat"):
                    usd_quote_open = False
                else:
                    usd_quote_open = True

    return trades


# ─────────────────────────────────────────────
#  REPORTING
# ─────────────────────────────────────────────
def print_pair_report(pair: str, trades: list, all_months: list):
    print()
    print("=" * 60)
    print(f"  PAIR: {pair.replace('_','/')}  |  12-Month Backtest  May 2025 – May 2026")
    print("=" * 60)
    print(f"{'Month':<14} {'Trades':>6} {'Wins':>5} {'Losses':>7} {'WR%':>6} {'Net R':>9} {'Net P&L($)':>12}")
    print("-" * 60)

    total_trades = total_wins = total_losses = 0
    total_r = 0.0
    total_usd = 0.0
    month_results = {}

    setup_trades  = {1: [], 2: [], 3: []}

    for t in trades:
        setup_trades[t["setup"]].append(t)
        m_key = t["entry_time"].strftime("%b %Y")
        if m_key not in month_results:
            month_results[m_key] = {"trades": 0, "wins": 0, "losses": 0,
                                     "r": 0.0, "usd": 0.0}
        m = month_results[m_key]
        m["trades"] += 1
        if t["pnl_r"] > 0:
            m["wins"] += 1
        elif t["pnl_r"] < 0:
            m["losses"] += 1
        m["r"]   += t["pnl_r"]
        m["usd"] += t["pnl_usd"]

    best_m = worst_m = None
    best_v = -1e9
    worst_v = 1e9

    for mth in all_months:
        m_key = mth.strftime("%b %Y")
        m = month_results.get(m_key, {"trades": 0, "wins": 0, "losses": 0, "r": 0.0, "usd": 0.0})
        tr = m["trades"]; wi = m["wins"]; lo = m["losses"]
        wr = (wi / tr * 100) if tr > 0 else 0
        nr = m["r"]; np_ = m["usd"]

        sign_r = "+" if nr >= 0 else ""
        sign_u = "+" if np_ >= 0 else ""
        print(f"{m_key:<14} {tr:>6} {wi:>5} {lo:>7} {wr:>5.0f}% "
              f"{sign_r}{nr:>7.2f}  {sign_u}${np_:>9,.0f}")

        total_trades += tr; total_wins += wi; total_losses += lo
        total_r += nr; total_usd += np_

        if np_ > best_v:
            best_v = np_; best_m = m_key
        if np_ < worst_v:
            worst_v = np_; worst_m = m_key

    wr_total = (total_wins / total_trades * 100) if total_trades > 0 else 0
    sign_r = "+" if total_r >= 0 else ""
    sign_u = "+" if total_usd >= 0 else ""
    print("-" * 60)
    print(f"{'TOTAL':<14} {total_trades:>6} {total_wins:>5} {total_losses:>7} "
          f"{wr_total:>5.0f}% {sign_r}{total_r:>7.2f}  {sign_u}${total_usd:>9,.0f}")

    # Max drawdown
    running_usd = 0.0
    peak = 0.0
    max_dd = 0.0
    max_consec_losses = 0
    cur_losses = 0
    for t in sorted(trades, key=lambda x: x["entry_time"]):
        running_usd += t["pnl_usd"]
        if running_usd > peak:
            peak = running_usd
        dd = peak - running_usd
        if dd > max_dd:
            max_dd = dd
        if t["pnl_r"] < 0:
            cur_losses += 1
            if cur_losses > max_consec_losses:
                max_consec_losses = cur_losses
        else:
            cur_losses = 0

    avg_trades = total_trades / 12

    print(f"  Best month:  {best_m}  +${best_v:,.0f}")
    print(f"  Worst month: {worst_m}  ${worst_v:,.0f}")
    print(f"  Max drawdown: -${max_dd:,.0f} ({max_consec_losses} consecutive losses)")
    print(f"  Avg trades/month: {avg_trades:.1f}")

    setup_str_parts = []
    for s in [1, 2, 3]:
        st = setup_trades[s]
        if st:
            st_wins = sum(1 for t in st if t["pnl_r"] > 0)
            st_wr = st_wins / len(st) * 100
            setup_str_parts.append(f"Setup{s}: {len(st)} trades {st_wr:.0f}%WR")
        else:
            setup_str_parts.append(f"Setup{s}: 0 trades --")
    print("  Setup breakdown: " + " | ".join(setup_str_parts))

    return {
        "pair": pair,
        "trades": total_trades,
        "wins": total_wins,
        "losses": total_losses,
        "wr": wr_total,
        "total_r": total_r,
        "total_usd": total_usd,
        "best_m": best_m, "best_v": best_v,
        "worst_m": worst_m, "worst_v": worst_v,
        "max_dd": max_dd,
        "max_consec": max_consec_losses,
        "avg_trades": avg_trades,
        "month_results": month_results,
    }


def print_combined_report(pair_summaries: list, all_months: list):
    print()
    print("=" * 70)
    print("  COMBINED SUMMARY — 3 Pairs (S1+S2+S3)  |  May 2025 – May 2026")
    print("=" * 70)
    print(f"{'Month':<14} {'Trades':>6} {'Wins':>5} {'Losses':>7} {'WR%':>6} {'Net R':>9} {'Net P&L($)':>12}")
    print("-" * 70)

    combined_months = {}
    for ps in pair_summaries:
        for mth, m in ps["month_results"].items():
            if mth not in combined_months:
                combined_months[mth] = {"trades": 0, "wins": 0, "losses": 0, "r": 0.0, "usd": 0.0}
            cm = combined_months[mth]
            cm["trades"]  += m["trades"]
            cm["wins"]    += m["wins"]
            cm["losses"]  += m["losses"]
            cm["r"]       += m["r"]
            cm["usd"]     += m["usd"]

    gt = gw = gl = 0
    gr = gusd = 0.0
    best_m = worst_m = None
    best_v = -1e9; worst_v = 1e9

    for mth in all_months:
        m_key = mth.strftime("%b %Y")
        m = combined_months.get(m_key, {"trades": 0, "wins": 0, "losses": 0, "r": 0.0, "usd": 0.0})
        tr = m["trades"]; wi = m["wins"]; lo = m["losses"]
        wr = (wi / tr * 100) if tr > 0 else 0
        nr = m["r"]; np_ = m["usd"]
        sign_r = "+" if nr >= 0 else ""
        sign_u = "+" if np_ >= 0 else ""
        print(f"{m_key:<14} {tr:>6} {wi:>5} {lo:>7} {wr:>5.0f}% "
              f"{sign_r}{nr:>7.2f}  {sign_u}${np_:>9,.0f}")
        gt += tr; gw += wi; gl += lo; gr += nr; gusd += np_
        if np_ > best_v:
            best_v = np_; best_m = m_key
        if np_ < worst_v:
            worst_v = np_; worst_m = m_key

    gwr = (gw / gt * 100) if gt > 0 else 0
    sign_r = "+" if gr >= 0 else ""
    sign_u = "+" if gusd >= 0 else ""
    print("-" * 70)
    print(f"{'TOTAL':<14} {gt:>6} {gw:>5} {gl:>7} {gwr:>5.0f}% "
          f"{sign_r}{gr:>7.2f}  {sign_u}${gusd:>9,.0f}")
    print(f"  Best month:  {best_m}  +${best_v:,.0f}")
    print(f"  Worst month: {worst_m}  ${worst_v:,.0f}")
    print()
    print("  Per-Pair Summary:")
    for ps in pair_summaries:
        sign = "+" if ps["total_usd"] >= 0 else ""
        print(f"    {ps['pair'].replace('_','/'):<9}  {ps['trades']:>3} trades  "
              f"WR {ps['wr']:>4.0f}%  Net {sign}${ps['total_usd']:>7,.0f}  "
              f"MaxDD -${ps['max_dd']:,.0f}")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Gemini V2 Framework — 12-Month Forex Backtest  (V2)")
    print(f"  Period: May 2025 – May 2026")
    print(f"  Pairs:  EUR/USD  GBP/USD  AUD/USD  (Setups S1+S2+S3 only)")
    print(f"  USD/JPY excluded. Setup 4 removed from all pairs.")
    print("=" * 60)

    # Build list of 12 months for reporting
    all_months = []
    for y in [2025, 2026]:
        for m in range(1, 13):
            dt = datetime(y, m, 1, tzinfo=timezone.utc)
            if datetime(2025, 5, 1, tzinfo=timezone.utc) <= dt < datetime(2026, 5, 1, tzinfo=timezone.utc):
                all_months.append(dt)

    pair_summaries = []
    all_trades_by_pair = {}

    for pair in PAIRS.keys():
        print(f"\n[{pair}] Fetching 1H candles ({BACKTEST_FROM} to {BACKTEST_TO})...")
        df1h = fetch_candles(pair, "H1", BACKTEST_FROM, BACKTEST_TO)

        if df1h.empty:
            print(f"  [SKIP] No data for {pair}")
            continue

        print(f"  Fetched {len(df1h):,} 1H bars for {pair}")

        trades = run_backtest_for_pair(pair, df1h)
        all_trades_by_pair[pair] = trades
        print(f"  Total trades generated: {len(trades)}")

        summary = print_pair_report(pair, trades, all_months)
        pair_summaries.append(summary)

    # Combined
    if pair_summaries:
        print_combined_report(pair_summaries, all_months)

    print("\n[DONE] Backtest complete.")


if __name__ == "__main__":
    main()
