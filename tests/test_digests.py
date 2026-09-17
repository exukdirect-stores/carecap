"""Build 3: digest delivery — the sibling read-moment.

Contract: send builds the payload as the pure function of the current care
graph, delivers to every sibling (not the parent, not the captain), archives
one record per week (re-send replaces, opens reset), opens are idempotent
(first open wins) and only recipients can open. The open-rate list is what
the >=55% v0 gate is measured on.
"""
from datetime import datetime

from fastapi.testclient import TestClient

from app import domain
from app.main import app
from app.store import DEMO_TOKEN


def client():
    c = TestClient(app, headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    c.post("/api/reset")
    return c


def test_send_creates_record_with_sibling_recipients():
    c = client()
    rec = c.post("/api/digests/send").json()
    # recipients = siblings only: not the parent, not the sending captain
    assert rec["sent_to"] == ["miguel", "sofia"]
    assert rec["id"] == "w" + rec["week_start"]
    assert len(rec["deliveries"]) == 2
    assert all(d["status"] == "sent" and d["channel"] == "email" for d in rec["deliveries"])
    assert rec["opens"] == {}

    rows = c.get("/api/digests").json()
    assert len(rows) == 1
    assert rows[0]["id"] == rec["id"]
    assert rows[0]["sent_to"] == 2 and rows[0]["opened"] == 0
    assert rows[0]["open_rate"] == 0


def test_sent_payload_is_pure_function_of_state():
    c = client()
    rec = c.post("/api/digests/send").json()
    s = c.get("/api/state").json()
    raw = {k: s[k] for k in s if k not in ("now", "derived")}
    expected = domain.build_digest(raw, datetime.fromisoformat(s["now"]))
    assert rec["payload"] == expected


def test_send_is_deterministic_for_the_same_week():
    c = client()
    r1 = c.post("/api/digests/send").json()
    c.post("/api/reset")
    r2 = c.post("/api/digests/send").json()
    assert r1["payload"] == r2["payload"]
    assert r1["id"] == r2["id"]


def test_resend_same_week_replaces_record_and_resets_opens():
    c = client()
    rec = c.post("/api/digests/send").json()
    c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "miguel"})
    rec2 = c.post("/api/digests/send").json()
    assert rec2["id"] == rec["id"]
    assert rec2["opens"] == {}
    assert len(c.get("/api/digests").json()) == 1  # still one record per week


def test_open_is_idempotent_first_open_wins():
    c = client()
    rec = c.post("/api/digests/send").json()
    r1 = c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "miguel"}).json()
    r2 = c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "miguel"}).json()
    assert r1["opens"] == r2["opens"]
    assert len(r2["opens"]) == 1


def test_only_recipients_can_open():
    c = client()
    rec = c.post("/api/digests/send").json()
    assert c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "patricia"}).status_code == 404
    assert c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "rosa"}).status_code == 404
    assert c.post("/api/digests/w2000-01-01/open", json={"member_id": "miguel"}).status_code == 404


def test_open_rate_moves_with_opens():
    c = client()
    rec = c.post("/api/digests/send").json()
    c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "miguel"})
    rows = c.get("/api/digests").json()
    assert (rows[0]["opened"], rows[0]["open_rate"]) == (1, 50)
    c.post(f"/api/digests/{rec['id']}/open", json={"member_id": "sofia"})
    rows = c.get("/api/digests").json()
    assert (rows[0]["opened"], rows[0]["open_rate"]) == (2, 100)


def test_get_digest_detail_and_404():
    c = client()
    rec = c.post("/api/digests/send").json()
    got = c.get(f"/api/digests/{rec['id']}").json()
    assert got["payload"]["family"] == "Reyes"
    assert got["subject"].startswith("The Reyes family week")
    assert c.get("/api/digests/w2000-01-01").status_code == 404


def test_archive_newest_week_first_with_open_rates():
    # pure function: ordering + open-rate math over fabricated records
    def rec(week_start, opens):
        return {
            "id": f"w{week_start}",
            "week_start": week_start,
            "week_end": week_start,
            "generated_at": "2026-09-17T09:00:00",
            "subject": "s",
            "payload": {},
            "sent_to": ["miguel", "sofia"],
            "deliveries": [],
            "opens": opens,
        }

    rows = domain.digest_summaries([rec("2026-09-04", {"miguel": "t"}), rec("2026-09-11", {})])
    assert [r["week_start"] for r in rows] == ["2026-09-11", "2026-09-04"]
    assert rows[0]["open_rate"] == 0  # this week: nothing opened yet
    assert rows[1]["open_rate"] == 50  # older week: 1 of 2
