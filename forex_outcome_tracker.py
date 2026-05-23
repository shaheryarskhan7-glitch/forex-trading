"""
Forex Outcome Tracker — resolves open signals against current price.
Called every poll cycle by forex_monitor.py.

Logic mirrors gold's outcome_tracker.py:
  - SL/TP1/TP2 checked against current price
  - SL always wins if it and TP fired in same poll window
  - Releases the exposure slot when a trade closes
"""
import csv, os
from datetime import datetime, timezone, timedelta
from notifier import push
from forex_exposure_manager import release_slot

EST = timezone(timedelta(hours=-4))

LOG_FILES = {
    "EUR_USD": "forex_signal_log_EURUSD.csv",
    "GBP_USD": "forex_signal_log_GBPUSD.csv",
    "AUD_USD": "forex_signal_log_AUDUSD.csv",
}

ALL_HEADERS = [
    "timestamp", "pair", "setup", "direction",
    "entry", "sl", "tp1", "tp2", "score", "score_factors",
    "atr14", "rsi14", "trend_daily", "trend_4h", "dema_dir",
    "worst_price", "outcome", "exit_price", "resolved_time",
]


def _pip_factor(pair: str) -> float:
    return 100 if "JPY" in pair else 10000


def _resolve(row: dict, price: float) -> tuple[str, float] | None:
    try:
        sl  = float(row["sl"])
        tp1 = float(row["tp1"])
        tp2 = float(row["tp2"])
        d   = row["direction"].upper()
        wp  = float(row.get("worst_price") or price)
    except (ValueError, KeyError):
        return None

    if d == "LONG":
        wp = min(wp, price)
        if wp <= sl:
            return "SL_HIT", sl
        if price >= tp2:
            return "TP2_HIT", tp2
        if price >= tp1:
            return "TP1_HIT", tp1
    else:
        wp = max(wp, price)
        if wp >= sl:
            return "SL_HIT", sl
        if price <= tp2:
            return "TP2_HIT", tp2
        if price <= tp1:
            return "TP1_HIT", tp1
    return None


def _update_worst(row: dict, price: float) -> float:
    try:
        wp = float(row.get("worst_price") or price)
    except ValueError:
        wp = price
    if row["direction"].upper() == "LONG":
        return min(wp, price)
    return max(wp, price)


def _read_log(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write_log(path: str, rows: list[dict]):
    if not rows:
        return
    headers = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def check_and_update(pair: str, price: float):
    log_file = LOG_FILES.get(pair)
    if not log_file or not os.path.exists(log_file):
        return

    rows    = _read_log(log_file)
    changed = False

    for row in rows:
        if row.get("outcome"):
            continue
        if row.get("pair", pair) != pair:
            continue

        row["worst_price"] = _update_worst(row, price)
        result = _resolve(row, price)

        if result:
            outcome, exit_px = result
            row["outcome"]      = outcome
            row["exit_price"]   = round(exit_px, 5)
            row["resolved_time"] = datetime.now(EST).isoformat()
            changed = True

            pip_f = _pip_factor(pair)
            pnl_r = (exit_px - float(row["entry"])) / abs(float(row["sl"]) - float(row["entry"]))
            if row["direction"].upper() == "SHORT":
                pnl_r = -pnl_r
            pnl_r = round(pnl_r, 2)
            pnl_usd = round(pnl_r * 100, 0)   # $100 risk per trade

            color = "white_check_mark" if outcome != "SL_HIT" else "x"
            push(
                f"FOREX {outcome} — {pair.replace('_','/')} {row['setup']}",
                f"{row['direction']} | Entry: {row['entry']} → Exit: {exit_px}\n"
                f"P&L: {'+' if pnl_r >= 0 else ''}{pnl_r}R  (${'+' if pnl_usd >= 0 else ''}{pnl_usd:.0f})\n"
                f"Score: {row['score']}/7",
                priority="high" if outcome != "SL_HIT" else "default",
                tags=color,
            )
            release_slot(pair)

    if changed:
        # Ensure all headers present
        for row in rows:
            for h in ALL_HEADERS:
                row.setdefault(h, "")
        _write_log(log_file, rows)


def check_all(prices: dict[str, float]):
    """prices = {"EUR_USD": 1.08500, "GBP_USD": 1.27300, "AUD_USD": 0.64200}"""
    for pair, price in prices.items():
        try:
            check_and_update(pair, price)
        except Exception as e:
            print(f"  [OUTCOME {pair}] {e}")


def session_flat(pair: str, price: float):
    """Force-close all open trades for a pair at session kill time."""
    log_file = LOG_FILES.get(pair)
    if not log_file or not os.path.exists(log_file):
        return
    rows    = _read_log(log_file)
    changed = False
    for row in rows:
        if row.get("outcome"):
            continue
        if row.get("pair", pair) != pair:
            continue
        row["outcome"]       = "SESSION_FLAT"
        row["exit_price"]    = round(price, 5)
        row["resolved_time"] = datetime.now(EST).isoformat()
        changed = True
        push(
            f"FOREX SESSION FLAT — {pair.replace('_','/')}",
            f"{row['direction']} {row['setup']} closed at market: {price}",
            priority="default",
            tags="alarm_clock",
        )
        release_slot(pair)
    if changed:
        for row in rows:
            for h in ALL_HEADERS:
                row.setdefault(h, "")
        _write_log(log_file, rows)
