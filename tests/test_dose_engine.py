"""The dose-safety engine: grace windows + per-slot consecutive-miss escalation.

Design point under test: escalation is per-SLOT, not per-day. A day with the
9am dose confirmed and the 9pm dose missed is not a "missed day" — the alert
that actually saves the week names the slot.
"""
from datetime import date, datetime

from app import domain

# Thursday 2026-09-17 at noon.
NOW = datetime(2026, 9, 17, 12, 0)


def med(slots=("09:00", "21:00"), started="2026-09-01", prn=False):
    return {
        "id": "g",
        "name": "Med",
        "dose_label": "1",
        "slots": list(slots),
        "prn": prn,
        "started": started,
        "days_supply": 30,
        "track_from": started,
    }


def recs(*entries):
    out = []
    for mid, day, slot, status in entries:
        out.append(
            {"med_id": mid, "date": day, "slot": slot, "status": status,
             "confirmed_by": "t", "note": ""}
        )
    return out


# ------------------------------------------------------------ grace window

def test_pending_inside_grace_then_missed_after():
    m = med(slots=("09:00",))
    r = domain.index_records(recs())
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "09:00", datetime(2026, 9, 17, 10, 30)) == "pending"
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "09:00", datetime(2026, 9, 17, 11, 1)) == "missed"


def test_upcoming_slot_not_judged():
    m = med(slots=("21:00",))
    r = domain.index_records(recs())
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "21:00", NOW) == "upcoming"


def test_recorded_decision_wins_over_clock():
    m = med(slots=("09:00",))
    r = domain.index_records(recs(("g", "2026-09-17", "09:00", "taken")))
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "09:00", NOW) == "taken"
    r = domain.index_records(recs(("g", "2026-09-17", "09:00", "skipped")))
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "09:00", NOW) == "skipped"


# ------------------------------------------------------ per-slot escalation

def test_evening_streak_two_days_with_mornings_fine():
    # The seed story: morning doses all taken, evening missed on the 15th + 16th.
    m = med(slots=("09:00", "21:00"))
    entries = [("g", day, "09:00", "taken")
               for day in ("2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17")]
    entries += [("g", "2026-09-13", "21:00", "taken"), ("g", "2026-09-14", "21:00", "taken")]
    # 15th/16th evening: no record -> missed once past grace
    r = domain.index_records(recs(*entries))

    streak, dates = domain.consecutive_missed(m, r, NOW, "21:00")
    assert streak == 2
    assert dates == ["2026-09-16", "2026-09-15"]  # most-recent-first

    # the morning slot has no streak at all
    assert domain.consecutive_missed(m, r, NOW, "09:00")[0] == 0


def test_taken_breaks_streak():
    m = med(slots=("21:00",))
    r = domain.index_records(recs(("g", "2026-09-16", "21:00", "taken")))
    assert domain.consecutive_missed(m, r, NOW, "21:00")[0] == 0


def test_skipped_breaks_streak():
    # A recorded skip is a decision, not a miss.
    m = med(slots=("21:00",))
    r = domain.index_records(recs(("g", "2026-09-16", "21:00", "skipped")))
    assert domain.consecutive_missed(m, r, NOW, "21:00")[0] == 0


def test_pending_today_does_not_break_streak():
    # Evening is still within grace at noon; 14th/15th/16th missed, 13th taken.
    m = med(slots=("21:00",))
    r = domain.index_records(recs(("g", "2026-09-13", "21:00", "taken")))
    streak, dates = domain.consecutive_missed(m, r, NOW, "21:00")
    assert streak == 3
    assert dates == ["2026-09-16", "2026-09-15", "2026-09-14"]


def test_escalation_alert_fires_at_two():
    m = med(slots=("09:00", "21:00"))
    entries = [("g", day, "09:00", "taken") for day in ("2026-09-15", "2026-09-16")]
    entries += [("g", "2026-09-14", "21:00", "taken")]
    r = domain.index_records(recs(*entries))
    alerts = domain.dose_alerts(m, r, NOW)
    esc = [a for a in alerts if a["level"] == "escalation"]
    assert len(esc) == 1
    assert esc[0]["slot"] == "21:00"
    assert esc[0]["streak"] == 2
    assert "in a row" in esc[0]["message"]


def test_watch_alert_at_one():
    m = med(slots=("21:00",))
    r = domain.index_records(recs(("g", "2026-09-15", "21:00", "taken")))
    alerts = domain.dose_alerts(m, r, NOW)
    assert [a["level"] for a in alerts] == ["watch"]
    assert alerts[0]["missed_dates"] == ["2026-09-16"]


def test_prn_excluded_from_missed_detection():
    m = med(slots=("18:00",), prn=True)
    r = domain.index_records(recs())
    assert domain.dose_alerts(m, r, NOW) == []


def test_prn_unrecorded_is_never_missed_but_logged_shows_taken():
    m = med(slots=("18:00",), prn=True)
    r = domain.index_records(recs())
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "18:00", NOW) == "prn"
    r = domain.index_records(recs(("g", "2026-09-17", "18:00", "taken")))
    assert domain.slot_outcome(m, r, date(2026, 9, 17), "18:00", NOW) == "taken"


# ---------------------------------------------------------------- adherence

def test_adherence_counts_judged_slots_only():
    # 7-day window ending 2026-09-17, one daily 09:00 slot.
    # All recorded taken (11th..17th) -> 7/7.
    m = med(slots=("09:00",))
    days = ("2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14",
            "2026-09-15", "2026-09-16", "2026-09-17")
    r = domain.index_records(recs(*[("g", d, "09:00", "taken") for d in days]))
    a = domain.adherence(m, r, NOW)
    assert (a["taken"], a["closed"], a["rate"]) == (7, 7, 100)

    # drop the 15th -> unjudged slot past grace counts as missed
    r = domain.index_records(recs(*[("g", d, "09:00", "taken") for d in days if d != "2026-09-15"]))
    a = domain.adherence(m, r, NOW)
    assert (a["taken"], a["closed"]) == (6, 7)
    assert a["rate"] == 86  # round(100 * 6/7)
