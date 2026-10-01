"""Sidecar log of successfully-sent certificates, keyed by Certificate ID
(see cm_utils.make_row_key). Never touches the user's source file."""

import json
from datetime import datetime, timedelta

from cm_utils import atomic_write_json


class SentLog:
    def __init__(self, path):
        self.path = path
        self.entries = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries")
            self.entries = entries if isinstance(entries, dict) else {}
        except Exception:
            self.entries = {}

    def save(self):
        try:
            atomic_write_json(self.path, {"version": 1, "entries": self.entries})
        except Exception:
            pass

    def get(self, key, email):
        """The log entry if this key was sent to THIS address, else None (so a
        corrected email address makes the row eligible again)."""
        e = self.entries.get(key)
        if e and str(e.get("email", "")).lower() == (email or "").lower():
            return e
        return None

    def is_sent(self, key, email):
        return self.get(key, email) is not None

    def record(self, key, email, name, filename):
        self.entries[key] = {
            "email": email, "name": name, "file": filename,
            "sent_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.save()

    def count_since(self, hours=24):
        cutoff = datetime.now() - timedelta(hours=hours)
        n = 0
        for e in self.entries.values():
            try:
                if datetime.fromisoformat(e.get("sent_at", "")) >= cutoff:
                    n += 1
            except ValueError:
                continue
        return n

    def clear(self):
        self.entries = {}
        self.save()
