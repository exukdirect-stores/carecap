# 🫂 CareCap — *the care captain's OS*

**Build 2** of the Americas untapped-demand series (deep-dive Opportunity 4, ranked #1 for a
$1–5M team: fastest to cash, lowest regulatory load, freshest competitive vacuum).

> When 45–65-year-old adult children coordinate an aging parent's meds, appointments,
> money, and siblings — CareCap is the app they open. Siblings don't open apps.
> Siblings read the weekly digest.

## What's real in this build
- **Dose-safety engine** — grace-window (2h) missed detection + **per-slot consecutive-miss
  escalation** ("the evening dose has been missed 2 days in a row"). Per-slot, not
  per-day, because a 9am-confirm/9pm-miss day isn't a clean missed day — that's the
  alert that actually saves the week. PRN meds are never "missed".
- **Refill watch** — predicted run-out dates (pharmacy days-supply math) with a 7-day
  urgent buffer; PRN excluded from urgency (no scheduled consumption rate).
- **Weekly family digest** — a *pure, deterministic function* of the care graph
  (adherence, spend, appointments, rule-based priorities, team load). Same state +
  same clock ⇒ byte-identical output. The retention feature: it's what out-of-town
  siblings actually read.
- **Digest delivery + the read-moment (Build 3)** — one click sends the week to
  every sibling through a pluggable channel (`delivery.py` is the provider seam;
  email is simulated in the demo). Each send is archived per week with a delivery
  outbox; a sibling opening the digest is tracked (idempotent, first open wins) —
  so the **≥55% open-rate v0 gate is measured in the UI**, not guessed. Resending
  the same week replaces the record and resets opens.
- **Money ledger** — out-of-pocket by category (MTD) + insurance-claim status tracking
  (the "care + money" layer nobody else owns).
- **Multi-family + captain auth (Build 4)** — the state is a family map, each
  family gated by a captain bearer token (401 otherwise). `POST /api/families`
  is the concierge onboarding: family + captain + parent → a fresh family and
  its token, in one call. Families are fully isolated (state, tasks, claims,
  digests). Legacy single-family files migrate automatically to the v2 shape.
  The demo family's token (`demo-reyes-2026`) is shown on the sign-in screen.
- **Medication management (Build 5)** — the captain adds a medication (name,
  dose, time chips, PRN, days-supply), marks a **refill** (run-out clock
  resets to today, the urgent alert and watch row vanish), or discontinues
  one (med + its history removed). New meds track from today — no hindsight.
  A freshly onboarded family can now build a real regimen in the app.
- **Mobile / Play Store (Build 5)** — the app is a PWA (manifest, icons,
  offline-safe service worker) and `android/` holds a complete, buildable
  WebView wrapper (Gradle 8.9 wrapper, minSdk 24, upload keystore generated,
  CI that produces the signed `.aab`) plus a Play Console runbook.
- **Care team** — task assignment with accountability (overdue flags, who's carrying it).
- **Seed family**: Patricia (captain, 52, Austin) + Rosa (84, HTN/T2DM/osteoarthritis) +
  Miguel & Sofía; 14 days of realistic dose history (including the escalation story),
  appointments, claims, and a documents vault. Seed is **anchored to today**, so the
  demo always shows a live situation (`POST /api/reset` re-seeds).

## Run it
```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
pytest tests/ -q          # 64 tests: engine, refill, digest, delivery, families/auth, medications, API
```
(or `make dev` / `make test` / `make run`)

**Signing in:** the app now has a captain door. The demo family's token is
`demo-reyes-2026` (shown on the sign-in screen). New families get their own
token from the onboarding form — or straight from the API:
```bash
curl -X POST :8001/api/families -H 'Content-Type: application/json' \
  -d '{"family_name":"Carew","captain_name":"Ada","parent_name":"Nana"}'
# -> {"family_id": "carew-1a2b3c", "token": "fam-…", …}
curl :8001/api/state -H 'Authorization: Bearer fam-…'
```
The app runs on the captain's local timezone (`CARECAP_TZ` env var, defaults to
`Africa/Nairobi`) — the *day* the meds are due for, not the server's.

## Try it
0. **Sign in** — the demo token is prefilled (`demo-reyes-2026`). Or take the
   concierge path: *New family* → name, captain, parent → you're the captain
   of a fresh, empty family with its own token.
1. **Today** — the Gabapentin evening escalation + the Metformin refill warning are live
   on load; big targets confirm Rosa's doses (or fix the missed evening).
   **Build 5:** the Metformin alert now also offers *Got the new fill — mark
   refilled ✓* (alert + watch row clear, supply reset to today). Add a med
   via the form at the bottom (time chips, PRN, supply); the ✕ on any dose
   card discontinues it. A brand-new family starts here: first med in,
   board alive.
2. **Team** — add a task, assign it, watch the load shift; Miguel's POA task is overdue.
3. **Money** — log an expense; watch MTD and the category bars move; claims with status
   (the 16-day-old OptumRx claim is the "stale" story).
4. **Digest** — generate the family week, **send to the family group**, then watch the
   family inbox: simulate Miguel (San Diego) opening it, watch the open rate hit 50%
   (v0 gate ≥55% not met), then Sofía (Seattle) and the gate turns green.
5. **Vault** — POA, insurance cards, MOLST, doctor list + the parent's care notes.

## Publish

**v0.3.0** — containerized, PaaS-ready. `GET /api/health` reports the version.

**Right now (zero effort):** the sandbox preview link is a public URL —
share it in the family group today. It's ephemeral (the demo state resets
when the sandbox sleeps, and re-seeds fresh on wake — which is what a demo
wants).

**Permanent home (one-click PaaS)** — the app is a single Dockerfile; no
build step, no secrets, one env var (`CARECAP_TZ`):

```bash
# Render (render.yaml blueprint included)
git init && git add -A && git commit -m "carecap v0.3.0"
# → New > Blueprint > point at the repo → deploy

# …or Fly.io
fly launch --no-deploy && fly deploy

# …or any VPS / local
make docker-run        # see Makefile
```

Notes for the real world:
- **Persistence:** state is one JSON file (`CARECAP_DATA`). Mount a volume at
  `/srv/data` (Docker) or a disk (Render paid / Fly volume) — otherwise each
  boot re-seeds the demo family.
- **Timezone:** `CARECAP_TZ` (default `Africa/Nairobi`) sets the captain's
  local day — keep it pointed at the family, not the data center.
- **CORS:** off by default (same-origin frontend). Set `CARECAP_CORS_ORIGINS`
  to a comma-separated allowlist if the frontend ever deploys separately.
- **Going live with real email:** implement `app/delivery.py::deliver()`
  (SMTP/Postmark) — nothing else changes.

### Mobile & Google Play (Build 5)

Two tracks, zero duplicated logic — both are the same web app:

1. **PWA (no store needed, works today):** open the deployed URL in Android
   Chrome → menu → *Install app*. The manifest + service worker make it a
   full-screen, offline-capable home-screen app. iOS: *Share → Add to Home
   Screen*.
2. **Play Store (listed, badged, updatable):** `android/` is a complete,
   buildable WebView wrapper.
   - `./gradlew bundleRelease` → signed `app-release.aab` (upload keystore
     already generated in `android/`; credentials in `keystore.properties`)
   - Or CI: push to GitHub + 4 keystore secrets → tag `v0.5.0` → the
     workflow hands you the AAB
   - Full Play Console runbook (account → listing → signing → release):
     [`android/README.md`](android/README.md)
   - Point `BASE_URL` in `android/app/build.gradle` at your **permanent**
     backend URL before the first release (it currently points at this
     sandbox preview, which is ephemeral).
   - Backend deploys are instantly live for all store users — the wrapper
     never needs a re-release for app changes.

## Shape of the code
```
app/
  domain.py    pure functions: grace windows, per-slot streaks, adherence,
               refill math, build_digest(), digest_summaries() — no clock, no I/O
  seed.py      the Reyes family, 14 days of history, anchored to today
  delivery.py  the provider seam: deliver(recipient, subject, now) -> log entry
               (email simulated in demo; implement once for real sends)
  store.py     one JSON file (data/carecap.json) + lock. v2 shape:
               {version, families:{id:state}, tokens:{id:token}}; v1 files
               migrate automatically. Swap for Postgres later.
  models.py    pydantic validation at the HTTP edge only
  main.py      FastAPI, all family routes behind the captain-token dependency:
               POST /api/families (onboarding), GET /api/families/me,
               GET /api/state (graph + derived), POST /api/doses|tasks|
               expenses|documents, POST /api/medications (+/refill, +/delete),
               POST /api/digest (preview), POST /api/digests/send,
               GET /api/digests(/:id), POST /api/digests/:id/open, POST /api/reset
  static/      Today / Team / Money / Digest / Vault — a thin renderer over the API
tests/
  test_dose_engine.py   grace window, per-slot streaks, skipped≠missed, PRN
  test_refill.py        run-out math, 7-day buffer boundary, PRN exclusion
  test_digest.py        determinism, priority ranking, MTD, stale-claim threshold
  test_digests.py       sibling-only recipients, payload == pure function of state,
                        idempotent opens, non-recipient 404, open-rate math
  test_families.py      401s, token isolation between families, onboarding,
                        v1→v2 migration, reset scoping, no token leakage
  test_medications.py   add (no hindsight, validation, PRN rules), refill
                        (clock reset, alert clears), delete (no orphan history),
                        fresh-family regimen flow
  static/               index.html is the build output of scripts/inline_app.py
                        (one self-contained document — no cacheable assets);
                        manifest.webmanifest + sw.js + icons make it a PWA
  android/              Play Store WebView wrapper (Gradle wrapper, upload
                        keystore, CI AAB build) — see android/README.md
  test_api.py           seed story live on load, dose confirm clears escalation,
                        task/expense lifecycles, reset
```

**Design rule:** everything the family sees is a pure function of the care graph —
`now` is always passed in. That's what makes the digest trustworthy and the whole
engine testable without a database.

## v0 concierge (from the deep dive, before any code at scale)
10 families, done-with-you onboarding ($50 flat), 6 weeks.
**Gates:** ≥70% convert to $19.99/mo · weekly-digest open rate ≥55% · NPS ≥55.
**Kill criteria:** week 8 <50% pay → pivot to the money angle only; month 6 sibling
engagement <20% active → reposition as solo-caregiver product.

## What's deliberately out (swap map → production)
- **Payer/insurer integrations** (the B2B2C wedge: $3/enrolled/mo care-navigation
  benefits — the Spring-Health playbook for physical eldercare).
- **Sensor layer** (fall detection as *optional notification-only* hardware — the
  12.1%-CAGR segment; FDA SaMD boundary respected by staying out of diagnosis).
- **HIPAA**: consumer-authorized data only in v1; BAA + SOC2 when the first
  insurer/employer deal lands.
- **Next build candidates (Build 5+):** medication management UI (a brand-new
  family currently has an empty dose board), real delivery provider behind the
  seam (email now, SMS/WhatsApp for markets where email dies at the 45–65 age
  band), sibling roles (read + comment on the digest), pharmacy/claims integrations.
