"""API input models (validation at the edge).

The app state itself stays plain JSON-serializable dicts (see `store.py`);
pydantic only guards what comes in over HTTP.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DoseIn(BaseModel):
    med_id: str
    date: str  # YYYY-MM-DD
    slot: str  # HH:MM
    status: str = Field(pattern="^(taken|skipped|cleared)$")
    confirmed_by: str = "patricia"
    note: str = ""


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    assignee: str
    due_date: str  # YYYY-MM-DD
    created_by: str = "patricia"


class ExpenseIn(BaseModel):
    category: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0)
    note: str = ""
    date: Optional[str] = None  # defaults to today on the server


class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(pattern="^(legal|insurance|medical|notes)$")
    detail: str = ""


class DigestOpenIn(BaseModel):
    """Sibling read-moment: a recipient opened this week's digest."""
    member_id: str


class MedIn(BaseModel):
    """Build 5: add a medication to the family's regimen.

    `started` is the pharmacy fill date (defaults to today); `days_supply`
    drives the refill watch. `slots` are daily "HH:MM" times; PRN meds keep
    at least one slot so the dose board can show the "as needed" row.
    """
    name: str = Field(min_length=1, max_length=80)
    dose_label: str = Field(default="", max_length=80)
    slots: list[str] = Field(min_length=1, max_length=6)
    prn: bool = False
    started: Optional[str] = None  # YYYY-MM-DD fill date; defaults to today
    days_supply: int = Field(default=30, ge=1, le=365)
    notes: str = Field(default="", max_length=300)

    @field_validator("slots")
    @classmethod
    def _valid_slots(cls, v: list[str]) -> list[str]:
        for s in v:
            if not (len(s) == 5 and s[2] == ":" and s[0:2].isdigit() and s[3:5].isdigit()):
                raise ValueError(f"slot {s!r} must be HH:MM")
            h, m = int(s[0:2]), int(s[3:5])
            if h > 23 or m > 59:
                raise ValueError(f"slot {s!r} is not a time")
        return sorted(set(v))


class RefillIn(BaseModel):
    """Build 5: a new pharmacy fill — resets the run-out clock to today."""
    days_supply: Optional[int] = Field(default=None, ge=1, le=365)


class FamilyIn(BaseModel):
    """Concierge onboarding: create a family, get back its captain token."""
    family_name: str = Field(min_length=1, max_length=60)
    captain_name: str = Field(min_length=1, max_length=60)
    parent_name: str = Field(min_length=1, max_length=60)
