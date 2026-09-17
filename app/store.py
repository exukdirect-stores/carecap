"""Persistence: in-memory state, flushed to data/carecap.json on every change.

Build 4 (v2 shape) — multi-family:

    {
      "version": 2,
      "families": { "<fam_id>": <family state> },   # members, meds, history, ...
      "tokens":   { "<fam_id>": "<bearer token>" }, # captain credentials
    }

Files written by v1 (single family, no version key) migrate automatically:
the old state becomes the seeded demo family under the demo token.
One small JSON file, no DB — the logic lives in pure functions, so swapping
in Postgres later is a store-layer change only.
"""
from __future__ import annotations

import json
import pathlib
import secrets
import threading
from datetime import datetime
from typing import Callable, Optional

DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "carecap.json"

DEMO_FAMILY_ID = "reyes"
# Well-known on purpose: it's the demo login, shown on the sign-in screen.
DEMO_TOKEN = "demo-reyes-2026"


class Store:
    def __init__(
        self,
        seed_fn: Callable[[datetime], dict],
        empty_fn: Callable[[str, str, str, datetime], dict],
        now_fn: Optional[Callable[[], datetime]] = None,
        data_file: Optional[pathlib.Path] = None,
    ):
        self._lock = threading.Lock()
        self.data_file = data_file or DATA_FILE
        self._seed_fn = seed_fn
        self._empty_fn = empty_fn
        self._now_fn = now_fn or datetime.now
        self.state = self._load_or_seed()
        self._save()

    # ------------------------------------------------------------- loading

    def _load_or_seed(self) -> dict:
        raw = None
        try:
            raw = json.loads(self.data_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        migrated = self._migrate(raw)
        if migrated is not None:
            return migrated
        return self._seed_state(self._now_fn())

    @staticmethod
    def _migrate(raw) -> Optional[dict]:
        if isinstance(raw, dict) and raw.get("version") == 2:
            return raw
        if isinstance(raw, dict) and "members" in raw and "medications" in raw:
            raw.setdefault("digests", [])  # backfill Build 3 keys
            return {
                "version": 2,
                "families": {DEMO_FAMILY_ID: raw},
                "tokens": {DEMO_FAMILY_ID: DEMO_TOKEN},
            }
        return None

    def _seed_state(self, now: datetime) -> dict:
        return {
            "version": 2,
            "families": {DEMO_FAMILY_ID: self._seed_fn(now)},
            "tokens": {DEMO_FAMILY_ID: DEMO_TOKEN},
        }

    # -------------------------------------------------------------- access

    def snapshot(self) -> dict:
        with self._lock:
            return self.state

    def families(self) -> dict:
        with self._lock:
            return self.state["families"]

    def family(self, family_id: str) -> Optional[dict]:
        with self._lock:
            return self.state["families"].get(family_id)

    def token(self, family_id: str) -> Optional[str]:
        with self._lock:
            return self.state["tokens"].get(family_id)

    def resolve_token(self, token: str) -> Optional[str]:
        """family id for a bearer token, or None. Constant-shape lookup."""
        if not token:
            return None
        with self._lock:
            for fid, tok in self.state["tokens"].items():
                if tok == token:
                    return fid
            return None

    # ------------------------------------------------------------- writes

    def update_family(self, family_id: str, mutator: Callable[[dict], None]) -> None:
        with self._lock:
            mutator(self.state["families"][family_id])
            self._save()

    def _save(self) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.data_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        tmp.replace(self.data_file)

    def create_family(
        self, now: datetime, family_name: str, captain_name: str, parent_name: str
    ) -> tuple[str, str]:
        """Concierge onboarding: a fresh family + its captain token."""
        with self._lock:
            base = "".join(ch for ch in family_name.lower() if ch.isalnum())[:12] or "family"
            fid = f"{base}-{secrets.token_hex(3)}"
            while fid in self.state["families"]:
                fid = f"{base}-{secrets.token_hex(4)}"
            token = "fam-" + secrets.token_urlsafe(12)
            self.state["families"][fid] = self._empty_fn(family_name, captain_name, parent_name, now)
            self.state["tokens"][fid] = token
            self._save()
            return fid, token

    def reset_demo(self, now: datetime) -> dict:
        """Re-seed the demo family only (anchored to today); other families untouched."""
        with self._lock:
            self.state["families"][DEMO_FAMILY_ID] = self._seed_fn(now)
            self.state["tokens"][DEMO_FAMILY_ID] = DEMO_TOKEN
            self._save()
            return self.state["families"][DEMO_FAMILY_ID]

    def reset_family(self, family_id: str, family_state: dict) -> dict:
        with self._lock:
            self.state["families"][family_id] = family_state
            self._save()
            return self.state["families"][family_id]
