"""Build 5: medication management — add, refill, delete.

Contract:
- adding a med puts it on today's board, tracking from today (no hindsight,
  no retroactive missed-dose alerts);
- refill resets the run-out clock to today (urgent alert + watch row vanish);
- delete removes the med and its history (no orphans);
- validation at the edge (slot format, supply bounds, PRN refill is a 400).
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.store import DEMO_TOKEN


def client():
    c = TestClient(app, headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    c.post("/api/reset")  # fresh demo seed anchored to today
    return c


def med_names(s: dict) -> list[str]:
    return [m["name"] for m in s["medications"]]


# --------------------------------------------------------------------- add

def test_add_med_appears_on_board_and_tracks_from_today():
    c = client()
    r = c.post("/api/medications", json={
        "name": "Amlodipine", "dose_label": "5 mg · 1 pill",
        "slots": ["23:59"], "days_supply": 30,
        "notes": "Blood pressure — new addition",
    })
    assert r.status_code == 200
    s = r.json()
    assert "Amlodipine" in med_names(s)
    med = next(m for m in s["medications"] if m["name"] == "Amlodipine")
    today = s["now"][:10]
    assert med["started"] == today and med["track_from"] == today
    # on today's board, in the future => 'upcoming' at any run time
    board = [t for t in s["derived"]["today_doses"] if t["med_id"] == med["id"]]
    assert len(board) == 1 and board[0]["outcome"] == "upcoming"


def test_add_med_judged_only_from_today():
    """A med added mid-day may flag TODAY's early slot (the captain should
    confirm it), but never any day before onboarding."""
    c = client()
    c.post("/api/medications", json={"name": "Levothyroxine", "slots": ["07:00"]})
    s = c.get("/api/state").json()
    today = s["now"][:10]
    for a in s["derived"]["alerts"]:
        if a.get("med") == "Levothyroxine":
            assert a["missed_dates"] == [today]  # at most a same-day watch
    a = next(x for x in s["derived"]["adherence"] if x["med"] == "Levothyroxine")
    assert a["closed"] in (0, 1)  # only today's slot could ever be judged


def test_add_med_validation():
    c = client()
    assert c.post("/api/medications", json={"name": "", "slots": ["09:00"]}).status_code == 422
    assert c.post("/api/medications", json={"name": "X", "slots": []}).status_code == 422
    assert c.post("/api/medications", json={"name": "X", "slots": ["9:00"]}).status_code == 422
    assert c.post("/api/medications", json={"name": "X", "slots": ["25:00"]}).status_code == 422
    assert c.post("/api/medications", json={"name": "X", "slots": ["09:00"], "days_supply": 0}).status_code == 422
    # slots are de-duplicated + sorted server-side
    r = c.post("/api/medications", json={"name": "Sorty", "slots": ["21:00", "09:00", "09:00"]})
    assert r.status_code == 200
    m = next(m for m in r.json()["medications"] if m["name"] == "Sorty")
    assert m["slots"] == ["09:00", "21:00"]


def test_prn_med_has_no_obligations():
    c = client()
    c.post("/api/medications", json={"name": "Oxycodone", "slots": ["21:00"], "prn": True})
    s = c.get("/api/state").json()
    # no dose alerts, no refill urgency, never in the adherence table
    assert not [a for a in s["derived"]["alerts"] if a.get("med") == "Oxycodone"]
    assert not [a for a in s["derived"]["adherence"] if a["med"] == "Oxycodone"]
    # but it IS on the board as "as needed"
    board = [t for t in s["derived"]["today_doses"] if t["med"] == "Oxycodone"]
    assert len(board) == 1 and board[0]["prn"]


# ------------------------------------------------------------------ refill

def test_refill_resets_supply_and_clears_urgent_alert():
    c = client()
    # metformin in the seed: 4 days left -> urgent alert present
    s = c.get("/api/state").json()
    assert any(a["kind"] == "refill" and a["med"] == "Metformin" for a in s["derived"]["alerts"])

    r = c.post("/api/medications/metformin/refill", json={"days_supply": 30})
    assert r.status_code == 200
    s = r.json()
    assert not [a for a in s["derived"]["alerts"] if a.get("med") == "Metformin"]
    med = next(m for m in s["medications"] if m["id"] == "metformin")
    assert med["started"] == s["now"][:10] and med["days_supply"] == 30
    r0 = next(x for x in s["derived"]["refills"] if x["med"] == "Metformin")
    assert r0["days_left"] == 30 and not r0["urgent"]


def test_refill_default_keeps_current_supply():
    c = client()
    c.post("/api/medications/lisinopril/refill", json={})
    s = c.get("/api/state").json()
    r0 = next(x for x in s["derived"]["refills"] if x["med"] == "Lisinopril")
    assert r0["days_left"] == 30  # original days_supply kept


def test_refill_prn_is_400_and_unknown_is_404():
    c = client()
    assert c.post("/api/medications/naproxen/refill", json={}).status_code == 400
    assert c.post("/api/medications/nope/refill", json={}).status_code == 404


# ------------------------------------------------------------------ delete

def test_delete_removes_med_and_its_history():
    c = client()
    # take a dose for calcium so history exists, then discontinue it
    c.post("/api/doses", json={"med_id": "calcium", "date": c.get("/api/state").json()["now"][:10],
                               "slot": "13:00", "status": "taken"})
    assert any(h["med_id"] == "calcium" for h in c.get("/api/state").json()["history"])

    r = c.post("/api/medications/calcium/delete")
    assert r.status_code == 200
    s = r.json()
    assert "Calcium + D3" not in med_names(s)
    assert not [h for h in s["history"] if h["med_id"] == "calcium"]
    assert not [t for t in s["derived"]["today_doses"] if t["med"] == "Calcium + D3"]
    # the other meds are untouched
    assert "Metformin" in med_names(s)


def test_delete_unknown_is_404():
    c = client()
    assert c.post("/api/medications/nope/delete").status_code == 404


# ------------------------------------------------------------- new families

def test_new_family_can_build_a_regimen():
    """The Build 4 gap this closes: a fresh onboarding family can track meds."""
    anon = TestClient(app)
    body = anon.post("/api/families", json={
        "family_name": "Osei", "captain_name": "Ama Osei", "parent_name": "Kwame Osei",
    }).json()
    c = TestClient(app, headers={"Authorization": f"Bearer {body['token']}"})
    assert c.get("/api/state").json()["medications"] == []

    c.post("/api/medications", json={"name": "Metformin", "dose_label": "500 mg", "slots": ["08:00", "20:00"]})
    s = c.get("/api/state").json()
    assert len(s["medications"]) == 1
    assert len(s["derived"]["today_doses"]) == 2

    c.post("/api/doses", json={"med_id": s["medications"][0]["id"], "date": s["now"][:10],
                               "slot": "08:00", "status": "taken"})
    s = c.get("/api/state").json()
    board = {t["slot"]: t["outcome"] for t in s["derived"]["today_doses"]}
    assert board["08:00"] == "taken"  # the recorded decision always wins

    # digest works on a one-med family
    d = c.post("/api/digest").json()
    assert d["adherence"]["by_medication"][0]["med"] == "Metformin"
    assert d["adherence"]["taken"] >= 1
