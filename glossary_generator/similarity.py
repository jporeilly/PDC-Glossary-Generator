"""
Similarity scoring for **suggested merges** — the layer PDC doesn't have.

PDC matches business terms by *identity* (a method's Assign-Business-Term binds one
term by id); it has no notion that "phone", "customer_phone" and "cust_phone_no" are
the same concept. That reconciliation has to happen upstream, in the authoring layer.

This module scores candidate term pairs across a few signals and returns them ranked,
so the steward can merge near-duplicates *before* they reach PDC and fragment the
catalog. It is deliberately a **proposer**: high-scoring pairs are surfaced, the
steward disposes. No embeddings and no third-party deps — lexical,
token/abbreviation, and structural signals, plus (since 1.8.3) the **data-shape
evidence** the scan carries on every row: induced value patterns/signatures,
profiled reference-value sets, PII class, and PK/FK links. That evidence also
powers `recommend_groups()` — the Merge / Disambiguate / Keep separate advisor
shown on same-named duplicate groups in the review grid.
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


# --------------------------------------------------------------------------- #
#  Data-shape evidence (the strongest signal): compare what the scan actually
#  profiled behind two terms, not just what they are called.
# --------------------------------------------------------------------------- #
def _row_evidence(r):
    """Comparable evidence off a review row (or a per-term evidence rollup)."""
    enums = {v.strip().upper() for v in str(r.get("Enum_Values") or "").split(";") if v.strip()}
    cols = [c.strip().lower() for c in str(r.get("Source_Column") or "").split(";") if c.strip()]
    refs = set()
    for k in (r.get("Source_Keys") or {}).values():
        if isinstance(k, dict) and k.get("ref"):
            refs.add(str(k["ref"]).strip().lower())
    return {"sig": (r.get("Value_Signature") or "").strip(),
            "pat": (r.get("Value_Pattern") or "").strip(),
            "enums": enums, "pii": (r.get("PII_Category") or "").strip(),
            "cols": cols, "refs": refs}


def _col_tails(cols):
    """'schema.table.column' -> 'table.column' (the form FK refs are recorded in)."""
    out = set()
    for c in cols:
        bits = c.split(".")
        if len(bits) >= 2:
            out.add(".".join(bits[-2:]))
    return out


def compare_evidence(row_a, row_b):
    """Verdict from profiled evidence: ('same' | 'different' | None, reason).
    Ordered strongest-first: an FK between the columns makes them the same concept
    by construction; profiled reference-value sets and induced formats come next;
    a PII-class mismatch is the weakest 'different' signal."""
    ea, eb = _row_evidence(row_a), _row_evidence(row_b)
    if (ea["refs"] & _col_tails(eb["cols"])) or (eb["refs"] & _col_tails(ea["cols"])):
        return "same", "a foreign key links the columns — one references the other, the same concept by construction"
    if ea["enums"] and eb["enums"]:
        j = _jaccard(ea["enums"], eb["enums"])
        if j >= 0.5:
            return "same", f"profiled value sets overlap ({int(round(j * 100))}%)"
        if j == 0:
            return "different", "profiled value sets are disjoint — same word, different code lists"
    if ea["pat"] and eb["pat"]:
        if ea["pat"] == eb["pat"]:
            return "same", f"identical induced value format {ea['pat']}"
        return "different", f"different value formats ({ea['pat']} vs {eb['pat']})"
    if ea["sig"] and eb["sig"]:
        if ea["sig"] == eb["sig"]:
            return "same", f"identical value signature {ea['sig']}"
        return "different", f"different value shapes ({ea['sig']} vs {eb['sig']})"
    if ea["pii"] and eb["pii"] and ea["pii"] != eb["pii"]:
        return "different", f"different PII classes ({ea['pii']} vs {eb['pii']})"
    return None, ""


def compare_value_sets(vals_a, vals_b):
    """Verdict from LIVE sampled column values — the direct form of the evidence
    (compares actual populations, not cached shapes). Containment beats Jaccard
    here: an FK-style relationship keeps the smaller set inside the bigger one.
    Returns ('same' | 'different' | None, reason)."""
    A = {str(v).strip().upper() for v in (vals_a or []) if str(v).strip()}
    B = {str(v).strip().upper() for v in (vals_b or []) if str(v).strip()}
    if not A or not B:
        return None, ""
    inter = len(A & B)
    contain = inter / min(len(A), len(B))
    if contain >= 0.6:
        return "same", f"live data probe: {int(round(contain * 100))}% of the smaller column's values appear in the other"
    if inter == 0:
        return "different", "live data probe: the columns share NO values — same word, different populations"
    return None, ""


def group_rows(rows):
    """Kept rows grouped by their (duplicate) term name: {name: [rows]}, only
    names with 2+ members. The grid's duplicate clusters, server-side."""
    by = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("Keep", "Y")).strip().lower() not in ("y", "yes", "true", "1"):
            continue
        nm = (r.get("Term") or "").strip()
        if nm:
            by.setdefault(nm, []).append(r)
    return {nm: ms for nm, ms in by.items() if len(ms) >= 2}


def recommend_resolution(members, probes=None):
    """One Merge / Disambiguate / Keep separate recommendation for a group of rows
    sharing a term name. Rubric (evidence beats context, context beats nothing):
      - any pair evidence-SAME, none DIFFERENT      -> merge (high)
      - any pair evidence-DIFFERENT:
          mixed with SAME pairs                     -> split (review; outlier present)
          all in one category                       -> split (import collides there)
          across categories                         -> separate (PDC holds both)
      - no evidence: matching context (category or
        PII class agree)                            -> merge (review)
        otherwise                                   -> no call (review manually)
    Returns {action: 'merge'|'split'|'separate'|None, band: 'high'|'review', reason}."""
    sames, diffs = [], []
    for v, why in (probes or []):
        (sames if v == "same" else diffs).append(why)
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            v, why = compare_evidence(members[i], members[j])
            if v == "same":
                sames.append(why)
            elif v == "different":
                diffs.append(why)
    cats = {(m.get("Category") or "").strip() for m in members}
    if diffs and sames:
        return {"action": "split", "band": "review",
                "reason": "mixed evidence — some columns match shapes, others don't: "
                          + diffs[0] + ". Disambiguate the outlier, then merge the rest"}
    if diffs:
        if len(cats) <= 1:
            return {"action": "split", "band": "high",
                    "reason": diffs[0] + " — and they share a category, where duplicate names collide on import"}
        return {"action": "separate", "band": "high",
                "reason": diffs[0] + " — categories differ, so PDC can hold both as distinct terms"}
    if sames:
        return {"action": "merge", "band": "high", "reason": sames[0]}
    piis = {(m.get("PII_Category") or "").strip() for m in members} - {""}
    if len(cats) <= 1 or len(piis) <= 1:
        return {"action": "merge", "band": "review",
                "reason": "no profiled evidence, but identical name and matching context — likely one concept (check the definitions)"}
    return {"action": None, "band": "review",
            "reason": "no profiled evidence to compare — review the definitions manually"}


def recommend_groups(rows):
    """Evidence-grounded recommendations for every same-named duplicate group in a
    set of review rows. Returns [{name, count, action, band, reason}]."""
    out = []
    for nm, members in group_rows(rows).items():
        rec = recommend_resolution(members)
        rec.update(name=nm, count=len(members))
        out.append(rec)
    out.sort(key=lambda x: (x["band"] != "high", -x["count"]))
    return out


def score_pair(a, b):
    """a, b: {name, category, sensitivity, pii, tags, evidence_row?}. Returns
    {score, signals, evidence, evidence_reason} — evidence is 'same'/'different'/None
    from the profiled data behind each term (when the caller supplies it)."""
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

    # data-shape evidence outranks name similarity: an FK link or a shared induced
    # format lifts the pair to the high band; conflicting shapes flag a false friend
    ev, ev_reason = (None, "")
    ra, rb = a.get("evidence_row"), b.get("evidence_row")
    if isinstance(ra, dict) and isinstance(rb, dict):
        ev, ev_reason = compare_evidence(ra, rb)
        if ev == "same":
            score = max(score, HIGH_BAND)
    return {"score": round(score, 3),
            "signals": {"lexical": round(lex, 3), "token": round(tok, 3),
                        "structural": round(struct, 3), "tag_overlap": round(tagj, 3)},
            "evidence": ev, "evidence_reason": ev_reason}


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
            # a shape conflict means the look-alike names hide DIFFERENT concepts —
            # surface it as a warning instead of a merge proposal
            band = ("conflict" if r.get("evidence") == "different"
                    else "high" if r["score"] >= HIGH_BAND else "review")
            out.append({"keep": keep, "drop": drop, "score": r["score"],
                        "signals": r["signals"], "band": band,
                        "evidence": r.get("evidence"),
                        "evidence_reason": r.get("evidence_reason", ""),
                        "keep_count": kd[0].get("count", 0) or 0,
                        "drop_count": kd[1].get("count", 0) or 0})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]
