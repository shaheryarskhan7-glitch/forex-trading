"""
Forex Self-Learning Engine
==========================
Reads the three pair signal logs after each poll cycle, finds newly resolved
trades, extracts features, and updates the forex pattern store.

Same philosophy as gold's learner.py:
  - NEVER blocks setups — purely builds statistical context
  - All outcomes (wins AND losses) are training data
  - Adaptive weights and insights written back to forex_pattern_db.json

Call run_learning_cycle() from forex_monitor.py after each outcome check.
"""
import csv, json, os
from datetime import datetime, timezone, timedelta
import forex_pattern_store as ps

_EST = timezone(timedelta(hours=-4))
_DIR = os.path.dirname(os.path.abspath(__file__))

SIGNAL_LOGS = {
    "EUR_USD": os.path.join(_DIR, "forex_signal_log_EURUSD.csv"),
    "GBP_USD": os.path.join(_DIR, "forex_signal_log_GBPUSD.csv"),
    "AUD_USD": os.path.join(_DIR, "forex_signal_log_AUDUSD.csv"),
}

_LEARNED_IDS_F = os.path.join(_DIR, "forex_learned_ids.json")
_MIN_SAMPLES   = 5


# ─── ID tracking ─────────────────────────────────────────────────────────────

def _load_learned_ids() -> set:
    if not os.path.exists(_LEARNED_IDS_F):
        return set()
    try:
        with open(_LEARNED_IDS_F, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_learned_ids(ids: set):
    with open(_LEARNED_IDS_F, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def _signal_id(row: dict) -> str:
    """Stable dedup key: (date, pair, setup, entry rounded to 5 dp)."""
    try:
        entry = str(round(float(row.get("entry", 0)), 5))
    except (ValueError, TypeError):
        entry = row.get("entry", "")
    date  = (row.get("timestamp", "") or "")[:10]
    return f"{date}|{row.get('pair','')}|{row.get('setup','')}|{entry}"


# ─── Feature extraction ───────────────────────────────────────────────────────

def _rsi_zone(val) -> str:
    try:
        r = float(val)
        if r < 30:  return "oversold"
        if r < 45:  return "bearish"
        if r < 55:  return "neutral"
        if r < 70:  return "bullish"
        return "overbought"
    except (ValueError, TypeError):
        return "unknown"


def _trend_align(row: dict) -> str:
    """Count how many of daily/4h/dema agree with the trade direction."""
    direction = row.get("direction", "").upper()
    score = 0
    if row.get("trend_daily", "").upper() == ("BULL" if direction == "LONG" else "BEAR"):
        score += 1
    if row.get("trend_4h", "").upper() == ("BULL" if direction == "LONG" else "BEAR"):
        score += 1
    dema = row.get("dema_dir", "").upper()
    if (direction == "LONG" and dema == "UP") or (direction == "SHORT" and dema == "DOWN"):
        score += 1
    return str(score)


def _score_bucket(val) -> str:
    try:
        s = int(float(val))
        if s >= 7:  return "7"
        if s >= 6:  return "6"
        return "5"
    except (ValueError, TypeError):
        return "5"


def _setup_prefix(setup: str) -> str:
    """S1-AsianBreak → S1, S2-LiqSweep → S2, S3-PDSwoop → S3."""
    if not setup:
        return "UNKNOWN"
    return setup.split("-")[0].upper()


def _day_of_week(row: dict) -> str:
    try:
        dt = datetime.fromisoformat((row.get("timestamp", "") or "")[:10])
        return dt.strftime("%A")
    except Exception:
        return None


def extract_features(row: dict) -> dict:
    return {
        "pair":        row.get("pair", "UNKNOWN"),
        "setup":       _setup_prefix(row.get("setup", "")),
        "direction":   row.get("direction", "").upper() or "UNKNOWN",
        "rsi_zone":    _rsi_zone(row.get("rsi14", "")),
        "score_bucket": _score_bucket(row.get("score", "")),
        "trend_align": _trend_align(row),
    }


def _is_win(row: dict) -> bool:
    return row.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT")


# ─── Weight recalculation ─────────────────────────────────────────────────────

def _update_weights(store: dict):
    pats = store["patterns"]

    for pair in ("EUR_USD", "GBP_USD", "AUD_USD"):
        p = pats.get(f"pair:{pair}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"])
            store["weights"]["pair"][pair] = round(wr / 0.5, 3)

    for setup in ("S1", "S2", "S3"):
        p = pats.get(f"setup:{setup}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"])
            store["weights"]["setup"][setup] = round(wr / 0.5, 3)

    for direction in ("LONG", "SHORT"):
        p = pats.get(f"direction:{direction}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"])
            store["weights"]["direction"][direction] = round(wr / 0.5, 3)

    for zone in ("oversold", "bearish", "neutral", "bullish", "overbought"):
        p = pats.get(f"rsi_zone:{zone}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"])
            store["weights"]["rsi_zone"][zone] = round(wr / 0.5, 3)

    for bucket in ("5", "6", "7"):
        p = pats.get(f"score_bucket:{bucket}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"])
            store["weights"]["score_bucket"][bucket] = round(wr / 0.5, 3)


def _update_insights(store: dict):
    pats     = store["patterns"]
    insights = []

    for pair in ("EUR_USD", "GBP_USD", "AUD_USD"):
        p = pats.get(f"pair:{pair}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr  = ps.win_rate(p["wins"], p["total"]) * 100
            tag = "HIGH-CONFIDENCE" if wr > 65 else ("LOW-CONFIDENCE" if wr < 45 else "AVERAGE")
            insights.append(f"{pair.replace('_','/')}: {wr:.0f}% WR ({p['wins']}/{p['total']}) — {tag}")

    for setup in ("S1", "S2", "S3"):
        p = pats.get(f"setup:{setup}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"]) * 100
            if wr < 45:
                insights.append(f"{setup} setups: {wr:.0f}% — AVOID or tighten entry")
            elif wr > 65:
                insights.append(f"{setup} setups: {wr:.0f}% — PREFERRED, prioritise")

    for n in ("3", "2", "1"):
        p = pats.get(f"trend_align:{n}", {})
        if p.get("total", 0) >= _MIN_SAMPLES:
            wr = ps.win_rate(p["wins"], p["total"]) * 100
            insights.append(f"{n}/3 trend aligned: {wr:.0f}% WR ({p['wins']}/{p['total']})")

    store["insights"] = insights[:12]


# ─── Main cycle ───────────────────────────────────────────────────────────────

def run_learning_cycle() -> int:
    """
    Process newly resolved forex trades across all three pair logs.
    Returns the number of new trades learned.
    """
    all_rows = []
    for pair, log_file in SIGNAL_LOGS.items():
        if not os.path.exists(log_file):
            continue
        try:
            with open(log_file, newline="", encoding="utf-8") as f:
                all_rows.extend(list(csv.DictReader(f)))
        except Exception as e:
            print(f"  [FOREX LEARNER] Could not read {log_file}: {e}")

    if not all_rows:
        return 0

    learned_ids = _load_learned_ids()
    store       = ps.load()
    new_count   = 0

    for row in all_rows:
        outcome = row.get("outcome", "").strip()
        if not outcome:
            continue
        sig_id = _signal_id(row)
        if sig_id in learned_ids:
            continue

        features = extract_features(row)
        won      = _is_win(row)

        # 1. Single-feature patterns
        for feat, val in features.items():
            ps.update_pattern(store, f"{feat}:{val}", won)

        # 2. Combination patterns
        pair   = features["pair"]
        setup  = features["setup"]
        align  = features["trend_align"]
        rsi    = features["rsi_zone"]
        day    = _day_of_week(row)

        for combo in (
            f"pair:{pair}|setup:{setup}",
            f"pair:{pair}|direction:{features['direction']}",
            f"setup:{setup}|align:{align}",
            f"rsi:{rsi}|align:{align}",
            f"pair:{pair}|rsi:{rsi}",
        ):
            ps.update_pattern(store, combo, won)

        if day:
            ps.update_pattern(store, f"day:{day}", won)
            ps.update_pattern(store, f"pair:{pair}|day:{day}", won)

        learned_ids.add(sig_id)
        store["total_trades_learned"] += 1
        new_count += 1

    if new_count > 0:
        _update_weights(store)
        _update_insights(store)
        ps.save(store)
        _save_learned_ids(learned_ids)
        print(f"  [FOREX LEARNER] +{new_count} trade(s) learned. "
              f"Total={store['total_trades_learned']}  "
              f"Insights={len(store['insights'])}")

    return new_count
