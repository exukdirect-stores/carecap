"""Seed family — the demo family, anchored to *today*.

Everything is date-relative so the demo always shows a live situation:
Gabapentin's evening miss streak, Metformin's imminent run-out, the stale
OptumRx claim, Miguel's overdue task. Deterministic for a given `now`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

FAMILY = "Reyes"
PARENT_ID = "rosa"


def build_empty_family(
    family_name: str, captain_name: str, parent_name: str, now: datetime
) -> dict:
    """Concierge onboarding: a brand-new family — captain + parent, nothing else.

    The captain fills in medications, tasks, claims, and the vault as they
    work through the first week with us.
    """
    today = now.date().isoformat()
    return {
        "family_name": family_name,
        "care_start": today,
        "parent_id": "p1",
        "members": [
            {
                "id": "p1",
                "name": parent_name,
                "role": "parent",
                "age": None,
                "location": "",
                "relationship": "parent",
                "conditions": "",
            },
            {
                "id": "c1",
                "name": captain_name,
                "role": "captain",
                "age": None,
                "location": "",
                "relationship": "captain",
            },
        ],
        "medications": [],
        "history": [],
        "tasks": [],
        "appointments": [],
        "claims": [],
        "expenses": [],
        "documents": [],
        "digests": [],
    }


def build_seed(now: datetime) -> dict:
    today = now.date()

    def D(n: int) -> str:
        """ISO date offset: D(1) = yesterday, D(-2) = 2 days from now."""
        return (today - timedelta(days=n)).isoformat()

    def at(n: int, hh: int, mm: int) -> str:
        """ISO datetime offset (n days ago)."""
        return f"{(today - timedelta(days=n)).isoformat()}T{hh:02d}:{mm:02d}:00"

    def atf(n: int, hh: int, mm: int) -> str:
        """ISO datetime ahead (n days from now)."""
        return f"{(today + timedelta(days=n)).isoformat()}T{hh:02d}:{mm:02d}:00"

    members = [
        {
            "id": PARENT_ID,
            "name": "Rosa Reyes",
            "role": "parent",
            "age": 84,
            "location": "Austin, TX",
            "relationship": "mother",
            "conditions": "Hypertension · Type 2 diabetes · Osteoarthritis (knees)",
        },
        {
            "id": "patricia",
            "name": "Patricia Reyes",
            "role": "captain",
            "age": 52,
            "location": "Austin, TX",
            "relationship": "daughter (primary caregiver)",
        },
        {
            "id": "miguel",
            "name": "Miguel Reyes",
            "role": "sibling",
            "age": 49,
            "location": "San Diego, CA",
            "relationship": "son",
        },
        {
            "id": "sofia",
            "name": "Sofía Reyes-Liu",
            "role": "sibling",
            "age": 44,
            "location": "Seattle, WA",
            "relationship": "daughter",
        },
    ]

    # `started` = pharmacy fill date; `track_from` = when tracking began for
    # this med (no later than app onboarding, D(13)).
    medications = [
        {
            "id": "lisinopril",
            "name": "Lisinopril",
            "dose_label": "10 mg · 1 pill",
            "slots": ["09:00"],
            "prn": False,
            "started": D(20),
            "days_supply": 30,
            "track_from": D(13),
            "notes": "Blood pressure. Take with breakfast.",
        },
        {
            "id": "metformin",
            "name": "Metformin",
            "dose_label": "1000 mg · 2 pills",
            "slots": ["09:00"],
            "prn": False,
            "started": D(7),
            "days_supply": 11,  # -> 4 days of supply left: refill urgent
            "track_from": D(7),
            "notes": "Type 2 diabetes. Must be taken with food.",
        },
        {
            "id": "gabapentin",
            "name": "Gabapentin",
            "dose_label": "300 mg · 1 pill",
            "slots": ["09:00", "21:00"],
            "prn": False,
            "started": D(15),
            "days_supply": 30,
            "track_from": D(13),
            "notes": "Nerve pain. The evening dose is the one that slips.",
        },
        {
            "id": "calcium",
            "name": "Calcium + D3",
            "dose_label": "600 mg · 1 pill",
            "slots": ["13:00"],
            "prn": False,
            "started": D(12),
            "days_supply": 30,
            "track_from": D(12),
            "notes": "Bone health (osteoarthritis prevention).",
        },
        {
            "id": "naproxen",
            "name": "Naproxen",
            "dose_label": "250 mg · 1–2 pills",
            "slots": ["18:00"],
            "prn": True,  # PRN: excluded from missed detection + refill urgency
            "started": D(9),
            "days_supply": 21,
            "track_from": D(9),
            "notes": "PRN — knee pain only, with food. Max 2 pills.",
        },
    ]

    # ---- 14 days of dose history (the escalation story lives here) ----
    history: list[dict] = []

    def rec(med_id: str, n: int, slot: str, status: str = "taken", note: str = "") -> None:
        history.append(
            {
                "med_id": med_id,
                "date": D(n),
                "slot": slot,
                "status": status,
                "confirmed_by": "patricia",
                "note": note,
            }
        )

    # Intentionally unrecorded slots (=> missed once past grace):
    # Gabapentin evening, yesterday and the day before -> 2-day streak.
    # Calcium, 4 days ago -> a one-off (no streak).
    missed = {
        ("gabapentin", 1, "21:00"),
        ("gabapentin", 2, "21:00"),
        ("calcium", 4, "13:00"),
    }

    for med in medications:
        if med["prn"]:
            continue
        track_from = date.fromisoformat(med["track_from"])
        for n in range(13, 0, -1):  # 13 days ago .. yesterday
            day = today - timedelta(days=n)
            if day < track_from:
                continue
            for slot in med["slots"]:
                if (med["id"], n, slot) in missed:
                    continue
                if med["id"] == "lisinopril" and n == 2:
                    rec(
                        med["id"],
                        n,
                        slot,
                        "skipped",
                        "Held one dose — felt faint, per Dr. Iman's advice",
                    )
                    continue
                rec(med["id"], n, slot)

    # Today: everything already past grace is confirmed taken — except
    # Gabapentin's evening dose, which stays live for the demo.
    for med in medications:
        if med["prn"]:
            continue
        for slot in med["slots"]:
            if med["id"] == "gabapentin" and slot == "21:00":
                continue
            hh, mm = (int(x) for x in slot.split(":"))
            due = datetime.combine(today, datetime.min.time().replace(hour=hh, minute=mm))
            if now >= due + timedelta(minutes=120):
                rec(med["id"], 0, slot)

    appointments = [
        {
            "id": "a1",
            "title": "Cardiology follow-up",
            "provider": "Dr. A. Alvarez — St. David's",
            "when": atf(3, 10, 30),
            "notes": "BP 138/84 at last visit; bring all pill bottles.",
            "prep": "",
        },
        {
            "id": "a2",
            "title": "Physical therapy (knees)",
            "provider": "Barton Springs PT",
            "when": atf(6, 14, 0),
            "notes": "Gait + quad strengthening, week 4 of 6.",
            "prep": "Bring the walker",
        },
        {
            "id": "a3",
            "title": "Endocrinology",
            "provider": "Dr. N. Okafor",
            "when": atf(12, 9, 0),
            "notes": "A1c review — last 7.2%, goal <7.0%.",
            "prep": "Fasting glucose draw; take metformin after",
        },
        {
            "id": "a4",
            "title": "PCP visit",
            "provider": "Dr. S. Iman — Austin Family Med",
            "when": at(2, 11, 15),
            "notes": "Held one lisinopril dose after dizziness; recheck in 2 weeks.",
            "prep": "",
        },
    ]

    claims = [
        {
            "id": "c1",
            "payer": "OptumRx (Part D)",
            "kind": "rx",
            "amount": 186.40,
            "submitted": D(16),  # stale: > 14 days pending -> digest priority
            "status": "pending",
            "note": "Q3 refills — worth a phone call",
        },
        {
            "id": "c2",
            "payer": "Medicare (B)",
            "kind": "dme",
            "amount": 412.00,
            "submitted": D(30),
            "status": "approved",
            "note": "Walker + brace, billed direct by the DME vendor",
        },
        {
            "id": "c3",
            "payer": "Optum Health (Medigap)",
            "kind": "homecare",
            "amount": 520.00,
            "submitted": D(5),
            "status": "pending",
            "note": "Home aide visits, 2 visits x $260",
        },
    ]

    expenses = [
        {
            "id": "e1",
            "date": D(0),
            "category": "Pharmacy",
            "amount": 22.00,
            "note": "Copays — Metformin + Lisinopril (CVS)",
        },
        {
            "id": "e2",
            "date": D(1),
            "category": "Transport",
            "amount": 38.50,
            "note": "Gas — pharmacy run + PT drop-off",
        },
        {
            "id": "e3",
            "date": D(5),
            "category": "Groceries",
            "amount": 64.10,
            "note": "Low-sodium pantry + soft foods",
        },
        {
            "id": "e4",
            "date": D(8),
            "category": "Home care",
            "amount": 250.00,
            "note": "Home aide — 2 visits",
        },
        {
            "id": "e5",
            "date": D(11),
            "category": "Supplies",
            "amount": 41.25,
            "note": "Compression socks, incontinence supplies",
        },
    ]

    tasks = [
        {
            "id": "t1",
            "title": "Refill Metformin (11-day fill)",
            "assignee": "patricia",
            "due_date": D(-2),
            "status": "open",
            "created_by": "patricia",
        },
        {
            "id": "t2",
            "title": "Confirm POA filing with the bank",
            "assignee": "miguel",
            "due_date": D(1),  # overdue
            "status": "open",
            "created_by": "patricia",
        },
        {
            "id": "t3",
            "title": "Order bathroom grab bars + raised toilet seat",
            "assignee": "sofia",
            "due_date": D(-5),
            "status": "open",
            "created_by": "patricia",
        },
        {
            "id": "t4",
            "title": "Pick up Gabapentin from CVS",
            "assignee": "patricia",
            "due_date": D(0),
            "status": "done",
            "created_by": "patricia",
        },
    ]

    documents = [
        {
            "id": "d1",
            "title": "Power of Attorney (2019, notarized)",
            "category": "legal",
            "detail": (
                "Medical + financial POA. Effective. Original in the fire-safe box; "
                "copies on file at Chase and Bank of America."
            ),
            "updated": D(60),
        },
        {
            "id": "d2",
            "title": "Medicare + OptumRx cards",
            "category": "insurance",
            "detail": (
                "Medicare B + Part D (OptumRx). Member ID on file with the pharmacy. "
                "Premium paid through the bank bill-pay."
            ),
            "updated": D(14),
        },
        {
            "id": "d3",
            "title": "MOLST (signed)",
            "category": "medical",
            "detail": (
                "Full treatment. Signed by Rosa + Dr. Alvarez, updated last spring. "
                "Copy in the kitchen fridge + with EMS."
            ),
            "updated": D(90),
        },
        {
            "id": "d4",
            "title": "Doctor list",
            "category": "medical",
            "detail": (
                "PCP: Dr. S. Iman (Austin Family Med) · Cardiology: Dr. A. Alvarez · "
                "Endo: Dr. N. Okafor · PT: Barton Springs PT."
            ),
            "updated": D(30),
        },
        {
            "id": "d5",
            "title": "Rosa's care notes",
            "category": "notes",
            "detail": (
                "Allergies: sulfa. Morning meds with coffee (~9am), evening with soup "
                "(~9pm). Hates being rushed — call before visiting. Gets anxious on "
                "calls after 8pm."
            ),
            "updated": D(2),
        },
    ]

    return {
        "family_name": FAMILY,
        "care_start": D(13),
        "parent_id": PARENT_ID,
        "members": members,
        "medications": medications,
        "history": history,
        "tasks": tasks,
        "appointments": appointments,
        "claims": claims,
        "expenses": expenses,
        "documents": documents,
        "digests": [],  # sent family weeks (Build 3): archive + opens
    }
