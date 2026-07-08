#!/usr/bin/env python3
"""
Glossary Suggester  -  end-to-end prototype
=================================================
Scans a relational source, SUGGESTS a business glossary, writes a reviewable
CSV for a steward to approve, then converts the approved rows to import-ready
PDC glossary JSONL.

Pipeline (mirrors the architecture we discussed):
  1. HARVEST   - read schema: tables, columns, types, keys, inline comments.
                 (Demo parses the DDL file. A live run would query
                  information_schema over psycopg2 - see harvest_live().)
  2. SUGGEST   - turn columns into candidate terms: name, definition,
                 category, sensitivity/PII, CDE flag, abbreviation, tags.
  3. REVIEW    - write suggested_glossary.csv with Confidence + Reason +
                 a Keep column. Nothing is auto-published; a steward edits this.
  4. GENERATE  - read back the kept rows and emit Suggested-Glossary.jsonl
                 (glossary + categories + terms) ready for Actions -> Import.

Suggested terms are written with status "Draft" on purpose: they are proposals,
not approved governance, until a Business Steward signs off.
"""

import re, csv, json, uuid, sys, datetime

DDL      = "/mnt/user-data/uploads/01-schema-and-data.sql"
REVIEW   = "/mnt/user-data/outputs/suggested_glossary.csv"
JSONL    = "/mnt/user-data/outputs/Suggested-Glossary.jsonl"
GLOSSARY = "Business Glossary (Suggested)"
DOMAIN   = "General"
GEN_TS   = "2026-06-18T12:00:00.000Z"
NS       = uuid.uuid5(uuid.NAMESPACE_DNS, "suggested-glossary")  # deterministic ids

# ---------------------------------------------------------------- 1. HARVEST
def harvest_ddl(path):
    """Parse CREATE TABLE blocks from a DDL file into {table: [columns...]}."""
    sql = open(path, encoding="utf-8").read()
    tables = {}
    for m in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\n\)\s*;", sql, re.S | re.I):
        tname, body = m.group(1), m.group(2)
        cols = []
        for raw in body.split("\n"):
            line = raw.strip().rstrip(",")
            if not line:
                continue
            # split off an inline "-- comment"
            comment = ""
            if "--" in line:
                line, comment = line.split("--", 1)
                line, comment = line.strip().rstrip(","), comment.strip()
            parts = line.split()
            if len(parts) < 2:
                continue
            col = parts[0]
            # skip table-level constraint lines
            if col.upper() in {"PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK", "REFERENCES"}:
                continue
            dtype = parts[1]
            up = line.upper()
            cols.append({
                "table": tname, "column": col, "type": dtype,
                "pk": "PRIMARY KEY" in up,
                "fk": "REFERENCES" in up,
                "notnull": "NOT NULL" in up,
                "unique": "UNIQUE" in up,
                "comment": comment,
            })
        if cols:
            tables[tname] = cols
    return tables

def harvest_live(dsn):
    """Reference implementation for a live PostgreSQL source (not run in demo).
       import psycopg2; SELECT table_name, column_name, data_type ...
       FROM information_schema.columns WHERE table_schema=%s ORDER BY ordinal_position;
       plus key_column_usage / table_constraints for PK/FK. Returns same shape."""
    raise NotImplementedError("Demo uses harvest_ddl(); wire psycopg2 here for live scans.")

# ---------------------------------------------------------------- 2. SUGGEST
# Map each physical table to a business category (this is the one place a
# human's domain knowledge seeds the structure; everything else is derived).
TABLE_CATEGORY = {
    "customers":             "Customer",
        "tiered_rates":          "Billing & Rates",
    "monthly_usage":         "Usage",
        "account_alerts":        "Governance",
}

# PII / sensitivity heuristics on the column name (seeded from PDC's PII categories).
# Order matters: first match wins, so put specific rules before generic ones.
# Each rule: (match_pattern, exclude_pattern_or_None, pii_category, sensitivity, tags)
PII_RULES = [
    (r"account_number|acct",        None,                       "FINANCIAL",     "HIGH",   ["PII", "Financial"]),
    (r"email|e_mail",               None,                       "CONTACT_INFO",  "MEDIUM", ["PII"]),
    (r"phone|mobile|telephone",     None,                       "CONTACT_INFO",  "MEDIUM", ["PII"]),
    # "name" is PII only for people - exclude system/report/file/plan/type names
    (r"name",                       r"system|report|file|plan|type|source", "PERSONAL_NAME", "MEDIUM", ["PII"]),
    (r"address|street",             None,                       "ADDRESS_INFO",  "MEDIUM", ["PII"]),
    (r"city|county|zip|postal",     None,                       "ADDRESS_INFO",  "LOW",    []),
    # money columns only - not "rate_period" or "billing_city"
    (r"amount|charge|tax|due|paid|balance", None,               "FINANCIAL",     "LOW",    ["Financial"]),
]

# Acronym helpers for abbreviation suggestions.
ABBREV = {"number": "No.", "identifier": "ID", "amount": "Amt", "account": "Acct",
          "address": "Addr", "quantity": "Qty", "percentage": "Pct"}

def humanize(col):
    """account_number -> Account Number ; total_due -> Total Due ; pH_level -> Ph Level"""
    s = re.sub(r"[_]+", " ", col).strip()
    s = re.sub(r"\s+", " ", s)
    return " ".join(w.capitalize() if not w.isupper() else w for w in s.split())

def suggest_abbrev(name):
    words = name.lower().split()
    for w in words:
        if w in ABBREV:
            return ABBREV[w]
    return ""

def classify(col):
    """Return (pii_category, sensitivity, tags) from the column name."""
    cl = col.lower()
    for pat, excl, cat, sens, tags in PII_RULES:
        if re.search(pat, cl) and not (excl and re.search(excl, cl)):
            return cat, sens, list(tags)
    return None, "LOW", []

def define(c):
    """Definition: prefer the DDL comment; otherwise template from name+table."""
    human_tbl = humanize(c["table"]).rstrip("s")
    name = humanize(c["column"])
    if c["comment"]:
        # comment may be an enumeration ("Active, Suspended, Closed") or prose
        if "," in c["comment"] and len(c["comment"].split(",")) >= 2 and len(c["comment"]) < 90:
            return f"{name} for a {human_tbl.lower()} record. Valid values: {c['comment']}."
        return c["comment"].rstrip(".") + "."
    if c["pk"]:
        return f"Unique identifier for a {human_tbl.lower()} record."
    if c["fk"]:
        ref = humanize(c["column"]).replace(" Id", "").strip()
        return f"Reference linking this record to its related {ref.lower()}."
    return f"{name} associated with a {human_tbl.lower()} record."

# Columns we skip as terms (pure technical plumbing with no business meaning).
SKIP = re.compile(r"^(last_updated|created_date|created_at|updated_at)$", re.I)

def suggest(tables):
    rows = []
    for tname, cols in tables.items():
        category = TABLE_CATEGORY.get(tname, "Uncategorized")
        for c in cols:
            if SKIP.match(c["column"]):
                continue
            name = humanize(c["column"])
            pii, sens, tags = classify(c["column"])
            cde = bool(c["pk"] or c["unique"] or sens == "HIGH")
            # confidence: high when we had a DDL comment or a key; lower when templated
            if c["comment"]:
                conf, reason = "High", "DDL comment used for definition"
            elif c["pk"] or c["fk"]:
                conf, reason = "High", "Key column - identity/relationship"
            elif pii:
                conf, reason = "Medium", f"Name matched {pii} pattern"
            else:
                conf, reason = "Low", "Templated from column name"
            rows.append({
                "Keep": "Y",
                "Category": category,
                "Term": name,
                "Source_Column": f"public.{tname}.{c['column']}",
                "Definition": define(c),
                "Sensitivity": sens,
                "PII_Category": pii or "",
                "Critical_Data_Element": "Yes" if cde else "No",
                "Abbreviation": suggest_abbrev(name),
                "Suggested_Tags": ";".join(tags),
                "Status": "Draft",
                "Confidence": conf,
                "Suggested_Reason": reason,
            })
    # de-duplicate identical term names within the same category (e.g. base_charge
    # appears in two tables) - keep the first, note the extra source on it.
    seen = {}
    deduped = []
    for r in rows:
        key = (r["Category"], r["Term"])
        if key in seen:
            seen[key]["Source_Column"] += "; " + r["Source_Column"]
            continue
        seen[key] = r
        deduped.append(r)
    return deduped

# ---------------------------------------------------------------- 3. REVIEW
REVIEW_COLS = ["Keep", "Category", "Term", "Source_Column", "Definition",
               "Sensitivity", "PII_Category", "Critical_Data_Element",
               "Abbreviation", "Suggested_Tags", "Status",
               "Confidence", "Suggested_Reason"]

def write_review(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLS)
        w.writeheader()
        w.writerows(rows)

# ---------------------------------------------------------------- 4. GENERATE
def lex(text):
    """PDC Lexical rich-text format (a JSON string), matching the import schema."""
    if not text:
        return None
    obj = {"root": {"children": [{"children": [{"detail": 0, "format": 0, "mode": "normal",
            "style": "", "text": str(text), "type": "text", "version": 1}],
            "direction": "ltr", "format": "", "indent": 0, "type": "paragraph", "version": 1}],
            "direction": "ltr", "format": "", "indent": 0, "type": "root", "version": 1}}
    return json.dumps(obj, ensure_ascii=False)

def to_jsonl(rows, path):
    root = str(uuid.uuid5(NS, "glossary:" + GLOSSARY))
    recs = []
    # glossary object
    recs.append({"createdAt": GEN_TS, "fqdn": GLOSSARY, "rootId": root,
                 "createdBy": "suggester", "name": GLOSSARY,
                 "attributes": {"isSoftCreated": False, "info": {"status": "Draft"}},
                 "type": "glossary", "updatedAt": GEN_TS,
                 "resourceId": "null", "_id": root, "sort": None})
    # categories (unique, in first-seen order)
    cats = []
    for r in rows:
        if r["Category"] not in cats:
            cats.append(r["Category"])
    cat_id = {}
    for cat in cats:
        cid = str(uuid.uuid5(NS, "category:" + cat))
        cat_id[cat] = cid
        recs.append({"createdAt": GEN_TS, "updatedBy": "suggester",
                     "fqdn": f"{GLOSSARY}/{cat}", "rootId": root, "createdBy": "suggester",
                     "name": cat, "attributes": {"isSoftCreated": False,
                     "info": {"domain": DOMAIN, "status": "Draft"}},
                     "type": "category", "parentId": root, "updatedAt": GEN_TS,
                     "resourceId": "null", "_id": cid, "sort": None})
    # terms
    for r in rows:
        if r["Keep"].strip().lower() not in ("y", "yes", "true", "1"):
            continue
        cat = r["Category"]
        tid = str(uuid.uuid5(NS, f"term:{cat}/{r['Term']}"))
        features = {"sensitivity": r["Sensitivity"],
                    "isCriticalDataElement": r["Critical_Data_Element"].strip().lower() == "yes"}
        info = {"domain": DOMAIN, "definition": lex(r["Definition"]),
                "classification": "Company Confidential" if r["Sensitivity"] == "HIGH" else "Private"
                if r["Sensitivity"] == "MEDIUM" else "Public",
                "status": "Draft",
                "purpose": lex(f"Suggested from {r['Source_Column']}.")}
        if r["Abbreviation"]:
            info["abbreviation"] = r["Abbreviation"]
        attrs = {"features": features, "isSoftCreated": False, "info": info}
        if r["Suggested_Tags"]:
            attrs["tags"] = [{"name": t} for t in r["Suggested_Tags"].split(";") if t]
        recs.append({"createdAt": GEN_TS, "updatedBy": "suggester",
                     "fqdn": f"{GLOSSARY}/{cat}/{r['Term']}", "rootId": root,
                     "createdBy": "suggester", "name": r["Term"], "attributes": attrs,
                     "type": "term", "parentId": cat_id[cat], "updatedAt": GEN_TS,
                     "resourceId": "null", "_id": tid, "sort": None})
    with open(path, "w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(cats), sum(1 for r in recs if r["type"] == "term")

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    tables = harvest_ddl(DDL)
    print(f"[1] HARVEST  : {len(tables)} tables, "
          f"{sum(len(c) for c in tables.values())} columns")
    rows = suggest(tables)
    print(f"[2] SUGGEST  : {len(rows)} candidate terms across "
          f"{len({r['Category'] for r in rows})} categories")
    write_review(rows, REVIEW)
    print(f"[3] REVIEW   : wrote {REVIEW}")
    ncat, nterm = to_jsonl(rows, JSONL)
    print(f"[4] GENERATE : {nterm} kept terms + {ncat} categories -> {JSONL}")
    # quick confidence + sensitivity summary
    from collections import Counter
    print("    confidence :", dict(Counter(r["Confidence"] for r in rows)))
    print("    sensitivity:", dict(Counter(r["Sensitivity"] for r in rows)))
    print("    PII flagged:", sum(1 for r in rows if r["PII_Category"]))
