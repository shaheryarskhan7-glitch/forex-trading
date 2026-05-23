"""
Push notifications for Forex Monitor — ntfy.sh.
Topic: forex-signals-sk7  (subscribe in ntfy app)
"""
import requests

try:
    import winsound
    _WINSOUND = True
except ImportError:
    _WINSOUND = False

from config import NTFY_TOPIC


def _ascii(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii")


def push(title: str, body: str, priority: str = "high", tags: str = "rotating_light"):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={
                "Title":    _ascii(title),
                "Priority": priority,
                "Tags":     tags,
            },
            timeout=6,
        )
        print(f"  [PUSH] {title}")
    except Exception as e:
        print(f"  [PUSH] Failed: {e}")


def beep():
    if not _WINSOUND:
        return
    try:
        for freq, dur in [(1000, 350), (800, 200), (1000, 350), (1200, 500)]:
            winsound.Beep(freq, dur)
    except Exception:
        pass


def alert_forex(pair: str, setup: str, direction: str,
                entry: float, sl: float, tp1: float, tp2: float,
                score: int, reason: str = ""):
    """Fire urgent phone alert when a forex setup arms."""
    pip_factor = 100 if "JPY" in pair else 10000
    sl_pips  = round(abs(entry - sl)  * pip_factor, 1)
    tp1_pips = round(abs(tp1 - entry) * pip_factor, 1)
    tp2_pips = round(abs(tp2 - entry) * pip_factor, 1)
    pair_disp = pair.replace("_", "/")
    title = f"FOREX {setup} {direction} — {pair_disp}"
    body  = (
        f"Entry: {entry:.5f}  |  SL: {sl:.5f} ({sl_pips} pips)\n"
        f"TP1: {tp1:.5f} ({tp1_pips} pips)  ← close half, SL to BE\n"
        f"TP2: {tp2:.5f} ({tp2_pips} pips)  ← let rest run\n"
        f"Score: {score}/7\n"
        f"{reason}".strip()
    )
    push(title, body, priority="urgent", tags="rotating_light,chart_with_upwards_trend")
    beep()


def alert_info(title: str, body: str):
    push(title, body, priority="default", tags="chart_with_upwards_trend")


if __name__ == "__main__":
    print(f"Sending test push to topic '{NTFY_TOPIC}'...")
    push(
        title="FOREX MONITOR — Push Test",
        body="If you see this on your phone, forex notifications are working!\nSubscribe to 'forex-signals-sk7' in the ntfy app.",
        priority="default",
        tags="white_check_mark",
    )
    print("Done.")
