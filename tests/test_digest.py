"""The weekly family digest — a pure, deterministic function of the care graph.

Same state + same `now` => identical output. Rule-based priorities in a fixed
rank order: dose-escalation > refill-urgent > claim-stale > task-overdue > dose-watch.
"""
import json
from datetime import datetime, timedelta

from app import domain
from app.seed import build_seed

NOW = datetime(2026, 9, 17, 12, 0)


def seeded():
    return build_seed(NOW)


def test_digest_is_deterministic():
    s = seeded()
    a = domain.build_digest(s, NOW)
    b = domain.build_digest(json.loads(json.dumps(s)), NOW)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_seed_story_is_present():
    d = domain.build_digest(seeded(), NOW)
    rules = {p["rule"] for p in d["priorities"]}
    # Gabapentin evening 2-day streak
    assert any("Gabapentin" in p["text"] for p in d["priorities"] if p["rule"] == "dose-escalation")
    # Metformin refill within the 7-day buffer
    assert any(p["rule"] == "refill-urgent" and "Metformin" in p["text"] for p in d["priorities"])
    # OptumRx claim pending 16 days -> stale
    assert "claim-stale" in rules
    # Miguel's task was due yesterday
    assert any(p["rule"] == "task-overdue" and "Miguel" in p["text"] for p in d["priorities"])


def test_priority_ranking_and_ranks():
    d = domain.build_digest(seeded(), NOW)
    rules = [p["rule"] for p in d["priorities"]]
    order = {"dose-escalation": 0, "refill-urgent": 1, "claim-stale": 2,
             "task-overdue": 3, "dose-watch": 4}
    assert rules == sorted(rules, key=lambda r: order[r])
    assert [p["rank"] for p in d["priorities"]] == list(range(1, len(d["priorities"]) + 1))


def test_watch_priority_for_single_miss():
    s = seeded()
    yesterday = (NOW.date() - timedelta(days=1)).isoformat()
    # remove calcium's yesterday record -> one-off miss, no streak
    s["history"] = [h for h in s["history"]
                    if not (h["med_id"] == "calcium" and h["date"] == yesterday)]
    d = domain.build_digest(s, NOW)
    watch = [p for p in d["priorities"] if p["rule"] == "dose-watch"]
    assert len(watch) == 1
    assert "Calcium" in watch[0]["text"]


def test_mtd_only_counts_current_month():
    s = seeded()
    month = NOW.date().isoformat()[:7]
    s["expenses"] = [e for e in s["expenses"] if e["date"][:7] == month]
    d = domain.build_digest(s, NOW)
    expected = round(sum(e["amount"] for e in s["expenses"]), 2)
    assert d["money"]["mtd_total"] == expected
    assert d["money"]["mtd_total"] >= 22.0  # today's pharmacy copay is always in


def test_stale_claim_rule_threshold_at_fourteen_days():
    s = seeded()
    s["claims"] = [{"id": "c1", "payer": "P", "kind": "rx", "amount": 10.0,
                    "submitted": "2026-09-04", "status": "pending"}]  # 13 days old
    d13 = domain.build_digest(s, NOW)
    assert not [p for p in d13["priorities"] if p["rule"] == "claim-stale"]

    s["claims"][0]["submitted"] = "2026-09-03"  # 14 days old
    d14 = domain.build_digest(s, NOW)
    assert [p for p in d14["priorities"] if p["rule"] == "claim-stale"]


def test_team_load_counts_open_and_overdue():
    d = domain.build_digest(seeded(), NOW)
    load = d["team_load"]
    assert load["patricia"]["open"] == 1  # t1 open (t4 done)
    assert load["miguel"]["open"] == 1 and load["miguel"]["overdue"] == 1
    assert load["sofia"]["open"] == 1 and load["sofia"]["overdue"] == 0
    assert load["rosa"] == {"name": "Rosa Reyes", "open": 0, "overdue": 0}


def test_adherence_uses_seven_day_window():
    d = domain.build_digest(seeded(), NOW)
    a = d["adherence"]
    # 7-day window, judged slots only: all non-PRN meds. Seeded gaps in the
    # window: 2 gabapentin evenings + 1 calcium one-off + 1 intentional
    # lisinopril skip ("skipped" counts as closed, not taken).
    assert a["closed"] > 0
    assert a["taken"] + 4 == a["closed"]
    assert a["overall_rate"] == round(100 * a["taken"] / a["closed"])
