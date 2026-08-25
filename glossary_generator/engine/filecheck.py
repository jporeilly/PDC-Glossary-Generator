"""
Uploaded-file checking (walk-log W21): "it would be great to be able to
upload documents to the chat. lets say i want to check my JSONL for errors."

Validates a PDC glossary-import JSONL against the contract this app's own
Generate writes (engine/sug_generate.py) — per-line parse, record shape, id
integrity, tree integrity, the field-caught traps ('&' names kill PDC search;
uppercase tags never match the governed vocabulary) — and REPAIRS what is
mechanical: BOM, blank lines, tag casing, fqdn drift, resourceId shape.
Anything touching identity (_ids, names) is reported, never rewritten — the
deterministic ids derive from the names, so a "repair" there would silently
re-key the glossary.

Deterministic throughout: no model involved. The docs chat hands the findings
to its composer as context, so questions ABOUT the file stay grounded.
"""
from __future__ import annotations
import json

REQUIRED_KEYS = ("_id", "type", "name", "fqdn", "rootId")
RECORD_TYPES = {"glossary", "category", "term"}
SENSITIVITIES = {"HIGH", "MEDIUM", "LOW"}
MAX_BYTES = 15 * 1024 * 1024


def check_glossary_jsonl(text, name="upload.jsonl"):
    """Validate (and mechanically repair) one glossary-import JSONL.

    Returns {findings: [{line, severity, code, message}], counts, repaired,
    repaired_lines, summary}. `repaired` is the full corrected JSONL text —
    present only when at least one mechanical repair applied."""
    findings = []
    counts = {"glossary": 0, "category": 0, "term": 0}
    repaired_any = False

    def flag(line, severity, code, message):
        findings.append({"line": line, "severity": severity,
                         "code": code, "message": message})

    if len(text.encode("utf-8", "ignore")) > MAX_BYTES:
        flag(0, "error", "too-large", "file exceeds 15 MB — not a glossary export")
        return {"findings": findings, "counts": counts, "repaired": None,
                "summary": _summary(name, findings, counts, False)}

    if text.startswith("﻿"):
        text = text.lstrip("﻿")
        flag(1, "repaired", "bom", "UTF-8 BOM stripped — PDC's importer reads "
             "the first record as malformed JSON with it in place")
        repaired_any = True

    records, out_lines = [], []
    for i, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            flag(i, "repaired", "blank-line", "blank line dropped — the importer "
                 "treats every line as one record")
            repaired_any = True
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as e:
            flag(i, "error", "parse", f"not valid JSON ({e.msg} at column {e.colno}) "
                 "— the importer stops at the first malformed line")
            out_lines.append(raw)
            continue
        if not isinstance(rec, dict):
            flag(i, "error", "shape", "line is valid JSON but not an object")
            out_lines.append(raw)
            continue
        records.append((i, rec))
        out_lines.append(rec)          # dict → re-serialised after repairs

    # ---- record-level shape -------------------------------------------------
    ids, roots = {}, set()
    glossary_rec = None
    cat_ids, term_recs = {}, []
    for i, rec in records:
        for k in REQUIRED_KEYS:
            if not str(rec.get(k) or "").strip():
                flag(i, "error", "missing-key", f'required key "{k}" is missing or empty')
        rtype = str(rec.get("type") or "")
        if rtype not in RECORD_TYPES:
            flag(i, "error", "type", f'unknown record type "{rtype}" — expected '
                 "glossary, category or term")
            continue
        counts[rtype] += 1
        rid = str(rec.get("_id") or "")
        if rid:
            if rid in ids:
                flag(i, "error", "duplicate-id",
                     f"_id {rid} already used on line {ids[rid]} — the importer "
                     "keeps one record and silently drops the other")
            else:
                ids[rid] = i
        if rec.get("rootId"):
            roots.add(str(rec["rootId"]))
        if rtype == "glossary":
            if glossary_rec:
                flag(i, "error", "extra-glossary", "second glossary record — an "
                     "import file carries exactly one")
            else:
                glossary_rec = (i, rec)
        elif rtype == "category":
            cat_ids[rid] = (i, rec)
        else:
            term_recs.append((i, rec))

        # mechanical: resourceId is the literal string "null" in every export
        if "resourceId" in rec and rec["resourceId"] != "null":
            rec["resourceId"] = "null"
            flag(i, "repaired", "resource-id", 'resourceId normalised to the '
                 'literal string "null" (the contract PDC\'s importer expects)')
            repaired_any = True

        # the PDC search killer — report, never rewrite: the deterministic ids
        # derive from the names, so renaming here would re-key the glossary
        if "&" in str(rec.get("name") or ""):
            flag(i, "warn", "ampersand", f'"{rec.get("name")}" contains "&" — PDC '
                 'name search returns NOTHING for such names (field-proven). '
                 'Rename to "and" in the Review grid and regenerate; a text-side '
                 "rename here would break the deterministic ids")

        # tags must be lowercase to meet the governed vocabulary
        tags = (rec.get("attributes") or {}).get("tags")
        if isinstance(tags, list):
            for t in tags:
                nm = (t or {}).get("name")
                if isinstance(nm, str) and nm != nm.lower():
                    t["name"] = nm.lower()
                    flag(i, "repaired", "tag-case", f'tag "{nm}" lowercased — '
                         "governed tags are lowercase and PDC matches exactly")
                    repaired_any = True

        info = ((rec.get("attributes") or {}).get("features") or {})
        sens = info.get("sensitivity")
        if sens is not None and sens not in SENSITIVITIES:
            flag(i, "warn", "sensitivity", f'sensitivity "{sens}" is not '
                 "HIGH/MEDIUM/LOW — PDC stores it but nothing downstream "
                 "recognises it")

    # ---- tree integrity -----------------------------------------------------
    if not glossary_rec and records:
        flag(0, "error", "no-glossary", "no glossary record — the importer has "
             "no root to attach categories to")
    if len(roots) > 1:
        flag(0, "error", "root-drift", f"{len(roots)} different rootId values — "
             "every record must point at the one glossary root")
    gname = str(glossary_rec[1].get("name") or "") if glossary_rec else ""
    if glossary_rec:
        gi, grec = glossary_rec
        if str(grec.get("_id") or "") != str(grec.get("rootId") or ""):
            flag(gi, "error", "root-id", "the glossary record's _id and rootId "
                 "disagree — they are the same id by contract")

    for i, rec in term_recs:
        pid = str(rec.get("parentId") or "")
        if pid and pid not in cat_ids:
            flag(i, "error", "orphan-term", f'term "{rec.get("name")}" points at '
                 "a parent category that is not in this file — it imports "
                 "nowhere visible")
        if not str(((rec.get("attributes") or {}).get("info") or {})
                   .get("definition") or "").strip():
            flag(i, "warn", "no-definition", f'term "{rec.get("name")}" has no '
                 "definition — it imports, but a glossary of empty terms is "
                 "the thing a glossary exists to prevent")
        # fqdn drift is mechanical: rebuild from the actual names
        if gname and pid in cat_ids:
            want = f"{gname}/{cat_ids[pid][1].get('name')}/{rec.get('name')}"
            if str(rec.get("fqdn") or "") != want:
                rec["fqdn"] = want
                flag(i, "repaired", "fqdn", f"fqdn rebuilt to {want} — it drifted "
                     "from the glossary/category/term path the names spell")
                repaired_any = True
    for cid, (i, rec) in cat_ids.items():
        if gname:
            want = f"{gname}/{rec.get('name')}"
            if str(rec.get("fqdn") or "") != want:
                rec["fqdn"] = want
                flag(i, "repaired", "fqdn", f"fqdn rebuilt to {want}")
                repaired_any = True
        if glossary_rec and str(rec.get("parentId") or "") != str(glossary_rec[1].get("_id")):
            flag(i, "error", "orphan-category", f'category "{rec.get("name")}" '
                 "does not point at the glossary record as its parent")

    repaired = None
    if repaired_any:
        repaired = "\n".join(
            json.dumps(l, ensure_ascii=False) if isinstance(l, dict) else l
            for l in out_lines) + "\n"

    findings.sort(key=lambda f: (f["line"], f["severity"]))
    return {"findings": findings, "counts": counts, "repaired": repaired,
            "summary": _summary(name, findings, counts, repaired_any)}


def _summary(name, findings, counts, repaired_any):
    e = sum(1 for f in findings if f["severity"] == "error")
    w = sum(1 for f in findings if f["severity"] == "warn")
    r = sum(1 for f in findings if f["severity"] == "repaired")
    verdict = ("IMPORTABLE as-is" if not e and not r
               else "IMPORTABLE after the repairs below" if not e
               else "NOT importable — fix the errors first")
    return (f"{name}: {counts['glossary']} glossary / {counts['category']} "
            f"categories / {counts['term']} terms · {e} error(s), {w} warning(s), "
            f"{r} repaired · {verdict}")


def findings_as_context(name, result, limit=25):
    """Render a check result as a docs-chat excerpt, so questions about the
    uploaded file stay inside the grounded-or-refuse contract."""
    lines = [result["summary"]]
    for f in result["findings"][:limit]:
        where = f"line {f['line']}" if f["line"] else "file"
        lines.append(f"- [{f['severity']}] {where}: {f['message']}")
    if len(result["findings"]) > limit:
        lines.append(f"- ... and {len(result['findings']) - limit} more")
    return f"[YOUR FILE - {name}]\n" + "\n".join(lines)
