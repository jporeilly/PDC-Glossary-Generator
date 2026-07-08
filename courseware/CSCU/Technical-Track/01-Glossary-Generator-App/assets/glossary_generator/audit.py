"""
Steward **audit trail** — an append-only record of governance actions (who did
what, when) so the vocabulary's history is defensible and travels with the Registry.

Records dictionary saves, pending approve/reject decisions, and reseeds, each with a
UTC timestamp and an actor. In this single-user training app the actor is supplied by
the client ("Acting as …") and defaults to $GLOSSARY_STEWARD or "steward"; in a real
deployment it would come from the authenticated identity. Persisted to audit_log.json
(override with $GLOSSARY_AUDIT_LOG).
"""
from __future__ import annotations
import os, json, threading, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_FILE = os.environ.get("GLOSSARY_AUDIT_LOG") or os.path.join(HERE, "audit_log.json")
_LOCK = threading.Lock()
_CAP = 5000  # keep the last N entries on disk


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _clean_actor(actor):
    a = (str(actor).strip() if actor else "") or os.environ.get("GLOSSARY_STEWARD") or "steward"
    return a[:80]


def _load():
    try:
        with open(AUDIT_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(entries):
    tmp = AUDIT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, AUDIT_FILE)


def record(action, actor=None, detail=None, **fields):
    """Append one audit entry. `action` is a dotted verb (e.g. 'tag.approve',
    'dictionary.save'); extra keyword fields (names, warnings, counts…) are stored
    as-is when not None."""
    entry = {"ts": _now(), "actor": _clean_actor(actor), "action": action}
    if detail:
        entry["detail"] = detail
    for k, v in fields.items():
        if v is not None:
            entry[k] = v
    with _LOCK:
        entries = _load()
        entries.append(entry)
        if len(entries) > _CAP:
            entries = entries[-_CAP:]
        _save(entries)
    return entry


def recent(n=50):
    """Most-recent-first, capped at n."""
    try:
        n = max(1, min(int(n), 500))
    except Exception:
        n = 50
    return _load()[-n:][::-1]


def all_entries():
    return _load()


def summary():
    """Compact record for embedding in the Registry."""
    e = _load()
    return {"count": len(e),
            "last_action_at": (e[-1]["ts"] if e else None),
            "actors": sorted({x.get("actor", "") for x in e if x.get("actor")}),
            "recent": e[-15:][::-1]}
