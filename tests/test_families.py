"""Build 4: multi-family + captain auth.

Contract: every family-scoped route requires a captain token (401 without);
families are fully isolated (state, tasks, digests); onboarding creates a
family + token; legacy v1 files migrate to v2 under the demo token; tokens
never leak into state responses.
"""
import json
import pathlib
import tempfile
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.seed import build_empty_family, build_seed
from app.store import DEMO_FAMILY_ID, DEMO_TOKEN, Store


def client():
    c = TestClient(app, headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    c.post("/api/reset")
    return c


def anon():
    return TestClient(app)


# ------------------------------------------------------------------- auth

def test_missing_token_is_401():
    c = anon()
    assert c.get("/api/state").status_code == 401
    assert c.post("/api/digests/send").status_code == 401
    assert c.get("/api/digests").status_code == 401


def test_wrong_token_is_401():
    c = anon()
    assert c.get("/api/state", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_demo_token_works_and_token_query_is_accepted():
    c = anon()
    r = c.get("/api/families/me", headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    assert r.status_code == 200
    assert r.json()["family_name"] == "Reyes"
    r2 = c.get("/api/state", params={"token": DEMO_TOKEN})
    assert r2.status_code == 200
    assert r2.json()["family_name"] == "Reyes"


def test_token_never_leaks_into_state():
    c = client()
    s = c.get("/api/state").json()
    assert DEMO_TOKEN not in json.dumps(s)


# ------------------------------------------------------------- onboarding

def test_create_family_returns_token_and_members():
    c = anon()
    r = c.post(
        "/api/families",
        json={"family_name": "Carew", "captain_name": "Ada Carew", "parent_name": "Nana Carew"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["family_name"] == "Carew"
    assert body["token"].startswith("fam-")
    roles = {m["name"]: m["role"] for m in body["members"]}
    assert roles == {"Ada Carew": "captain", "Nana Carew": "parent"}


def test_new_family_is_empty_and_usable():
    anon_c = anon()
    body = anon_c.post(
        "/api/families",
        json={"family_name": "Dube", "captain_name": "Kin Dube", "parent_name": "Baba Dube"},
    ).json()
    tok = body["token"]
    c = TestClient(app, headers={"Authorization": f"Bearer {tok}"})
    s = c.get("/api/state").json()
    assert s["family_name"] == "Dube"
    assert s["medications"] == [] and s["tasks"] == [] and s["digests"] == []
    # a brand-new family can already do the core loop
    r = c.post("/api/tasks", json={"title": "First task", "assignee": "c1", "due_date": "2026-09-30"})
    assert r.status_code == 200
    assert len(c.get("/api/state").json()["derived"]["tasks"]) == 1
    # and its digest is a graceful empty week
    d = c.post("/api/digest").json()
    assert d["adherence"]["overall_rate"] is None
    assert "First week" in d["headline"]


def test_families_are_fully_isolated():
    anon_c = anon()
    body = anon_c.post(
        "/api/families",
        json={"family_name": "Iyanda", "captain_name": "Chidi Iyanda", "parent_name": "Mama Iyanda"},
    ).json()
    other = TestClient(app, headers={"Authorization": f"Bearer {body['token']}"})
    other.post("/api/tasks", json={"title": "Iyanda secret task", "assignee": "c1",
                                   "due_date": "2026-09-30"})
    # no siblings on the team yet -> digest send is a clean 400, not a crash
    assert other.post("/api/digests/send").status_code == 400

    demo = client()
    s = demo.get("/api/state").json()
    assert s["family_name"] == "Reyes"
    assert all(t["title"] != "Iyanda secret task" for t in s["derived"]["tasks"])
    assert all(d["payload"]["family"] == "Reyes" for d in s["digests"])

    # the other family sees none of Reyes' data either
    s2 = other.get("/api/state").json()
    assert s2["family_name"] == "Iyanda"
    assert any(t["title"] == "Iyanda secret task" for t in s2["derived"]["tasks"])
    assert all(m["name"] != "Rosa Reyes" for m in s2["members"])


def test_two_families_get_distinct_tokens():
    anon_c = anon()
    a = anon_c.post("/api/families", json={"family_name": "A", "captain_name": "A", "parent_name": "PA"}).json()
    b = anon_c.post("/api/families", json={"family_name": "B", "captain_name": "B", "parent_name": "PB"}).json()
    assert a["token"] != b["token"]
    assert a["family_id"] != b["family_id"]
    # A's token can't open B's data
    ca = TestClient(app, headers={"Authorization": f"Bearer {a['token']}"})
    assert ca.get("/api/state").json()["family_name"] == "A"


# ------------------------------------------------------------- reset scope

def test_reset_rescopes_to_caller_family():
    anon_c = anon()
    body = anon_c.post(
        "/api/families",
        json={"family_name": "Mbeki", "captain_name": "Zol Mbeki", "parent_name": "Gogo Mbeki"},
    ).json()
    other = TestClient(app, headers={"Authorization": f"Bearer {body['token']}"})
    other.post("/api/tasks", json={"title": "scratch", "assignee": "c1", "due_date": "2026-09-30"})

    # demo reset keeps the other family alive (with its data)
    client()  # resets the demo family
    s = other.get("/api/state").json()
    assert s["family_name"] == "Mbeki"
    assert any(t["title"] == "scratch" for t in s["derived"]["tasks"])

    # ...but the other family's own reset wipes its data, back to onboarding
    other.post("/api/reset")
    s2 = other.get("/api/state").json()
    assert s2["tasks"] == []
    assert len(s2["members"]) == 2  # captain + parent kept


# --------------------------------------------------------------- migration

def test_fresh_state_is_v2():
    with tempfile.TemporaryDirectory() as td:
        s = Store(build_seed, build_empty_family, data_file=pathlib.Path(td) / "f.json")
        raw = s.snapshot()
        assert raw["version"] == 2
        assert DEMO_FAMILY_ID in raw["families"]
        assert s.resolve_token(DEMO_TOKEN) == DEMO_FAMILY_ID


def test_legacy_v1_file_migrates_to_v2():
    """A file written by Build 2/3 (single family, no version key) must load
    as the demo family under the demo token."""
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "f.json"
        v1 = build_seed(datetime(2026, 9, 17, 12, 0))  # a v1-shaped family state
        p.write_text(json.dumps(v1))
        s = Store(build_seed, build_empty_family, data_file=p)
        raw = s.snapshot()
        assert raw["version"] == 2
        assert raw["families"][DEMO_FAMILY_ID]["family_name"] == "Reyes"
        assert s.resolve_token(DEMO_TOKEN) == DEMO_FAMILY_ID
        # and it round-trips: rewriting keeps v2 shape
        s.update_family(DEMO_FAMILY_ID, lambda f: f["tasks"].append(
            {"id": "t9", "title": "x", "assignee": "patricia",
             "due_date": "2026-09-20", "status": "open", "created_by": "patricia"}
        ))
        assert json.loads(p.read_text())["version"] == 2


def test_empty_family_shape():
    fam = build_empty_family("Test", "Cap Test", "Par Test", datetime(2026, 9, 17, 12, 0))
    assert fam["parent_id"] == "p1"
    assert {m["role"] for m in fam["members"]} == {"captain", "parent"}
    assert fam["medications"] == [] and fam["digests"] == []
