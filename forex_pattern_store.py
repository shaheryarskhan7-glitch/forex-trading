"""
Forex Pattern Store — persists learned trade-outcome statistics to forex_pattern_db.json.
Mirrors gold's pattern_store.py but lives in the forex-trading directory.
"""
import json, os
from datetime import datetime, timezone, timedelta

_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forex_pattern_db.json")
_EST  = timezone(timedelta(hours=-4))

_PRIOR_WIN = 0.5
_PRIOR_N   = 4

_DEFAULT: dict = {
    "patterns":             {},
    "weights": {
        "pair":       {"EUR_USD": 1.0, "GBP_USD": 1.0, "AUD_USD": 1.0},
        "setup":      {},
        "direction":  {"LONG": 1.0, "SHORT": 1.0},
        "rsi_zone":   {},
        "score_bucket": {},
    },
    "insights":             [],
    "total_trades_learned": 0,
    "last_updated":         None,
}


def load() -> dict:
    if not os.path.exists(_FILE):
        import copy
        return copy.deepcopy(_DEFAULT)
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        import copy
        return copy.deepcopy(_DEFAULT)


def save(store: dict) -> None:
    store["last_updated"] = datetime.now(_EST).isoformat()
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, _FILE)


def update_pattern(store: dict, key: str, won: bool) -> None:
    if key not in store["patterns"]:
        store["patterns"][key] = {"wins": 0, "losses": 0, "total": 0}
    p = store["patterns"][key]
    p["total"] += 1
    if won:
        p["wins"] += 1
    else:
        p["losses"] += 1


def win_rate(wins: int, total: int) -> float:
    return (wins + _PRIOR_WIN * _PRIOR_N) / (total + _PRIOR_N)


def get_win_rate(store: dict, key: str) -> float:
    p = store["patterns"].get(key, {})
    return win_rate(p.get("wins", 0), p.get("total", 0))
