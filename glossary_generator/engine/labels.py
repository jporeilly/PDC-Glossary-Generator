"""Label suggestions — PDC labels are key/value custom properties on an item,
capped at a handful of values plus a default, so they suit small governable
sets rather than free text.

Every suggestion here is DERIVED from what the scan already proved (PII,
sensitivity, CDE, the settled category, the document's class) — labels read
classification, they never change it. Nothing is applied: the steward picks
which label keys to keep, exactly like every other proposal in this app, and
the choice rides the domain pack so the next scan proposes the same thing.

Retention deliberately has NO built-in values: how long a compliance record
must be kept is a customer's regulatory fact, not something this engine may
invent. Define a retention vocabulary in the domain pack (labels.retention:
{compliance: "7y", correspondence: "3y", …}) and the suggestion appears,
matched on the document's own folder/class words.
"""
from __future__ import annotations
import re

# The keys this engine can derive without inventing anything. Each carries the
# evidence it reads and a one-line rationale the steward sees.
_TRUTHY = ("y", "yes", "true", "1")

# per-value descriptions, shipped into PDC's availableValues so the label
# reads like the steward wrote it (the PII Type wording IS the steward's)
_VALUE_DESCRIPTIONS = {
    "PII Type": {
        "Restricted": "serious harm if exposed: government ID, financial, full identity sets",
        "Confidential": "identifies a person on its own: name, email, phone, address, account",
        "Internal": "quasi-identifiers that only identify in combination: ZIP, city, county, meter ID",
    },
}


def _kept(r):
    return str(r.get("Keep", "Y")).strip().lower() in _TRUTHY


def _doc_class(row):
    """The class word of a document-derived term: its top folder ('compliance',
    'inspections', 'scada'). Empty for database columns."""
    src = str(row.get("Source_Column") or "").split(";")[0].strip()
    if "/" not in src:
        return ""
    head, _, rest = src.partition(".")
    path = rest if ("." in src.split("/")[0]) else src
    seg = path.split("/")
    return (seg[1] if len(seg) > 1 and "." in seg[0] else seg[0]).strip().lower()


def suggest_labels(rows, pack=None):
    """rows -> {keys: [...], vocabulary: {...}, notes: [...]}.

    Each key entry: {key, why, values: [{value, terms: [...], count}], source}.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict) and _kept(r)]
    pack_labels = ((pack or {}).get("labels") or {}) if isinstance(pack, dict) else {}
    out, notes = [], []

    def bucket(key, why, source, assign):
        """assign(row) -> value or '' ; collapses to value -> [terms]."""
        vals = {}
        for r in rows:
            term = str(r.get("Term") or "").strip()
            if not term:
                continue
            v = (assign(r) or "").strip()
            if not v:
                continue
            vals.setdefault(v, [])
            if term not in vals[v]:
                vals[v].append(term)
        if not vals:
            return
        # PDC caps a label at a handful of values (+ a default), so a key that
        # explodes into dozens is not a label — it is a field.
        if len(vals) > 6:
            notes.append(f"{key}: {len(vals)} distinct values — too many for a PDC "
                         "label (max ~6 + default); narrow the vocabulary or drop it")
            return
        out.append({
            "key": key, "why": why, "source": source,
            "descriptions": _VALUE_DESCRIPTIONS.get(key, {}),
            "values": sorted(({"value": v, "count": len(t), "terms": sorted(t)[:12]}
                              for v, t in vals.items()),
                             key=lambda x: -x["count"]),
        })

    # PII Type — three tiers from the deterministic PII call, matching the
    # taxonomy the steward modelled in PDC's own Create Custom Property form
    # (field-adopted 2026-08-14): Restricted = serious harm if exposed,
    # Confidential = identifies a person on its own, Internal =
    # quasi-identifiers that only identify in combination.
    _PII_TIER = {"GOVERNMENT_ID": "Restricted", "FINANCIAL": "Restricted",
                 "PERSONAL_NAME": "Confidential", "CONTACT_INFO": "Confidential",
                 "ADDRESS_INFO": "Internal", "DEMOGRAPHIC": "Internal"}
    bucket("PII Type",
           "PII class from the scan, tiered by exposure harm",
           "evidence",
           lambda r: _PII_TIER.get(str(r.get("PII_Category") or "").strip().upper(), ""))

    # access-tier — from sensitivity
    tier = {"HIGH": "tier-1", "MEDIUM": "tier-2", "LOW": "tier-3"}
    bucket("access-tier", "sensitivity the scan assigned", "evidence",
           lambda r: tier.get(str(r.get("Sensitivity") or "").upper(), ""))

    # criticality — from the CDE flag
    bucket("criticality", "Critical Data Element flag", "evidence",
           lambda r: "critical" if str(r.get("Critical_Data_Element") or "").lower() == "yes" else "")

    # domain — the settled category (the keystone's own vocabulary)
    bucket("domain", "the approved category — the taxonomy this review settled",
           "evidence", lambda r: str(r.get("Category") or "").strip())

    # retention — ONLY from a pack-defined vocabulary; never invented here
    ret = pack_labels.get("retention") if isinstance(pack_labels.get("retention"), dict) else None
    if ret:
        low = {str(k).strip().lower(): str(v).strip() for k, v in ret.items() if str(v).strip()}
        def _ret(r):
            cls = _doc_class(r)
            if cls and cls in low:
                return low[cls]
            hay = f"{r.get('Term','')} {r.get('Source_Column','')}".lower()
            for k, v in low.items():
                if k and re.search(rf"\b{re.escape(k)}", hay):
                    return v
            return low.get("default", "")
        bucket("retention",
               "document class matched against the retention vocabulary in your domain pack",
               "pack", _ret)
    else:
        notes.append("retention: define labels.retention in the domain pack "
                     "(e.g. {\"compliance\": \"7y\", \"correspondence\": \"3y\"}) — "
                     "retention periods are a regulatory fact for your organisation, "
                     "so this engine will not invent them")

    # anything else the pack defines as a straight term->value map
    for key, spec in pack_labels.items():
        if key == "retention" or not isinstance(spec, dict):
            continue
        low = {str(k).strip().lower(): str(v).strip() for k, v in spec.items()}
        bucket(key, "matched from your domain pack's label vocabulary", "pack",
               lambda r, _l=low: _l.get(str(r.get("Term", "")).strip().lower(), ""))

    return {"keys": out, "notes": notes,
            "vocabulary": {k["key"]: [v["value"] for v in k["values"]] for k in out}}


def labels_for_row(row, keys, pack=None):
    """The {key: value} a single row would carry for the ENABLED keys — used at
    export/apply time so the written labels always match the current grid."""
    got = suggest_labels([row], pack=pack)
    want = {str(k).strip() for k in (keys or [])}
    out = {}
    for entry in got["keys"]:
        if entry["key"] in want and entry["values"]:
            out[entry["key"]] = entry["values"][0]["value"]
    return out
