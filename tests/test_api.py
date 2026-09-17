"""End-to-end API tests: seed load, dose confirmations, tasks, money, digest."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.store import DEMO_TOKEN


def client():
    c = TestClient(app, headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    c.post("/api/reset")  # fresh demo seed anchored to today
    return c


def test_health_and_seeded_state():
    c = client()
    assert c.get("/api/health").json()["ok"] is True

    s = c.get("/api/state").json()
    assert s["family_name"] == "Reyes"
    assert len(s["members"]) == 4
    assert s["derived"]["today_doses"]

    # the seed story is live on load
    alerts = s["derived"]["alerts"]
    assert any(a["kind"] == "dose" and a["level"] == "escalation" for a in alerts)
    assert any(a["kind"] == "refill" for a in alerts)


def test_confirming_missed_dose_clears_escalation():
    c = client()
    s = c.get("/api/state").json()
    today = s["now"][:10]
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    # mark gabapentin's missed evenings as taken (the most recent missed day)
    for day in (yesterday,):
        r = c.post("/api/doses", json={
            "med_id": "gabapentin", "date": day, "slot": "21:00", "status": "taken",
        })
        assert r.status_code == 200

    s2 = c.get("/api/state").json()
    assert not any(a.get("med") == "Gabapentin" and a["level"] == "escalation"
                   for a in s2["derived"]["alerts"])


def test_dose_cleared_undoes_record():
    c = client()
    c.post("/api/doses", json={"med_id": "lisinopril", "date": "2000-01-01",
                               "slot": "09:00", "status": "taken"})
    s = c.get("/api/state").json()
    assert any(h["med_id"] == "lisinopril" and h["date"] == "2000-01-01"
               for h in s["history"])
    c.post("/api/doses", json={"med_id": "lisinopril", "date": "2000-01-01",
                               "slot": "09:00", "status": "cleared"})
    s = c.get("/api/state").json()
    assert not any(h["date"] == "2000-01-01" for h in s["history"])


def test_task_lifecycle_and_overdue_flag():
    c = client()
    today = c.get("/api/state").json()["now"][:10]
    c.post("/api/tasks", json={"title": "Test task", "assignee": "miguel",
                               "due_date": today})
    s = c.get("/api/state").json()
    t = next(t for t in s["derived"]["tasks"] if t["title"] == "Test task")
    assert t["status"] == "open" and not t["overdue"]

    c.post(f"/api/tasks/{t['id']}/toggle")
    s = c.get("/api/state").json()
    t = next(t for t in s["derived"]["tasks"] if t["title"] == "Test task")
    assert t["status"] == "done"

    # team load reflects the change
    assert s["derived"]["team_load"]["miguel"]["open"] == 1  # only the seeded overdue one


def test_expense_updates_mtd():
    c = client()
    before = c.get("/api/state").json()["derived"]["mtd_total"]
    r = c.post("/api/expenses", json={"category": "Other", "amount": 5.5, "note": "test"})
    assert r.status_code == 200
    after = c.get("/api/state").json()["derived"]["mtd_total"]
    assert abs(after - before - 5.5) < 0.005


def test_digest_endpoint_and_reset():
    c = client()
    d = c.post("/api/digest").json()
    assert d["family"] == "Reyes"
    assert d["priorities"]
    assert d["adherence"]["overall_rate"] is not None

    c.post("/api/tasks", json={"title": "Test task", "assignee": "miguel",
                               "due_date": "2026-09-20"})
    c.post("/api/reset")
    s = c.get("/api/state").json()
    assert all(t["title"] != "Test task" for t in s["derived"]["tasks"])


def test_unknown_medication_rejected():
    c = client()
    r = c.post("/api/doses", json={"med_id": "nope", "date": "2026-09-17",
                                   "slot": "09:00", "status": "taken"})
    assert r.status_code == 404


def test_index_serves_frontend():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "CareCap" in r.text
