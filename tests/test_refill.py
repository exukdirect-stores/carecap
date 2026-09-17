"""Refill watch: predicted run-out dates with a 7-day urgent buffer."""
from datetime import datetime

from app import domain

NOW = datetime(2026, 9, 17, 12, 0)


def med(started, supply):
    return {
        "id": "m", "name": "M", "dose_label": "1", "slots": ["09:00"],
        "prn": False, "started": started, "days_supply": supply,
    }


def test_run_out_and_days_left():
    # started 7 days ago, 11-day supply -> 4 days left, urgent (the seed story)
    r = domain.refill_status(med("2026-09-10", 11), NOW)
    assert r["run_out"] == "2026-09-21"
    assert r["days_left"] == 4
    assert r["urgent"] is True


def test_urgent_buffer_boundary_at_seven_days():
    # run-out exactly 7 days out -> urgent; 8 days out -> not
    r7 = domain.refill_status(med("2026-09-10", 14), NOW)
    r8 = domain.refill_status(med("2026-09-10", 15), NOW)
    assert r7["days_left"] == 7 and r7["urgent"] is True
    assert r8["days_left"] == 8 and r8["urgent"] is False


def test_run_out_already_past_is_urgent():
    r = domain.refill_status(med("2026-09-01", 10), NOW)
    assert r["days_left"] == -6
    assert r["urgent"] is True


def test_refill_alerts_only_for_urgent():
    meds = [med("2026-09-10", 11), med("2026-09-10", 30)]
    alerts = domain.refill_alerts(meds, NOW)
    assert len(alerts) == 1
    assert alerts[0]["days_left"] == 4


def test_prn_excluded_from_refill_urgency():
    prn = med("2026-09-13", 8)  # 4 days left -> would be urgent if scheduled
    prn["prn"] = True
    assert domain.refill_alerts([prn], NOW) == []
    # status itself is still available for display
    assert domain.refill_status(prn, NOW)["days_left"] == 4
    assert domain.refill_status(prn, NOW)["urgent"] is True
