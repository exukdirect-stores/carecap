# 🫂 CareCap — *the care captain's OS*

**Build 2** of the Americas untapped-demand series (deep-dive Opportunity 4, ranked #1 for a
$1–5M team: fastest to cash, lowest regulatory load, freshest competitive vacuum).

> When 45–65-year-old adult children coordinate an aging parent's meds, appointments,
> money, and siblings — CareCap is the app they open. Siblings don't open apps.
> Siblings read the weekly digest.

## What's real in this build
- **Dose-safety engine** — grace-window missed detection + **per-slot consecutive-miss
  escalation** ("the evening dose has been missed 2 days in a row"). Per-slot, not
  per-day, because a 9am-confirm/9pm-miss day isn't a clean missed day — that's the
  alert that actually saves the week.
- **Refill watch** — predicted run-out dates with a 7-day urgent buffer.
- **Weekly family digest** — a *pure, deterministic function* of the care graph
  (adherence, spend, appointments, rule-based priorities, team load). The retention
  feature: it's what out-of-town siblings actually read.
- **Money ledger** — out-of-pocket by category + insurance-claim status tracking
  (the "care + money" layer nobody else owns).
- **Care team** — task assignment with accountability (overdue flags, who's carrying it).
- **Seed family**: Patricia (captain, 52, Austin) + Rosa (84, HTN/T2DM/osteoarthritis) +
  Miguel & Sofía; 14 days of realistic dose history (including the escalation story),
  appointments, claims, and a documents vault.

## Run it
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
pytest tests/ -q
```

## Try it
1. **Today** — confirm Rosa's doses (big targets, the daily ritual); note the Gabapentin
   escalation + the refill warning on Metformin.
2. **Team** — add a task, assign it, watch the load shift.
3. **Money** — log an expense; watch MTD and the category bars move; claims with status.
4. **Digest** — generate the family week; "send to the family group" is the demo hook.
5. **Vault** — POA, insurance cards, MOLST, doctor list + the parent's care notes.

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
