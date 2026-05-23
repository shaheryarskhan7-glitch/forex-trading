"""
Forex Learning Advisor
======================
Analyzes forex signal logs (EUR/USD, GBP/USD, AUD/USD) and forex_pattern_db.json
to generate tiered findings — same tier system as the gold advisor:

  OBSERVATION   — notable stat, not yet enough data to act (3-4 trades)
  RECOMMENDATION — clear pattern, enough evidence (5-9 trades)
  PROPOSAL      — specific change ready for your consent (10+ trades)

Proposals stored in forex_advisor_output.json.
Push fires only when NEW significant findings appear — not every cycle.
Runs nightly at 10 PM ET (called from forex_monitor.py).
"""
import csv, json, os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

EST  = timezone(timedelta(hours=-4))
_DIR = os.path.dirname(os.path.abspath(__file__))

SIGNAL_LOGS = {
    "EUR_USD": os.path.join(_DIR, "forex_signal_log_EURUSD.csv"),
    "GBP_USD": os.path.join(_DIR, "forex_signal_log_GBPUSD.csv"),
    "AUD_USD": os.path.join(_DIR, "forex_signal_log_AUDUSD.csv"),
}

ADVISOR_F  = os.path.join(_DIR, "forex_advisor_output.json")
MANIFEST_F = os.path.join(_DIR, "forex_strategy_manifest.json")

MIN_OBSERVE   = 3
MIN_RECOMMEND = 5
MIN_PROPOSE   = 10

WR_DANGER = 0.42
WR_STRONG = 0.68


# ─── Manifest ─────────────────────────────────────────────────────────────────

def _load_manifest() -> dict:
    default = {
        "EUR_USD": {"active_setups": ["S1","S2","S3"], "score_gate_min": 5},
        "GBP_USD": {"active_setups": ["S1","S2","S3"], "score_gate_min": 5},
        "AUD_USD": {"active_setups": ["S1","S3"],      "score_gate_min": 5},
    }
    if not os.path.exists(MANIFEST_F):
        return default
    try:
        with open(MANIFEST_F, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ─── Advisor state ────────────────────────────────────────────────────────────

def _load_advisor() -> dict:
    if os.path.exists(ADVISOR_F):
        try:
            return json.loads(open(ADVISOR_F, encoding="utf-8").read())
        except Exception:
            pass
    return {"last_run": None, "findings": [], "pending_proposals": [], "pushed_fingerprints": []}


def _save_advisor(data: dict):
    with open(ADVISOR_F, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_signals(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f) if r.get("outcome")]
    except Exception:
        return []


def _wr(wins, total) -> float:
    return wins / total if total > 0 else 0.5


def _tier(total: int) -> str | None:
    if total >= MIN_PROPOSE:   return "PROPOSAL"
    if total >= MIN_RECOMMEND: return "RECOMMENDATION"
    if total >= MIN_OBSERVE:   return "OBSERVATION"
    return None


def _bucket(rows, key_fn) -> dict:
    out = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0})
    for r in rows:
        k = key_fn(r)
        if not k:
            continue
        out[k]["total"] += 1
        if r.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT"):
            out[k]["wins"] += 1
        else:
            out[k]["losses"] += 1
    return out


def _setup_prefix(r: dict) -> str:
    s = r.get("setup", "")
    return s.split("-")[0].upper() if s else None


def _day_of_week(r: dict) -> str:
    try:
        dt = datetime.fromisoformat((r.get("timestamp", "") or "")[:10])
        return dt.strftime("%A")
    except Exception:
        return None


def _rsi_zone(val) -> str:
    try:
        v = float(val)
        if v < 30: return "oversold"
        if v < 45: return "bearish"
        if v < 55: return "neutral"
        if v < 70: return "bullish"
        return "overbought"
    except Exception:
        return None


# ─── Per-pair analysis ────────────────────────────────────────────────────────

def _analyze_pair(pair: str, rows: list, manifest: dict) -> list:
    findings = []
    if not rows:
        return findings

    m              = manifest.get(pair, {})
    active_setups  = set(m.get("active_setups", []))
    score_gate_min = m.get("score_gate_min", 5)
    pair_disp      = pair.replace("_", "/")

    overall_wins  = sum(1 for r in rows if r.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT"))
    overall_total = len(rows)
    overall_wr    = _wr(overall_wins, overall_total)

    # ── 1. Overall health ────────────────────────────────────────────────────
    if overall_total >= MIN_RECOMMEND:
        if overall_wr < 0.45:
            findings.append({
                "pair": pair, "tier": "RECOMMENDATION", "category": "overall",
                "title": f"🔴 {pair_disp}: {overall_wr*100:.0f}% WR across {overall_total} trades",
                "evidence": f"{overall_wins}W / {overall_total-overall_wins}L",
                "recommendation": (
                    f"{pair_disp} is below break-even ({overall_wr*100:.0f}% WR). "
                    f"Review worst setup and direction combination first."
                ),
                "fingerprint": f"{pair}:overall:low:{overall_total}",
            })
        elif overall_wr > WR_STRONG:
            findings.append({
                "pair": pair, "tier": "OBSERVATION", "category": "overall",
                "title": f"✅ {pair_disp}: {overall_wr*100:.0f}% WR — performing well",
                "evidence": f"{overall_wins}W / {overall_total-overall_wins}L / {overall_total} trades",
                "recommendation": "No changes needed — strategy outperforming threshold.",
                "fingerprint": f"{pair}:overall:strong:{overall_total}",
            })

    # ── 2. Setup breakdown ───────────────────────────────────────────────────
    setups = _bucket(rows, _setup_prefix)
    for setup, d in setups.items():
        if not setup or (active_setups and setup not in active_setups):
            continue
        t = _tier(d["total"])
        if not t:
            continue
        wr = _wr(d["wins"], d["total"])
        if wr < WR_DANGER:
            emoji = "🔴" if t == "PROPOSAL" else "🟡"
            findings.append({
                "pair": pair, "tier": t, "category": "setup",
                "title": f"{emoji} {pair_disp} {setup}: {wr*100:.0f}% WR ({d['wins']}W/{d['losses']}L) — underperforming",
                "evidence": f"{d['wins']}W / {d['losses']}L / {d['total']} trades",
                "recommendation": (
                    f"{setup} on {pair_disp} has {wr*100:.0f}% WR across {d['total']} trades. "
                    f"Consider raising score gate or tightening entry conditions for {setup}."
                ),
                "fingerprint": f"{pair}:setup:{setup}:low:{d['total']}",
            })
        elif wr > WR_STRONG and d["total"] >= MIN_RECOMMEND:
            findings.append({
                "pair": pair, "tier": "OBSERVATION", "category": "setup",
                "title": f"✅ {pair_disp} {setup}: {wr*100:.0f}% WR — reliable edge",
                "evidence": f"{d['wins']}W / {d['losses']}L / {d['total']} trades",
                "recommendation": f"{setup} on {pair_disp} is a strong setup. Prioritise when armed.",
                "fingerprint": f"{pair}:setup:{setup}:strong:{d['total']}",
            })

    # ── 3. Direction bias ────────────────────────────────────────────────────
    directions = _bucket(rows, lambda r: r.get("direction", "").upper())
    for direction, d in directions.items():
        if not direction or d["total"] < MIN_OBSERVE:
            continue
        wr = _wr(d["wins"], d["total"])
        if wr < WR_DANGER and d["total"] >= MIN_OBSERVE:
            t = _tier(d["total"])
            findings.append({
                "pair": pair, "tier": t or "OBSERVATION", "category": "direction",
                "title": f"🟡 {pair_disp} {direction}: {wr*100:.0f}% WR ({d['wins']}W/{d['losses']}L)",
                "evidence": f"{d['total']} {direction} trades",
                "recommendation": (
                    f"{direction} trades on {pair_disp} win only {wr*100:.0f}%. "
                    f"Require extra confluence filter (trend alignment) for {direction} entries."
                ),
                "fingerprint": f"{pair}:direction:{direction}:low:{d['total']}",
            })

    # ── 4. Day of week ───────────────────────────────────────────────────────
    days = _bucket(rows, _day_of_week)
    for day, d in days.items():
        if not day or d["total"] < MIN_RECOMMEND:
            continue
        wr = _wr(d["wins"], d["total"])
        if wr < WR_DANGER:
            findings.append({
                "pair": pair, "tier": _tier(d["total"]) or "OBSERVATION", "category": "day_of_week",
                "title": f"🟡 {pair_disp} on {day}s: {wr*100:.0f}% WR ({d['wins']}W/{d['losses']}L)",
                "evidence": f"{d['total']} trades on {day}s",
                "recommendation": (
                    f"{pair_disp} has poor WR on {day}s ({wr*100:.0f}%). "
                    f"Consider skipping {pair_disp} on {day}s or requiring score of 7/7."
                ),
                "fingerprint": f"{pair}:day:{day}:{d['total']}",
            })

    # ── 5. Consecutive loss streak ───────────────────────────────────────────
    streak = 0
    max_streak = 0
    streak_counts = defaultdict(int)
    for r in rows:
        if r.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT"):
            streak = 0
        else:
            streak += 1
            max_streak = max(max_streak, streak)
            if streak >= 3:
                streak_counts[streak] += 1

    if max_streak >= 4 and overall_total >= MIN_RECOMMEND:
        three_plus = sum(v for k, v in streak_counts.items() if k >= 3)
        findings.append({
            "pair": pair, "tier": "RECOMMENDATION", "category": "drawdown",
            "title": f"🟡 {pair_disp}: max losing streak of {max_streak} — {three_plus} streaks of 3+",
            "evidence": f"Worst streak: {max_streak} consecutive losses",
            "recommendation": (
                f"{pair_disp} hit {three_plus} streak(s) of 3+ losses. "
                f"Consider a 3-loss daily pause rule — stop {pair_disp} after 3 losses in one session."
            ),
            "fingerprint": f"{pair}:streak:{max_streak}:{overall_total}",
        })

    # ── 6. Score gate audit ──────────────────────────────────────────────────
    findings.extend(_score_gate_audit(pair, rows, score_gate_min))

    # ── 7. RSI zone breakdown ────────────────────────────────────────────────
    rsi_buckets = _bucket(rows, lambda r: _rsi_zone(r.get("rsi14", "")))
    for zone, d in rsi_buckets.items():
        if not zone or d["total"] < MIN_OBSERVE:
            continue
        wr = _wr(d["wins"], d["total"])
        if wr < WR_DANGER:
            findings.append({
                "pair": pair, "tier": _tier(d["total"]) or "OBSERVATION", "category": "rsi",
                "title": f"🟡 {pair_disp} RSI {zone}: {wr*100:.0f}% WR ({d['wins']}W/{d['losses']}L)",
                "evidence": f"{d['total']} trades in RSI {zone} zone",
                "recommendation": (
                    f"Entries in RSI {zone} zone on {pair_disp} win only {wr*100:.0f}%. "
                    f"Avoid {pair_disp} entries when RSI is in the {zone} zone."
                ),
                "fingerprint": f"{pair}:rsi:{zone}:low:{d['total']}",
            })
        elif wr > WR_STRONG and d["total"] >= MIN_RECOMMEND:
            findings.append({
                "pair": pair, "tier": "OBSERVATION", "category": "rsi",
                "title": f"✅ {pair_disp} RSI {zone}: {wr*100:.0f}% WR — preferred entry zone",
                "evidence": f"{d['total']} trades in RSI {zone} zone",
                "recommendation": f"RSI {zone} zone on {pair_disp} is highly reliable. Prioritise.",
                "fingerprint": f"{pair}:rsi:{zone}:strong:{d['total']}",
            })

    return findings


def _score_gate_audit(pair: str, rows: list, score_gate_min: int) -> list:
    findings = []
    if len(rows) < MIN_RECOMMEND:
        return findings

    pair_disp = pair.replace("_", "/")
    buckets = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in rows:
        try:
            sc = int(float(r.get("score", 0)))
        except (ValueError, TypeError):
            continue
        if sc <= 0:
            continue
        buckets[sc]["total"] += 1
        if r.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT"):
            buckets[sc]["wins"] += 1

    if not buckets:
        return findings

    scores_present = sorted(buckets.keys())
    if len(scores_present) < 2:
        return findings

    breakdown_lines = []
    for sc in scores_present:
        b = buckets[sc]
        wr_pct = round(_wr(b["wins"], b["total"]) * 100)
        breakdown_lines.append(f"score {sc}: {wr_pct}% ({b['wins']}W/{b['total']-b['wins']}L)")
    breakdown = "  |  ".join(breakdown_lines)

    # Pass 1: individual score values
    for sc in scores_present:
        if sc < score_gate_min:
            continue
        b = buckets[sc]
        if b["total"] < MIN_OBSERVE:
            continue
        sc_wr = _wr(b["wins"], b["total"])
        if sc_wr < WR_DANGER:
            tier = "PROPOSAL" if b["total"] >= MIN_PROPOSE else "RECOMMENDATION"
            findings.append({
                "pair": pair, "tier": tier, "category": "score_gate",
                "title": (f"{'🔴' if tier=='PROPOSAL' else '🟡'} {pair_disp} score {sc}/7: "
                          f"{sc_wr*100:.0f}% WR ({b['wins']}W/{b['total']-b['wins']}L) — below break-even"),
                "evidence": breakdown,
                "recommendation": (
                    f"Score {sc}/7 on {pair_disp} has {sc_wr*100:.0f}% WR across {b['total']} trades. "
                    f"Propose: raise minimum score gate above {sc} for {pair_disp}."
                ),
                "fingerprint": f"{pair}:score_gate:sc{sc}:low:{b['total']}",
            })

    # Pass 2: band comparison
    split = scores_present[len(scores_present) // 2]
    if split <= score_gate_min:
        return findings

    low_w = low_t = high_w = high_t = 0
    for sc in scores_present:
        b = buckets[sc]
        if sc < split:
            low_w += b["wins"]; low_t += b["total"]
        else:
            high_w += b["wins"]; high_t += b["total"]

    if low_t < MIN_OBSERVE or high_t < MIN_OBSERVE:
        return findings

    low_wr  = _wr(low_w, low_t)
    high_wr = _wr(high_w, high_t)
    spread  = high_wr - low_wr

    if spread >= 0.15 and low_wr < WR_DANGER:
        tier = "PROPOSAL" if (low_t + high_t) >= MIN_PROPOSE else "RECOMMENDATION"
        findings.append({
            "pair": pair, "tier": tier, "category": "score_gate",
            "title": (f"{'🔴' if tier=='PROPOSAL' else '🟡'} {pair_disp} score gate: "
                      f"scores below {split} win only {low_wr*100:.0f}%"),
            "evidence": breakdown,
            "recommendation": (
                f"Score is predictive on {pair_disp}. Below-{split} trades win {low_wr*100:.0f}% "
                f"vs {high_wr*100:.0f}% for score {split}+. "
                f"Propose: raise score gate to {split} for {pair_disp}."
            ),
            "fingerprint": f"{pair}:score_gate:band:{split}:{low_t+high_t}",
        })

    return findings


# ─── Proposal management ──────────────────────────────────────────────────────

def _generate_proposals(findings: list, existing_proposals: list) -> list:
    existing_fps = {p.get("source_fingerprint") for p in existing_proposals}
    new_proposals = list(existing_proposals)
    for i, f in enumerate(findings):
        if f["tier"] != "PROPOSAL":
            continue
        fp = f["fingerprint"]
        if fp in existing_fps:
            continue
        prop_id = f"forex_prop_{datetime.now(EST).strftime('%Y%m%d')}_{i:02d}"
        new_proposals.append({
            "id":               prop_id,
            "created":          datetime.now(EST).isoformat(),
            "status":           "pending",
            "pair":             f["pair"],
            "title":            f["title"],
            "evidence":         f["evidence"],
            "recommendation":   f["recommendation"],
            "source_fingerprint": fp,
            "approved_at":      None,
            "rejected_at":      None,
        })
        existing_fps.add(fp)
    return new_proposals


# ─── Main entry point ─────────────────────────────────────────────────────────

def run_advisor() -> dict:
    """
    Analyze all forex signal logs, generate findings, push notification if new.
    Called nightly at 10 PM ET from forex_monitor.py.
    """
    try:
        from notifier import push
        _can_push = True
    except ImportError:
        _can_push = False

    data        = _load_advisor()
    manifest    = _load_manifest()
    pushed_fps  = set(data.get("pushed_fingerprints", []))
    all_findings = []
    pair_summaries = {}

    for pair, path in SIGNAL_LOGS.items():
        rows = _load_signals(path)
        if rows:
            findings = _analyze_pair(pair, rows, manifest)
            all_findings.extend(findings)
            wins = sum(1 for r in rows if r.get("outcome", "").upper() in ("TP1_HIT", "TP2_HIT"))
            pair_summaries[pair] = {
                "total": len(rows), "wins": wins,
                "wr": round(_wr(wins, len(rows)) * 100, 1),
            }

    new_proposals = _generate_proposals(all_findings, data.get("pending_proposals", []))

    new_significant = [
        f for f in all_findings
        if f["fingerprint"] not in pushed_fps
        and f["tier"] in ("PROPOSAL", "RECOMMENDATION")
    ]

    if new_significant and _can_push:
        proposals  = [f for f in new_significant if f["tier"] == "PROPOSAL"]
        recs       = [f for f in new_significant if f["tier"] == "RECOMMENDATION"]
        pending_ct = len([p for p in new_proposals if p["status"] == "pending"])

        if proposals:
            title = f"FOREX ADVISOR — {len(proposals)} proposal(s) ready"
        elif recs:
            title = f"FOREX ADVISOR — {len(recs)} new recommendation(s)"
        else:
            title = "FOREX ADVISOR — new insight"

        lines = []
        for f in (proposals + recs)[:3]:
            lines.append(f["title"])
            lines.append(f"  → {f['recommendation'][:120]}")
        if pending_ct:
            lines.append(f"\n{pending_ct} proposal(s) pending review.")
            lines.append("Tell Claude Code 'show forex advisor proposals' to review.")

        push(title, "\n".join(lines), priority="high", tags="brain,chart_with_upwards_trend")
        pushed_fps.update(f["fingerprint"] for f in new_significant)
        print(f"  [FOREX ADVISOR] Push sent — {len(new_significant)} new finding(s)")
    else:
        print(f"  [FOREX ADVISOR] No new significant findings this cycle")

    data.update({
        "last_run":            datetime.now(EST).isoformat(),
        "findings":            all_findings,
        "pending_proposals":   new_proposals,
        "pushed_fingerprints": sorted(pushed_fps),
        "pair_summaries":      pair_summaries,
    })
    _save_advisor(data)

    pending_ct = len([p for p in new_proposals if p["status"] == "pending"])
    return {"findings": len(all_findings), "proposals": pending_ct, "new_pushed": len(new_significant)}


def show_proposals():
    data      = _load_advisor()
    proposals = [p for p in data.get("pending_proposals", []) if p["status"] == "pending"]
    if not proposals:
        print("No pending forex proposals.")
        return
    print(f"\n{'='*60}")
    print(f"  FOREX ADVISOR — PENDING PROPOSALS ({len(proposals)})")
    print(f"{'='*60}")
    for i, p in enumerate(proposals, 1):
        print(f"\n  [{i}] ID: {p['id']}")
        print(f"  Pair    : {p['pair']}")
        print(f"  Created : {p['created'][:16]}")
        print(f"  Finding : {p['title']}")
        print(f"  Evidence: {p['evidence']}")
        print(f"  Action  : {p['recommendation']}")
        print(f"  Status  : {p['status'].upper()}")
    print(f"\n{'='*60}\n")


def show_findings():
    data     = _load_advisor()
    findings = data.get("findings", [])
    if not findings:
        print("No forex findings yet.")
        return
    by_tier = {"PROPOSAL": [], "RECOMMENDATION": [], "OBSERVATION": []}
    for f in findings:
        by_tier.get(f["tier"], []).append(f)
    print(f"\n{'='*60}")
    print(f"  FOREX ADVISOR — ALL FINDINGS")
    print(f"  Last run: {data.get('last_run','never')[:16]}")
    print(f"{'='*60}")
    for tier in ("PROPOSAL", "RECOMMENDATION", "OBSERVATION"):
        items = by_tier[tier]
        if not items:
            continue
        print(f"\n  --- {tier}S ({len(items)}) ---")
        for f in items:
            print(f"  [{f['pair']}] {f['title']}")
            print(f"          {f['evidence']}")
            print(f"          → {f['recommendation'][:100]}")
    print()


if __name__ == "__main__":
    import sys, os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "proposals": show_proposals()
        elif cmd == "findings": show_findings()
        elif cmd == "run":
            result = run_advisor()
            print(f"Done: {result}")
    else:
        result = run_advisor()
        show_findings()
