"""
Similarity scoring for **suggested merges** — the layer PDC doesn't have.

PDC matches business terms by *identity* (a method's Assign-Business-Term binds one
term by id); it has no notion that "phone", "customer_phone" and "cust_phone_no" are
the same concept. That reconciliation has to happen upstream, in the authoring layer.

This module scores candidate term pairs across a few signals and returns them ranked,
so the steward can merge near-duplicates *before* they reach PDC and fragment the
catalog. It is deliberately a **proposer**: high-scoring pairs are surfaced, the
steward disposes. No embeddings and no third-party deps in this first pass — lexical,
token/abbreviation, and structural signals only. Data-shape (profiled value patterns)
is the strongest signal and is left as a hook for when profiling is present.
"""
from __future__ import annotations
import re

# common abbreviation → expansion, so cust_phone_no and customer_phone_number align
_ABBREV = {
    "no": "number", "num": "number", "nbr": "number", "qty": "quantity",
    "amt": "amount", "cust": "customer", "acct": "account", "addr": "address",
    "tel": "telephone", "ph": "phone", "dob": "dateofbirth", "ssn": "ssn",
    "id": "identifier", "desc": "description", "dt": "date", "ts": "timestamp",
    "pct": "percent", "bal": "balance", "txn": "transaction", "org": "organization",
    "dept": "department", "mgr": "manager", "emp": "employee", "svc": "service",
    "zip": "zipcode", "cd": "code", "qty_": "quantity", "fname": "firstname",
    "lname": "lastname", "dob_": "dateofbirth", "acc": "account",
}
_STOP = {"the", "a", "an", "of", "and", "or", "for"}

# blend weights (sum ~= 1). Lexical and token carry most; structural nudges.
_W = {"lexical": 0.40, "token": 0.40, "structural": 0.20}
DEFAULT_THRESHOLD = 0.60
HIGH_BAND = 0.85


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _tokens(s):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(s))           # split camelCase
    parts = re.split(r"[^A-Za-z0-9]+", s.lower())
    out = []
    for p in parts:
        if not p or p in _STOP:
            continue
        out.append(_ABBREV.get(p, p))
    return out


def _lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la:
        return lb
    if not lb:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if ai == b[j - 1] else 1))
        prev = cur
    return prev[lb]


def _lev_ratio(a, b):
    m = max(len(a), len(b))
    return 1.0 if not m else 1.0 - _lev(a, b) / m


def _jaccard(A, B):
    A, B = set(A), set(B)
    if not A and not B:
        return 0.0
    u = A | B
    return len(A & B) / len(u) if u else 0.0


def score_pair(a, b):
    """a, b: {name, category, sensitivity, pii, tags}. Returns {score, signals}."""
    na, nb = a.get("name", ""), b.get("name", "")

    lex = _lev_ratio(_norm(na), _norm(nb))

    ta, tb = _tokens(na), _tokens(nb)
    tok = _jaccard(ta, tb)
    sa, sb = set(ta), set(tb)
    if sa and sb and (sa <= sb or sb <= sa):        # one is a subset (phone ⊂ customer phone)
        tok = max(tok, 0.85)

    struct_parts = []
    if a.get("category") and b.get("category"):
        struct_parts.append(1.0 if a["category"] == b["category"] else 0.0)
    if a.get("pii") and b.get("pii"):
        struct_parts.append(1.0 if a["pii"] == b["pii"] else 0.0)
    if a.get("sensitivity") and b.get("sensitivity"):
        struct_parts.append(1.0 if a["sensitivity"] == b["sensitivity"] else 0.0)
    tagj = _jaccard(a.get("tags") or [], b.get("tags") or [])
    struct_parts.append(tagj)
    struct = sum(struct_parts) / len(struct_parts) if struct_parts else 0.0

    score = _W["lexical"] * lex + _W["token"] * tok + _W["structural"] * struct
    return {"score": round(score, 3),
            "signals": {"lexical": round(lex, 3), "token": round(tok, 3),
                        "structural": round(struct, 3), "tag_overlap": round(tagj, 3)}}


def suggest_merges(terms, threshold=DEFAULT_THRESHOLD, limit=50):
    """terms: [{name, category, sensitivity, pii, tags, count?}]. Returns ranked
    pairs above threshold, each with a canonical `keep` (higher usage, else shorter
    name) and the `drop` to merge into it, plus the contributing signals."""
    try:
        threshold = max(0.3, min(float(threshold), 0.95))
    except Exception:
        threshold = DEFAULT_THRESHOLD
    seen = {}
    for t in terms:
        nm = (t.get("name") or "").strip()
        if nm and nm not in seen:
            seen[nm] = t
    names = list(seen)
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = seen[names[i]], seen[names[j]]
            r = score_pair(a, b)
            if r["score"] < threshold:
                continue
            ca, cb = a.get("count", 0) or 0, b.get("count", 0) or 0
            if cb > ca or (cb == ca and len(names[j]) < len(names[i])):
                keep, drop, kd = names[j], names[i], (b, a)
            else:
                keep, drop, kd = names[i], names[j], (a, b)
            out.append({"keep": keep, "drop": drop, "score": r["score"],
                        "signals": r["signals"],
                        "band": "high" if r["score"] >= HIGH_BAND else "review",
                        "keep_count": kd[0].get("count", 0) or 0,
                        "drop_count": kd[1].get("count", 0) or 0})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]
