"""CareCap API + demo frontend.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8001

Build 4: every family-scoped route requires a captain bearer token
(`Authorization: Bearer <token>` or `?token=<token>`). Tokens live in the
store next to the family they gate; `/api/state` and friends always operate
on exactly one family. `POST /api/families` is the concierge onboarding —
it creates a family and returns its token.

The API returns the family graph plus a `derived` block computed by the
pure domain functions. The frontend is a thin renderer over that.
"""
from __future__ import annotations

import os
import secrets
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import delivery, domain
from . import __version__
from .models import (
    DoseIn,
    DigestOpenIn,
    DocumentIn,
    ExpenseIn,
    FamilyIn,
    MedIn,
    RefillIn,
    TaskIn,
)
from .seed import build_empty_family, build_seed
from .store import DEMO_FAMILY_ID, Store

app = FastAPI(title="CareCap", description="The care captain's OS", version=__version__)
STATIC = Path(__file__).resolve().parent / "static"

# The care captain's local day, not the server's. Override with CARECAP_TZ.
_TZ = ZoneInfo(os.environ.get("CARECAP_TZ", "Africa/Nairobi"))
NOW = lambda: datetime.now(_TZ).replace(tzinfo=None)

# CORS is off by default (frontend is same-origin). Set CARECAP_CORS_ORIGINS
# to a comma-separated allowlist the day a separate frontend deploy exists.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CARECAP_CORS_ORIGINS", "").split(",") if o.strip()
]
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    """Deliberately frame-friendly: no X-Frame-Options / frame-ancestors,
    because the app is embedded in the arena preview and concierge demos."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-App-Version", __version__)
    # Never let a browser/preview proxy serve yesterday's app.js over today's.
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Data location is overridable (CARECAP_DATA) so tests never touch the live
# demo state file.
DATA_FILE = Path(
    os.environ.get(
        "CARECAP_DATA",
        str(Path(__file__).resolve().parent.parent / "data" / "carecap.json"),
    )
)

store = Store(seed_fn=build_seed, empty_fn=build_empty_family, now_fn=NOW, data_file=DATA_FILE)


# ----------------------------------------------------------------- auth


def _token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return request.query_params.get("token") or None


def current_family(request: Request) -> str:
    """Resolve the caller's family id from their captain token."""
    token = _token_from(request)
    family_id = store.resolve_token(token) if token else None
    if not family_id:
        raise HTTPException(status_code=401, detail="missing or invalid family token")
    return family_id


def with_derived(state: dict, now: datetime) -> dict:
    """Family graph + everything the UI needs, computed by pure functions."""
    records = domain.index_records(state["history"])
    today = now.date()
    today_iso = today.isoformat()

    today_doses = []
    for med in state["medications"]:
        for slot in med["slots"]:
            today_doses.append(
                {
                    "med_id": med["id"],
                    "med": med["name"],
                    "dose_label": med["dose_label"],
                    "slot": slot,
                    "slot_label": domain.slot_label(slot),
                    "prn": bool(med.get("prn")),
                    "outcome": domain.slot_outcome(med, records, today, slot, now),
                }
            )

    alerts: list[dict] = []
    for med in state["medications"]:
        alerts.extend(domain.dose_alerts(med, records, now))
    alerts.extend(domain.refill_alerts(state["medications"], now))

    month = today_iso[:7]
    mtd: dict[str, float] = {}
    for e in state["expenses"]:
        if e["date"][:7] == month:
            mtd[e["category"]] = round(mtd.get(e["category"], 0) + e["amount"], 2)

    tasks = []
    for t in state["tasks"]:
        delta = (date.fromisoformat(t["due_date"]) - today).days
        tasks.append(
            {**t, "days_to_due": delta, "overdue": t["status"] == "open" and delta < 0}
        )

    team_load = {}
    for m in state["members"]:
        open_t = [t for t in tasks if t["assignee"] == m["id"] and t["status"] == "open"]
        team_load[m["id"]] = {
            "open": len(open_t),
            "overdue": sum(1 for t in open_t if t["overdue"]),
        }

    return {
        **state,
        "now": now.isoformat(timespec="seconds"),
        "derived": {
            "parent": next(m for m in state["members"] if m["id"] == state["parent_id"]),
            "today_doses": today_doses,
            "alerts": alerts,
            "refills": [domain.refill_status(m, now) for m in state["medications"]],
            "adherence": [
                domain.adherence(m, records, now)
                for m in state["medications"]
                if not m.get("prn")
            ],
            "mtd": mtd,
            "mtd_total": round(sum(mtd.values()), 2),
            "tasks": tasks,
            "team_load": team_load,
        },
    }


# ------------------------------------------------------------------- meta


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "time": NOW().isoformat(timespec="seconds")}


@app.post("/api/families")
def create_family(body: FamilyIn):
    """Concierge onboarding: create a family, return its captain token.

    This is the 'done-with-you' step of the v0 plan — the concierge fills it
    in with the family on the first call, hands over the token, done.
    """
    now = NOW()
    family_id, token = store.create_family(
        now, body.family_name, body.captain_name, body.parent_name
    )
    fam = store.family(family_id)
    return {
        "family_id": family_id,
        "token": token,
        "family_name": fam["family_name"],
        "members": fam["members"],
    }


@app.get("/api/families/me")
def my_family(family_id: str = Depends(current_family)):
    fam = store.family(family_id)
    captain = next(m for m in fam["members"] if m["role"] == "captain")
    return {
        "family_id": family_id,
        "family_name": fam["family_name"],
        "captain": captain["name"],
    }


@app.get("/api/state")
def get_state(family_id: str = Depends(current_family)):
    return with_derived(store.family(family_id), NOW())


@app.post("/api/reset")
def reset(family_id: str = Depends(current_family)):
    """Re-seed the caller's family to its initial state (demo family to the
    full story anchored to today; other families to fresh onboarding)."""
    if family_id == DEMO_FAMILY_ID:
        store.reset_demo(NOW())
    else:
        fam = store.family(family_id)
        captain = next(m for m in fam["members"] if m["role"] == "captain")["name"]
        parent = next(m for m in fam["members"] if m["id"] == fam["parent_id"])["name"]
        store.reset_family(
            family_id, build_empty_family(fam["family_name"], captain, parent, NOW())
        )
    return with_derived(store.family(family_id), NOW())


# ------------------------------------------------------------------ actions


@app.post("/api/doses")
def set_dose(body: DoseIn, family_id: str = Depends(current_family)):
    """Upsert a dose confirmation: 'taken' | 'skipped' | 'cleared' (undo)."""
    fam = store.family(family_id)
    if not any(m["id"] == body.med_id for m in fam["medications"]):
        raise HTTPException(404, "unknown medication")

    def mutate(s: dict) -> None:
        s["history"] = [
            h
            for h in s["history"]
            if not (
                h["med_id"] == body.med_id
                and h["date"] == body.date
                and h["slot"] == body.slot
            )
        ]
        if body.status != "cleared":
            s["history"].append(
                {
                    "med_id": body.med_id,
                    "date": body.date,
                    "slot": body.slot,
                    "status": body.status,
                    "confirmed_by": body.confirmed_by,
                    "note": body.note,
                }
            )

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


# ----------------------------------------------------------- medications


def _med_by_id(fam: dict, med_id: str) -> dict:
    med = next((m for m in fam["medications"] if m["id"] == med_id), None)
    if med is None:
        raise HTTPException(404, "unknown medication")
    return med


@app.post("/api/medications")
def add_medication(body: MedIn, family_id: str = Depends(current_family)):
    """Build 5: add a medication. Tracking starts today — no hindsight."""
    now = NOW()
    fam = store.family(family_id)
    base = "".join(ch for ch in body.name.lower() if ch.isalnum())[:16] or "med"
    med_id = base
    while any(m["id"] == med_id for m in fam["medications"]):
        med_id = f"{base}-{secrets.token_hex(2)}"
    med = {
        "id": med_id,
        "name": body.name,
        "dose_label": body.dose_label,
        "slots": body.slots,
        "prn": body.prn,
        "started": body.started or now.date().isoformat(),
        "days_supply": body.days_supply,
        "track_from": now.date().isoformat(),
        "notes": body.notes,
    }

    def mutate(s: dict) -> None:
        s["medications"].append(med)

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/medications/{med_id}/refill")
def refill_medication(med_id: str, body: RefillIn, family_id: str = Depends(current_family)):
    """Build 5: new pharmacy fill — run-out clock resets to today.

    Closes the refill-urgent loop: the alert, the refill watch row, and the
    digest priority all disappear because the math is now far in the future.
    """
    now = NOW()
    fam = store.family(family_id)
    med = _med_by_id(fam, med_id)
    if med.get("prn"):
        raise HTTPException(400, "PRN medications have no supply to refill")

    def mutate(s: dict) -> None:
        m = next(x for x in s["medications"] if x["id"] == med_id)
        m["started"] = now.date().isoformat()
        if body.days_supply is not None:
            m["days_supply"] = body.days_supply

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/medications/{med_id}/delete")
def delete_medication(med_id: str, family_id: str = Depends(current_family)):
    """Build 5: discontinue — removes the med and its dose history."""
    fam = store.family(family_id)
    _med_by_id(fam, med_id)

    def mutate(s: dict) -> None:
        s["medications"] = [m for m in s["medications"] if m["id"] != med_id]
        s["history"] = [h for h in s["history"] if h["med_id"] != med_id]

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/tasks")
def add_task(body: TaskIn, family_id: str = Depends(current_family)):
    fam = store.family(family_id)
    if not any(m["id"] == body.assignee for m in fam["members"]):
        raise HTTPException(404, "unknown team member")

    def mutate(s: dict) -> None:
        s["tasks"].append(
            {
                "id": f"t{secrets.token_hex(3)}",
                "title": body.title,
                "assignee": body.assignee,
                "due_date": body.due_date,
                "status": "open",
                "created_by": body.created_by,
            }
        )

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str, family_id: str = Depends(current_family)):
    def mutate(s: dict) -> None:
        for t in s["tasks"]:
            if t["id"] == task_id:
                t["status"] = "open" if t["status"] == "done" else "done"
                return
        raise HTTPException(404, "unknown task")

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/expenses")
def add_expense(body: ExpenseIn, family_id: str = Depends(current_family)):
    iso = body.date or NOW().date().isoformat()

    def mutate(s: dict) -> None:
        s["expenses"].append(
            {
                "id": f"e{secrets.token_hex(3)}",
                "date": iso,
                "category": body.category,
                "amount": round(body.amount, 2),
                "note": body.note,
            }
        )

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


@app.post("/api/documents")
def add_document(body: DocumentIn, family_id: str = Depends(current_family)):
    def mutate(s: dict) -> None:
        s["documents"].append(
            {
                "id": f"d{secrets.token_hex(3)}",
                "title": body.title,
                "category": body.category,
                "detail": body.detail,
                "updated": NOW().date().isoformat(),
            }
        )

    store.update_family(family_id, mutate)
    return with_derived(store.family(family_id), NOW())


# ------------------------------------------------------------------ digest


@app.post("/api/digest")
def digest(family_id: str = Depends(current_family)):
    """The weekly family digest — a pure function of this family's graph."""
    return domain.build_digest(store.family(family_id), NOW())


@app.post("/api/digests/send")
def send_digest(family_id: str = Depends(current_family)):
    """Send this week's digest to the family's siblings — the retention feature."""
    now = NOW()
    fam = store.family(family_id)
    payload = domain.build_digest(fam, now)
    recipients = [m for m in fam["members"] if m["role"] == "sibling"]
    if not recipients:
        raise HTTPException(400, "no sibling recipients on the team")
    subject = (
        f"The {payload['family']} family week — "
        f"{payload['week_start']} to {payload['week_end']}"
    )
    record = {
        "id": f"w{payload['week_start']}",
        "week_start": payload["week_start"],
        "week_end": payload["week_end"],
        "generated_at": now.isoformat(timespec="seconds"),
        "subject": subject,
        "payload": payload,
        "sent_to": [r["id"] for r in recipients],
        "deliveries": [delivery.deliver(r, subject, now) for r in recipients],
        "opens": {},
    }

    def mutate(s: dict) -> None:
        s["digests"] = [d for d in s["digests"] if d["id"] != record["id"]]
        s["digests"].append(record)

    store.update_family(family_id, mutate)
    return record


@app.get("/api/digests")
def list_digests(family_id: str = Depends(current_family)):
    """Archive, newest week first, with the open-rate the v0 gate cares about."""
    return domain.digest_summaries(store.family(family_id)["digests"])


@app.get("/api/digests/{digest_id}")
def get_digest(digest_id: str, family_id: str = Depends(current_family)):
    d = next(
        (x for x in store.family(family_id)["digests"] if x["id"] == digest_id), None
    )
    if d is None:
        raise HTTPException(404, "unknown digest")
    return d


@app.post("/api/digests/{digest_id}/open")
def open_digest(digest_id: str, body: DigestOpenIn, family_id: str = Depends(current_family)):
    """Record a sibling opening the digest. Idempotent — first open wins."""
    fam = store.family(family_id)
    cur = next((x for x in fam["digests"] if x["id"] == digest_id), None)
    if cur is None:
        raise HTTPException(404, "unknown digest")
    if body.member_id not in cur["sent_to"]:
        raise HTTPException(404, "not a recipient of this digest")
    ts = NOW().isoformat(timespec="seconds")
    store.update_family(
        family_id,
        lambda s: next(x for x in s["digests"] if x["id"] == digest_id)["opens"].setdefault(
            body.member_id, ts
        ),
    )
    return next(x for x in store.family(family_id)["digests"] if x["id"] == digest_id)


# ----------------------------------------------------------------- frontend


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
