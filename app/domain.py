"""CareCap domain logic — pure, deterministic functions.

Product rule (from the deep-dive): everything the family sees is a *pure
function of the care graph*. No hidden clock, no randomness — `now` is always
passed in, so the same state produces the same output. That's what makes the
weekly digest trustworthy and the whole thing testable.

State shape (plain JSON-serializable dicts — see `store.py`):

    {
      "family_name": str,
      "care_start": "YYYY-MM-DD",     # onboarding: doses tracked from here on
      "parent_id": str,
      "members":    [{id, name, role, age, location, relationship, conditions?}],
      "medications":[{id, name, dose_label, slots:[HH:MM], prn, started,
                      days_supply, track_from, notes}],
      "history":    [{med_id, date, slot, status, confirmed_by, note}],
      "tasks":      [{id, title, assignee, due_date, status, created_by}],
      "appointments":[{id, title, provider, when, notes, prep}],
      "claims":     [{id, payer, kind, amount, submitted, status, note}],
      "expenses":   [{id, date, category, amount, note}],
      "documents":  [{id, title, category, detail, updated}],
      "digests":    [{id, week_start, week_end, generated_at, subject, payload,
                      sent_to:[member_id], deliveries:[{member_id,channel,status,at}],
                      opens:{member_id: first-open iso}}],
    }
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

GRACE_MINUTES = 120        # a dose is only "missed" after the 2-hour grace window
REFILL_URGENT_DAYS = 7     # alert when run-out is within 7 days
ESCALATION_STREAK = 2      # >= 2 consecutive per-slot misses = escalation
CLAIM_STALE_DAYS = 14      # pending claims older than this get flagged


# ---------------------------------------------------------------- small utils

def d(s: str) -> date:
    return date.fromisoformat(s[:10])


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def index_records(history: list[dict]) -> dict[tuple, dict]:
    """(med_id, date, slot) -> record. The store keeps at most one record per key."""
    return {(r["med_id"], r["date"], r["slot"]): r for r in history}


def slot_due_at(day: date, slot: str) -> datetime:
    h, m = (int(x) for x in slot.split(":"))
    return datetime.combine(day, time(h, m))


def slot_label(slot: str) -> str:
    h, m = (int(x) for x in slot.split(":"))
    part = "morning" if h < 12 else ("afternoon" if h < 17 else "evening")
    return f"{part} ({h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'})"


def schedule_between(med: dict, start: date, end: date) -> list[tuple[date, str]]:
    """(day, slot) pairs the medication was scheduled for, inclusive.

    Clamped to the later of `start` and the medication's own start /
    `track_from` (app onboarding) — we never judge doses from before the
    family joined CareCap.
    """
    s = start
    for key in ("started", "track_from"):
        if key in med:
            s = max(s, date.fromisoformat(med[key]))
    if end < s:
        return []
    out: list[tuple[date, str]] = []
    day = s
    while day <= end:
        for slot in med["slots"]:
            out.append((day, slot))
        day += timedelta(days=1)
    return out


# ------------------------------------------------------- the dose-safety engine

def slot_outcome(med: dict, records: dict, day: date, slot: str, now: datetime) -> str:
    """'taken' | 'skipped' | 'missed' | 'pending' | 'upcoming' for one slot.

    A recorded decision always wins. Otherwise the clock decides, with a grace
    window: unconfirmed within grace = 'pending' (don't nag), past grace =
    'missed'.
    """
    rec = records.get((med["id"], day.isoformat(), slot))
    if rec is not None:
        return rec["status"]
    if med.get("prn"):
        # PRN (as-needed) meds have no daily obligation: unrecorded = "as
        # needed", never "missed". A logged dose still shows as taken.
        return "prn"
    due = slot_due_at(day, slot)
    if now < due:
        return "upcoming"
    if now < due + timedelta(minutes=GRACE_MINUTES):
        return "pending"
    return "missed"


def consecutive_missed(
    med: dict, records: dict, now: datetime, slot: str
) -> tuple[int, list[str]]:
    """Walk backward from today counting consecutive missed doses in THIS slot.

    Per-slot, not per-day: a 9am-confirm / 9pm-miss day is not a missed day.
    A recorded 'taken' or 'skipped' breaks the streak (it's a decision point);
    'pending' does not — the dose hasn't been judged yet, so the running
    streak stands until we know.

    Returns (streak, missed dates most-recent-first).
    """
    s = now.date()
    for key in ("started", "track_from"):
        if key in med:
            s = min(s, date.fromisoformat(med[key]))
    streak = 0
    missed: list[str] = []
    day = now.date()
    while day >= s:
        outcome = slot_outcome(med, records, day, slot, now)
        if outcome in ("taken", "skipped"):
            break
        if outcome == "missed":
            streak += 1
            missed.append(day.isoformat())
        day -= timedelta(days=1)
    return streak, missed


def dose_alerts(med: dict, records: dict, now: datetime) -> list[dict]:
    """Per-slot escalation alerts for one medication.

    streak >= ESCALATION_STREAK  -> 'escalation'  ("missed 2 days in a row")
    streak == 1                  -> 'watch'
    PRN medications are excluded from missed detection entirely.
    """
    if med.get("prn"):
        return []
    out: list[dict] = []
    for slot in med["slots"]:
        streak, missed_dates = consecutive_missed(med, records, now, slot)
        label = slot_label(slot)
        if streak >= ESCALATION_STREAK:
            out.append(
                {
                    "kind": "dose",
                    "med_id": med["id"],
                    "med": med["name"],
                    "slot": slot,
                    "slot_label": label,
                    "level": "escalation",
                    "streak": streak,
                    "missed_dates": missed_dates[:2],
                    "message": f"{med['name']} — {label} dose missed {streak} days in a row",
                }
            )
        elif streak == 1:
            out.append(
                {
                    "kind": "dose",
                    "med_id": med["id"],
                    "med": med["name"],
                    "slot": slot,
                    "slot_label": label,
                    "level": "watch",
                    "streak": 1,
                    "missed_dates": missed_dates[:1],
                    "message": f"{med['name']} — {label} dose missed ({missed_dates[0]})",
                }
            )
    return out


def adherence(med: dict, records: dict, now: datetime, days: int = 7) -> dict:
    """Doses on time over the last `days` days, judged slots only.

    'pending' and 'upcoming' slots (still inside the grace window) are
    excluded from the denominator — we don't penalize a dose that's still
    in time.
    """
    if med.get("prn"):
        return {"med": med["name"], "taken": 0, "closed": 0, "rate": None}
    end = now.date()
    start = end - timedelta(days=days - 1)
    taken = closed = 0
    for day, slot in schedule_between(med, start, end):
        outcome = slot_outcome(med, records, day, slot, now)
        if outcome == "taken":
            taken += 1
            closed += 1
        elif outcome in ("missed", "skipped"):
            closed += 1
    rate = round(100 * taken / closed) if closed else None
    return {"med": med["name"], "taken": taken, "closed": closed, "rate": rate}


# ------------------------------------------------- digest delivery + archive

def digest_summaries(digests: list[dict]) -> list[dict]:
    """Archive rows, newest week first, with the open rate the v0 gate measures."""
    rows = []
    for d in sorted(digests, key=lambda x: x["week_start"], reverse=True):
        sent = len(d["sent_to"])
        opened = len(d["opens"])
        rows.append(
            {
                "id": d["id"],
                "week_start": d["week_start"],
                "week_end": d["week_end"],
                "generated_at": d["generated_at"],
                "sent_to": sent,
                "opened": opened,
                "open_rate": round(100 * opened / sent) if sent else None,
            }
        )
    return rows


# --------------------------------------------------------------- refill watch

def refill_status(med: dict, now: datetime) -> dict:
    """Pharmacy-style days-supply math: run-out = fill start + days supply."""
    run_out = date.fromisoformat(med["started"]) + timedelta(days=med["days_supply"])
    days_left = (run_out - now.date()).days
    return {
        "med_id": med["id"],
        "med": med["name"],
        "days_left": days_left,
        "run_out": run_out.isoformat(),
        "urgent": days_left <= REFILL_URGENT_DAYS,
    }


def refill_alerts(meds: list[dict], now: datetime) -> list[dict]:
    out = []
    for med in meds:
        if med.get("prn"):
            continue  # no scheduled consumption rate -> no run-out urgency
        r = refill_status(med, now)
        if r["urgent"]:
            out.append(
                {
                    "kind": "refill",
                    "med_id": med["id"],
                    "med": med["name"],
                    "level": "urgent",
                    "days_left": r["days_left"],
                    "run_out": r["run_out"],
                    "message": (
                        f"{med['name']} — {r['days_left']} days of supply left "
                        f"(runs out {r['run_out']})"
                    ),
                }
            )
    return out


# ------------------------------------------------------------ family digest

def build_digest(state: dict, now: datetime) -> dict:
    """The weekly family digest — a pure, deterministic function of the care
    graph: adherence, spend, appointments, rule-based priorities, team load.

    Same state + same `now` => byte-identical output (stable ordering, no
    hidden clock). This is the retention feature: it's what out-of-town
    siblings actually read.
    """
    records = index_records(state["history"])
    members = {m["id"]: m for m in state["members"]}
    parent = members[state["parent_id"]]
    first = parent["name"].split()[0]
    today = now.date()

    # 1) alerts: dose escalations/watch + refill urgencies
    alerts: list[dict] = []
    for med in state["medications"]:
        alerts.extend(dose_alerts(med, records, now))
    alerts.extend(refill_alerts(state["medications"], now))

    # 2) adherence, last 7 days
    by_med = [
        adherence(m, records, now) for m in state["medications"] if not m.get("prn")
    ]
    total_taken = sum(a["taken"] for a in by_med)
    total_closed = sum(a["closed"] for a in by_med)
    overall_rate = round(100 * total_taken / total_closed) if total_closed else None

    # 3) money: month-to-date out-of-pocket + pending claims
    month = today.isoformat()[:7]
    mtd: dict[str, float] = {}
    for e in state["expenses"]:
        if e["date"][:7] == month:
            mtd[e["category"]] = round(mtd.get(e["category"], 0) + e["amount"], 2)
    pending = [c for c in state["claims"] if c["status"] == "pending"]
    oldest_pending_days = max(
        ((today - d(c["submitted"])).days for c in pending), default=0
    )

    # 4) appointments, next 14 days
    appts = []
    for a in state["appointments"]:
        when = parse_dt(a["when"])
        delta = (when.date() - today).days
        if 0 <= delta <= 14:
            appts.append(
                {
                    "title": a["title"],
                    "provider": a["provider"],
                    "when": a["when"],
                    "in_days": delta,
                    "label": "today"
                    if delta == 0
                    else ("tomorrow" if delta == 1 else f"in {delta} days"),
                }
            )
    appts.sort(key=lambda x: x["when"])

    # 5) team load
    load = {}
    for m in state["members"]:
        open_tasks = [
            t for t in state["tasks"] if t["assignee"] == m["id"] and t["status"] == "open"
        ]
        load[m["id"]] = {
            "name": m["name"],
            "open": len(open_tasks),
            "overdue": sum(1 for t in open_tasks if d(t["due_date"]) < today),
        }

    # 6) priorities — rule-based, ranked, stable order
    priorities: list[dict] = []

    def add(rule: str, text: str) -> None:
        priorities.append({"rule": rule, "text": text})

    for a in alerts:
        if a["kind"] == "dose" and a["level"] == "escalation":
            dates = ", ".join(x[-5:] for x in a["missed_dates"])
            add(
                "dose-escalation",
                f"Confirm {a['med']} {a['slot_label']} with {first} — missed "
                f"{a['streak']} days in a row ({dates})",
            )
    for a in alerts:
        if a["kind"] == "refill":
            add(
                "refill-urgent",
                f"Refill {a['med']} — only {a['days_left']} days left "
                f"(runs out {a['run_out']})",
            )
    for c in sorted(pending, key=lambda c: (d(c["submitted"]), c["id"])):
        age = (today - d(c["submitted"])).days
        if age >= CLAIM_STALE_DAYS:
            add(
                "claim-stale",
                f"Follow up with {c['payer']} — {c['kind']} claim pending "
                f"{age} days (${c['amount']:.2f})",
            )
    for t in [
        t
        for t in state["tasks"]
        if t["status"] == "open" and d(t["due_date"]) < today
    ]:
        who = members.get(t["assignee"], {}).get("name", t["assignee"])
        add("task-overdue", f"{who}: '{t['title']}' was due {t['due_date']}")
    for a in alerts:
        if a["kind"] == "dose" and a["level"] == "watch":
            add(
                "dose-watch",
                f"Check in on {a['med']} {a['slot_label']} — missed once "
                f"({a['missed_dates'][0]})",
            )

    order = {
        "dose-escalation": 0,
        "refill-urgent": 1,
        "claim-stale": 2,
        "task-overdue": 3,
        "dose-watch": 4,
    }
    priorities.sort(key=lambda p: order[p["rule"]])  # stable: ties keep insertion order
    for i, p in enumerate(priorities, 1):
        p["rank"] = i

    if total_closed == 0:
        headline = (
            f"First week with {first}'s care graph — no doses recorded in the "
            "past 7 days yet. Log the first dose and tracking starts."
        )
    else:
        headline = (
            f"{first} was at {overall_rate}% adherence in the past 7 days "
            f"({total_taken} of {total_closed} doses on time)."
        )
    if priorities:
        n = len(priorities)
        headline += f" {n} thing{'s' if n != 1 else ''} need{'s' if n == 1 else ''} attention."

    return {
        "family": state["family_name"],
        "week_start": (today - timedelta(days=6)).isoformat(),
        "week_end": today.isoformat(),
        "headline": headline,
        "alerts": alerts,
        "adherence": {
            "overall_rate": overall_rate,
            "taken": total_taken,
            "closed": total_closed,
            "by_medication": by_med,
        },
        "money": {
            "mtd_total": round(sum(mtd.values()), 2),
            "by_category": dict(sorted(mtd.items(), key=lambda kv: (-kv[1], kv[0]))),
            "pending_claims": {
                "count": len(pending),
                "total": round(sum(c["amount"] for c in pending), 2),
                "oldest_days": oldest_pending_days,
            },
        },
        "appointments": appts,
        "team_load": load,
        "priorities": priorities,
    }
