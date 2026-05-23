"""
Exposure Manager — enforces USD-quote group cap.

Rule: EUR/USD, GBP/USD, AUD/USD all quote in USD.
Only ONE open trade is allowed across the entire group at any time.

Session priority (Option A — soft):
  - 9 AM–5 PM ET:  EUR/USD has priority. If EUR and another pair both fire
                   simultaneously AND the group slot is already taken,
                   the other pair is suppressed.
  - 7 PM–10 PM ET: No setups run for these pairs (NY-only system).

State is persisted to forex_exposure.json so restarts don't lose open trades.
"""
import json, os
from datetime import datetime, timezone, timedelta

EST    = timezone(timedelta(hours=-4))
STATE_F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forex_exposure.json")

_USD_QUOTE_GROUP = {"EUR_USD", "GBP_USD", "AUD_USD"}


def _load() -> dict:
    if os.path.exists(STATE_F):
        try:
            with open(STATE_F) as f:
                return json.load(f)
        except Exception:
            pass
    return {"open_pair": None, "open_setup": None, "open_since": None}


def _save(state: dict):
    with open(STATE_F, "w") as f:
        json.dump(state, f, indent=2)


def get_open_pair() -> str | None:
    """Return the currently open pair, or None if the group slot is free."""
    return _load().get("open_pair")


def is_slot_free() -> bool:
    return get_open_pair() is None


def claim_slot(pair: str, setup_id: str):
    """Mark the USD-quote group slot as occupied by `pair`."""
    state = _load()
    state["open_pair"]   = pair
    state["open_setup"]  = setup_id
    state["open_since"]  = datetime.now(EST).isoformat()
    _save(state)
    print(f"  [EXPOSURE] Slot claimed by {pair} ({setup_id})")


def release_slot(pair: str):
    """Free the slot when a trade closes. Only releases if `pair` holds it."""
    state = _load()
    if state.get("open_pair") == pair:
        state["open_pair"]  = None
        state["open_setup"] = None
        state["open_since"] = None
        _save(state)
        print(f"  [EXPOSURE] Slot released by {pair}")


def can_take_signal(pair: str) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    allowed=False means suppress this signal — group slot is taken.
    """
    if pair not in _USD_QUOTE_GROUP:
        return True, "not in USD-quote group"
    state  = _load()
    holder = state.get("open_pair")
    if holder is None:
        return True, "group slot free"
    if holder == pair:
        return False, f"duplicate signal — {pair} already has open trade"
    return False, f"group slot held by {holder} — suppressing {pair}"


def session_priority_pair() -> str | None:
    """Return the session-priority pair based on current ET time."""
    now = datetime.now(EST)
    h   = now.hour
    if 9 <= h < 17:
        return "EUR_USD"
    return None
