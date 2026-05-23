"""
Forex Monitor — Session-aware polling loop.
Mirrors gold monitor.py structure.

Session windows (ET):
  NY Open    9:00 AM – 12:00 PM  → 3-min polls  [all 3 pairs]
  Off-hours  all other times     → 30-min sleep  [no setups]

Hard session kills:
  4:55 PM ET  — all open NY trades closed at market
  Rollover block: 4:55 PM – 6:05 PM ET — no new signals

Status push to phone every 45 minutes.
"""
import time, os, sys, importlib, traceback
from datetime import datetime, timezone, timedelta

from config import TIMEZONE_OFFSET
from notifier import push, alert_forex

EST = timezone(timedelta(hours=TIMEZONE_OFFSET))

STATUS_PUSH_INTERVAL = 2700   # 45 min


def now_est():
    return datetime.now(EST)


def in_rollover() -> bool:
    n = now_est()
    h, m = n.hour, n.minute
    return (h == 16 and m >= 55) or (h == 17) or (h == 18 and m < 5)


def in_trading_window() -> bool:
    n    = now_est()
    h    = n.hour
    wday = n.weekday()   # 0=Mon, 6=Sun
    if wday == 5:                        # Saturday — closed
        return False
    if wday == 6 and h < 19:             # Sunday before 7 PM
        return False
    if wday == 4 and h >= 17:            # Friday after 5 PM
        return False
    if in_rollover():
        return False
    return 9 <= h < 17                   # 9 AM – 5 PM ET


def get_interval() -> int:
    n = now_est()
    if 9 <= n.hour < 12:
        return 180    # 3 min — NY Open (most active window)
    if 12 <= n.hour < 17:
        return 300    # 5 min — NY afternoon (less active)
    return 1800       # 30 min — off-hours


def session_name() -> str:
    n = now_est()
    h = n.hour
    if 9 <= h < 12:
        return "NY OPEN (3 min)"
    if 12 <= h < 17:
        return "NY AFTERNOON (5 min)"
    return "OFF-SESSION (sleeping)"


def run_all_pairs() -> dict:
    """
    Run EUR/USD, GBP/USD, AUD/USD dashboards with exposure gate.
    Returns dict of armed signals per pair.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import eur_usd_dashboard as eur
    import gbp_usd_dashboard as gbp
    import aud_usd_dashboard as aud
    import forex_exposure_manager as exp

    importlib.reload(eur)
    importlib.reload(gbp)
    importlib.reload(aud)

    results = {"EUR_USD": [], "GBP_USD": [], "AUD_USD": []}

    for pair, module, fn in [
        ("EUR_USD", eur, eur.eur_usd_main),
        ("GBP_USD", gbp, gbp.gbp_usd_main),
        ("AUD_USD", aud, aud.aud_usd_main),
    ]:
        allowed, reason = exp.can_take_signal(pair)
        if not allowed:
            print(f"  [{pair}] Blocked by exposure manager: {reason}")
            continue
        try:
            signals = fn()
        except Exception as e:
            print(f"  [{pair}] Error: {e}")
            traceback.print_exc()
            signals = []

        for sig in signals:
            # Claim the group slot for the first arming signal
            if not exp.get_open_pair():
                exp.claim_slot(pair, sig["setup"])
            alert_forex(
                pair      = sig["pair"],
                setup     = sig["setup"],
                direction = sig["direction"],
                entry     = sig["entry"],
                sl        = sig["sl"],
                tp1       = sig["tp1"],
                tp2       = sig["tp2"],
                score     = sig["score"],
                reason    = sig["score_factors"],
            )
        results[pair] = signals

    return results


def run_outcome_checks():
    """Poll current prices and resolve open trades."""
    try:
        import forex_outcome_tracker as ot
        import forex_utils as fu
        importlib.reload(ot)
        prices = {}
        for pair in ["EUR_USD", "GBP_USD", "AUD_USD"]:
            try:
                prices[pair] = fu.fetch_current_price(pair)
            except Exception as e:
                print(f"  [PRICE {pair}] {e}")
        if prices:
            ot.check_all(prices)
            # Run learning cycle after outcomes are updated
            try:
                import forex_learner
                importlib.reload(forex_learner)
                forex_learner.run_learning_cycle()
            except Exception as lrn_err:
                print(f"  [FOREX LEARNER] {lrn_err}")
        return prices
    except Exception as e:
        print(f"  [OUTCOME] {e}")
        return {}


def do_session_flat():
    """Force-close all open trades at 4:55 PM ET."""
    try:
        import forex_outcome_tracker as ot
        import forex_utils as fu
        importlib.reload(ot)
        for pair in ["EUR_USD", "GBP_USD", "AUD_USD"]:
            try:
                price = fu.fetch_current_price(pair)
                ot.session_flat(pair, price)
            except Exception as e:
                print(f"  [SESSION FLAT {pair}] {e}")
    except Exception as e:
        print(f"  [SESSION FLAT] {e}")


def send_status_push(results: dict, prices: dict):
    """45-min heartbeat — summary of all three pairs."""
    any_armed = any(len(v) > 0 for v in results.values())
    lines     = []
    for pair, sigs in results.items():
        p    = pair.replace("_", "/")
        px   = prices.get(pair, "?")
        px_s = f"{px:.5f}" if isinstance(px, float) else str(px)
        n    = len(sigs)
        if n:
            setups = ", ".join(f"{s['setup']} {s['direction']} {s['score']}/7" for s in sigs)
            lines.append(f"{p} — {px_s} — {n} ARMED: {setups}")
        else:
            lines.append(f"{p} — {px_s} — Watching")

    title = "FOREX MONITOR — " + (
        f"{sum(len(v) for v in results.values())} SETUP(S) ARMED" if any_armed else "No setups armed"
    )
    body = "\n".join(lines) + f"\n{session_name()}"
    push(title, body.strip(),
         priority="high" if any_armed else "default",
         tags="chart_with_upwards_trend")
    print(f"  [STATUS PUSH] {title}")


def main():
    print("=" * 62)
    print("  FOREX MONITOR — EUR/USD · GBP/USD · AUD/USD")
    print(f"  Started : {now_est().strftime('%Y-%m-%d %I:%M %p EST')}")
    print("  NY Open  (9 AM-12 PM EST) → every 3 min")
    print("  NY Aft.  (12 PM-5 PM EST) → every 5 min")
    print("  Off-hours                 → 30 min sleep")
    print("  Status push to phone      → every 45 min")
    print("  Session flat at 4:55 PM ET daily")
    print("  Press Ctrl+C to stop.")
    print("=" * 62)

    push(
        "FOREX MONITOR — Started",
        f"System online at {now_est().strftime('%I:%M %p EST')}.\n"
        f"Pairs: EUR/USD · GBP/USD · AUD/USD\n"
        f"Active: NY session 9 AM–5 PM EST. Rollover blocked 4:55–6:05 PM.",
        priority="default",
        tags="white_check_mark",
    )

    last_status_push   = 0
    session_flat_fired = ""
    last_advisor_date  = ""   # nightly advisor fires once per day at 10 PM ET

    while True:
        now_ts    = now_est()
        ts        = now_ts.strftime("%I:%M %p EST")
        elapsed   = time.time() - last_status_push
        today_str = now_ts.strftime("%Y-%m-%d")

        # ── 4:55 PM session kill ─────────────────────────────────────────
        if (now_ts.hour == 16 and now_ts.minute >= 55
                and session_flat_fired != today_str
                and now_ts.weekday() < 5):
            print(f"\n[{ts}] SESSION FLAT — closing all open trades.")
            do_session_flat()
            session_flat_fired = today_str

        if in_trading_window():
            interval = get_interval()
            print(f"\n[{ts}] {session_name()} — running analysis...")

            results = run_all_pairs()
            prices  = run_outcome_checks()

            total_armed = sum(len(v) for v in results.values())
            print(f"[{ts}] Done. Armed: {total_armed}. Next in {interval//60} min.")

            if elapsed >= STATUS_PUSH_INTERVAL or last_status_push == 0:
                send_status_push(results, prices)
                last_status_push = time.time()

        else:
            interval = 1800
            print(f"\n[{ts}] OFF-SESSION — sleeping 30 min.")
            # Still resolve open trades using cached prices if possible
            run_outcome_checks()

            if elapsed >= STATUS_PUSH_INTERVAL or last_status_push == 0:
                send_status_push({p: [] for p in ["EUR_USD", "GBP_USD", "AUD_USD"]}, {})
                last_status_push = time.time()

        # Nightly advisor at 10 PM ET — weekdays only, once per day
        _today = now_ts.strftime("%Y-%m-%d")
        if now_ts.weekday() < 5 and now_ts.hour == 22 and last_advisor_date != _today:
            last_advisor_date = _today
            try:
                import threading, forex_learning_advisor
                importlib.reload(forex_learning_advisor)
                threading.Thread(target=forex_learning_advisor.run_advisor, daemon=True).start()
                print(f"  [FOREX ADVISOR] Nightly run started")
            except Exception as adv_err:
                print(f"  [FOREX ADVISOR] {adv_err}")

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        push(
            "FOREX MONITOR — Stopped",
            f"Monitor manually stopped at {now_est().strftime('%I:%M %p EST')}.",
            priority="low",
            tags="stop_sign",
        )
        print(f"\n  Monitor stopped at {now_est().strftime('%I:%M %p EST')}.")
