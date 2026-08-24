"""Term suggestion - naming, categorising, classify/define/tags/ratings,
quality scoring, detection intent, and suggest() itself.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS

# ----------------------------------------------------------------- SUGGEST
def _load_domain_pack():
    """Optionally load scenario vocabulary so the engine stays generic. Looks at
       $GLOSSARY_DOMAIN_PACK, else domain_pack.json beside this module. Returns {}
       when absent. Recognised keys: table_category, table_terms, cat_keywords,
       abbreviations, category_definitions. See domain_packs/*.example.json."""
    path = paths.domain_pack_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_PACK = _load_domain_pack()

# Physical table -> business category. Empty by default (table names are
# scenario-specific); populate via a domain pack for your schema.
TABLE_CATEGORY = dict(_PACK.get("table_category", {}))

# Table-level glossary terms — the ONE term per physical table that feeds the
# table's Trust Score "glossary term assigned" input. Columns carry their own
# terms (linked to the column); the TABLE needs a term on the table entity itself,
# because PDC reads the table's own businessTerms[] for that input. Curated names
# come from the domain pack (if any); otherwise a name is derived per table.
TABLE_TERMS = dict(_PACK.get("table_terms", {}))

# Singular nouns that already end in "s". Stripping the last letter turns a
# real word into a non-word, and the result is not cosmetic: it becomes the
# TERM NAME, it is stored in the domain pack, and it reaches PDC. Field-caught
# on the AWC estate — `system_water_quality_status` shipped a table term called
# "System Water Quality Statu Record", baked into the pack and imported into
# the customer-facing glossary. The -us / -is families cover most of it
# (status, census, bonus, radius, analysis, basis, axis, diagnosis); the rest
# are irregulars with no rule behind them.
_KEEPS_ITS_S = ("us", "is", "ss", "as", "os")
_SINGULAR_S = {"news", "series", "species", "means", "lens", "alias", "atlas"}


def _singularize(word):
    w = (word or "")
    low = w.lower()
    # the irregulars go FIRST: "series" would otherwise be caught by the -ies
    # rule and come back "sery"
    if low in _SINGULAR_S or low.rsplit("_", 1)[-1] in _SINGULAR_S:
        return w
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith("ses") and len(w) > 3:   # statuses -> status, addresses -> address
        return w[:-2]
    if low.endswith(_KEEPS_ITS_S):
        return w
    if w.endswith("s"):
        return w[:-1]
    return w

# A document store's "table" is a FILE, so its name carries two things a term
# must not: the extension, and — on an exported snapshot — the date it was cut.
#   pinal_valley_pressure_2026-05-14.json -> "Pinal Valley Pressure Record"
# Leaving the date in mints a NEW term for every daily export, so the glossary
# accretes one term per file per day and nothing ever merges: precisely the drift
# the Registry exists to prevent. The date belongs to the extract, not the concept.
_FILE_EXT = re.compile(r"\.(csv|tsv|psv|json|jsonl|xml|txt|parquet|avro|ya?ml|"
                       r"pdf|docx?|xlsx?|pptx?)$", re.I)
# A period stamp in any of the shapes an export uses: 2026-05-14, 202605,
# 2026Q1, 2026_H2. All of them name WHEN the extract was cut, not what it is.
_DATE_SUFFIX = re.compile(
    r"[._-]?(?:19|20)\d{2}"
    r"(?:[-_]?(?:Q[1-4]|H[12]|\d{2}(?:[-_]?\d{2})?))?$", re.I)


def _strip_file_noise(name):
    """Drop a file extension and any trailing date stamp, so the term names the
       concept rather than one export of it."""
    t = _FILE_EXT.sub("", str(name or "").strip())
    prev = None
    while prev != t:                      # e.g. "..._2026-05-14" then a stray "_"
        prev = t
        t = _DATE_SUFFIX.sub("", t).rstrip("._- ")
    return t


def table_term_name(table):
    """The table-level term for a physical table — the term linked to the TABLE
       entity so its Trust Score gets the 'term assigned' input. Uses the domain pack's
       names where known, else derives '<Singular Table> Record'."""
    t = (table or "").strip().lower()
    if t in TABLE_TERMS:
        return TABLE_TERMS[t]
    t = _strip_file_noise(t)
    if t in TABLE_TERMS:                  # a pack name may be keyed on the clean stem
        return TABLE_TERMS[t]
    human = humanize(_singularize(t))
    return f"{human} Record" if human else "Record"

def table_term_rows(tables, col_rows=None):
    """One table-level "record" term per scanned table, as a CONCEPTUAL glossary-only
       row: empty Source_Column means it is created in the glossary but never auto-linked.
       The Data Steward links each term to its table by hand to feed that table's Trust
       Score "term assigned" input — kept a manual task until Pentaho clarifies the Data
       Quality direction. Sensitivity inherits the table's highest column sensitivity so a
       record term is at least as sensitive as the data it represents."""
    col_rows = col_rows or []
    tmax = {}
    for r in col_rows:
        src = str(r.get("Source_Column", "")).split(";")[0].strip()
        parts = src.split(".")
        if len(parts) >= 3:
            tmax[parts[1]] = max(tmax.get(parts[1], 0), SENS_RANK.get(r.get("Sensitivity", "LOW"), 0))
    rows = []
    for tname in tables:
        term = table_term_name(tname)
        human_tbl = humanize(_singularize(tname)).lower()
        rows.append({
            "Keep": "Y", "Category": categorize(tname), "Term": term, "Source_Column": "",
            "Source_Table": tname,
            "Definition": f"A single {human_tbl} record — the table-level business term for the {tname} table.",
            "Purpose": f"Linked to the {tname} table at Apply (table roll-up) to give its Trust Score the assigned-term input.",
            "Sensitivity": RANK_SENS[tmax.get(tname, SENS_RANK.get("LOW", 0))],
            "PII_Category": "", "Critical_Data_Element": "No",
            "Abbreviation": _abbrev(term), "Suggested_Tags": ";".join(
                ["record", "table-level"] + tagdict.category_tags().get(categorize(tname), [])),
            "Suggested_Rating": 0, "Source_Ratings": {},
            "Suggested_Quality": None, "Source_Quality_Dims": {},
            "Status": "Draft", "Confidence": "",
            "Suggested_Reason": "Table-level term — Steward links it to the table by hand to feed the Trust Score.",
            "LLM_Enriched": "No", "Map": "No"})
    return rows

# keyword fallback for tables not in the explicit map (order matters - first hit wins)
# Categories come from the DOMAIN PACK. The engine ships none.
#
# There used to be 14 builtins here - ("billing", "Billing & Rates"), ("usage",
# "Usage") and so on. They were the water-utility scenario leaked into the
# engine: a credit union scanning `invoice_total` got a category named
# "Billing & Rates" that nobody had chosen, and it read as a considered default
# rather than a leak. Renaming them to neutral words would have kept the same
# flaw - the engine asserting a taxonomy the customer never agreed to.
#
# So: no pack, no keyword categorisation - and no INVENTED words. Since
# 1.36.21 the packless fallback is the PHYSICAL name (humanize_physical below):
# the table's own name, a document's top folder. That is evidence the scan
# proved, not a taxonomy the engine asserted, and it spares the steward
# guessing categories out of a wall of "Uncategorized" - they rename a group
# once and `Export domain pack` records the mapping, so the SECOND scan is
# categorised from the company's own evidence. categorize_column() still
# returns None packless. Same rule as the removed _CANONICAL_SEEDS: custom,
# from the profiled scan, never inbuilt.
CAT_KEYWORDS = [tuple(x) for x in _PACK.get("cat_keywords", [])]

def humanize_physical(tname):
    """A starting category from the estate's own structure, when the pack has
    no opinion: the table's name for a database, the top folder for a document.

        monthly_usage              -> Monthly Usage
        gis/asset_inventory.csv    -> Gis
        inspection_report.docx     -> Inspection Report

    This is NOT the engine asserting a taxonomy - that was the leak the big
    comment above records, and inventing business words again would repeat it.
    A physical name is evidence: the scan proved the table exists. The steward's
    job becomes RENAMING a group once ("Monthly Usage" -> "Usage"), instead of
    assigning categories row by row out of a wall of Uncategorized - stewards
    should never be left guessing. Export domain pack then records the renamed
    mapping, so the next scan categorises deterministically.
    """
    t = str(tname or "").strip()
    if "/" in t:
        t = t.split("/", 1)[0]          # a document's top folder is its subject
    else:
        t = _FILE_EXT.sub("", t)        # a bare file categorises by its stem
    t = re.sub(r"[_\-]+", " ", t).strip()
    return " ".join(w.capitalize() for w in t.split()) or "Uncategorized"


def categorize(tname):
    """Map a physical table name to a business glossary category: the pack's
    table map, else the pack's keywords, else the PHYSICAL name itself."""
    if tname in TABLE_CATEGORY:
        return TABLE_CATEGORY[tname]
    t = tname.lower()
    for kw, cat in CAT_KEYWORDS:
        if kw in t:
            return cat
    return humanize_physical(tname)


def categorize_column(cname):
    """Category implied by a COLUMN's own name, or None.

    For a database, the table is a good proxy for what its columns are about, so
    categorize(table) is enough. A FILE is not: one SCADA snapshot carries
    `turbidity_ntu` and `chlorine_residual_ppm` (water quality) alongside
    `pump_status` and `reservoir_level_percent` (water system), and the file name
    can only be right about one of them. Whatever single keyword the file matched
    would file the lot under it — which is how a harvested `Turbidity Ntu` landed
    in Water System while the database's own `Turbidity Ntu` sat in Water Quality,
    leaving two rows that can never merge (rows key on Category + Term).

    Deliberately consults CAT_KEYWORDS only, never TABLE_CATEGORY — that map is
    keyed on table names and would match a column by accident."""
    c = str(cname or "").lower()
    if not c:
        return None
    for kw, cat in CAT_KEYWORDS:
        if kw in c:
            return cat
    return None

# ---------------------------------------------------------------------------
# PII / sensitivity classification by COLUMN NAME.
#
# Each rule is a tuple:  (match, exclude, pii_category, sensitivity, tags)
#   match        regex tested against the lower-cased column name
#   exclude      regex that VETOES the match (e.g. "name" matches, but not
#                "system_name"/"file_name" which aren't personal names)
#   pii_category PDC PII bucket the column maps to (FINANCIAL, CONTACT_INFO…)
#   sensitivity  HIGH / MEDIUM / LOW assigned when this rule wins
#   tags         seed tags merged into the term's tag set
#
# Order matters: the FIRST rule that matches wins, so the most specific /
# highest-risk patterns are listed first (account number, SSN, email…) and the
# broad/low-risk ones last. A column that matches nothing is LOW with no PII.
# Value-level profiling (when "Sample values" is on) can OVERRIDE this name-based
# guess with what's actually in the data — see classify_values() above.
# ---------------------------------------------------------------------------
PII_RULES = [
    (r"account_number|acct", None, "FINANCIAL", "HIGH", ["pii", "financial"]),
    (r"ssn|social_security", None, "GOVERNMENT_ID", "HIGH", ["pii"]),
    (r"tax_?id|\bein\b|passport|driver_?licen[cs]e", None, "GOVERNMENT_ID", "HIGH", ["pii"]),
    (r"email|e_mail", None, "CONTACT_INFO", "HIGH", ["pii"]),
    (r"birth|dob|date_of_birth", None, "DEMOGRAPHIC", "HIGH", ["pii"]),
    (r"phone|mobile|telephone", None, "CONTACT_INFO", "MEDIUM", ["pii"]),
    (r"name", r"system|report|file|plan|type|source", "PERSONAL_NAME", "MEDIUM", ["pii"]),
    (r"address|street", None, "ADDRESS_INFO", "HIGH", ["pii"]),
    (r"(?<![a-z])(city|county|zip|postal|province|state)(?![a-z])", None, "ADDRESS_INFO", "MEDIUM", []),
    (r"amount|charge|tax|due|paid|balance", None, "FINANCIAL", "LOW", ["financial"]),
]
ABBREV = {"number": "No.", "identifier": "ID", "amount": "Amt", "account": "Acct",
          "address": "Addr", "quantity": "Qty", "percentage": "Pct"}
SKIP = re.compile(r"^(last_updated|created_date|created_at|updated_at)$", re.I)

# Token-level expansion for cryptic/abbreviated column names, so a horrible name
# like "cust_acct_no" becomes "Customer Account Number" rather than "Cust Acct No".
# Keys are matched per underscore-separated token (case-insensitive, exact token).
# Values are stored already-cased and inserted verbatim (so "ID"/"SSN" stay upper and
# multi-word expansions like "Date of Birth" keep their small words lower-case).
# Conservative on purpose: only well-known abbreviations a steward would expand by
# hand. Anything not listed falls through to plain Title-Casing, and every result is
# still only a *suggestion* the reviewer can edit.
EXPAND = {
    # identity / generic
    "id": "ID", "no": "Number", "num": "Number", "nbr": "Number", "cd": "Code",
    "nm": "Name", "desc": "Description", "ref": "Reference", "seq": "Sequence",
    "flg": "Flag", "ind": "Indicator", "stat": "Status", "sts": "Status",
    "qty": "Quantity", "amt": "Amount", "pct": "Percent", "avg": "Average",
    "tot": "Total", "bal": "Balance", "min": "Minimum", "max": "Maximum",
    # people / contact
    "cust": "Customer", "acct": "Account", "addr": "Address", "fname": "First Name",
    "lname": "Last Name", "dob": "Date of Birth", "ssn": "SSN", "tel": "Telephone",
    # "ph" is deliberately ABSENT: it is Phone in a CRM and pH in chemistry, and
    # a global builtin cannot know which. The generic expansion turned a water
    # utility's ph_level into "Phone Level" - which the PII name-matcher then
    # read as CONTACT_INFO, stamping privacy tags and MEDIUM sensitivity on a
    # chemistry measurement. Ambiguous tokens belong to the DOMAIN PACK, where
    # the company's own review decides (ph -> pH for a utility, Phone for a
    # call centre) and Export pack records it.
    "phn": "Phone", "email": "Email", "zip": "ZIP",
    # time
    "dt": "Date", "ts": "Timestamp", "yr": "Year", "mo": "Month", "qtr": "Quarter",
    "wk": "Week", "hr": "Hour",
    # finance / billing
    "txn": "Transaction", "trans": "Transaction", "inv": "Invoice", "pmt": "Payment",
    "freq": "Frequency", "curr": "Currency",
    # location / general
    "svc": "Service", "sys": "System", "loc": "Location", "geo": "Geographic",
    "lat": "Latitude", "lon": "Longitude", "lng": "Longitude",
}
EXPAND.update(_PACK.get("abbreviations", {}))

# Units render lowercase in parentheses — (psi), (ppm), (ntu) — the user's
# convention (walk-log W6: the namer emitted "Chlorine Residual Ppm" while
# "Pressure (psi)" sat beside it). Trailing token only: a unit mid-name is
# part of the phrase ("Rate Per 1000 Gallons"), a unit at the end is a unit.
_UNIT_SUFFIX = re.compile(r"^(.*\S)\s+(ppm|ppb|ntu|psi|gpm|kwh|mgd|pct|percent)$",
                          re.I)


def humanize(col):
    """Turn a snake_case identifier into a human-readable Title Case label, expanding
       well-known abbreviations (see EXPAND) so cryptic column names still read well."""
    s = re.sub(r"\s+", " ", re.sub(r"[_]+", " ", col).strip())
    # series tokens split CONSISTENTLY: tier1_to_gallons must name like its
    # tier2/3/4 siblings — "Tier1" beside "Tier 2" bred 88%-similar fold
    # bait and a lone misnamed term (walk-log W9 addendum)
    s = re.sub(r"\b([A-Za-z]{2,})(\d{1,2})\b", r"\1 \2", s)
    out = []
    for w in s.split():
        rep = EXPAND.get(w.lower())
        if rep is not None:
            out.append(rep)                 # already-cased expansion, inserted verbatim
        else:
            out.append(w if w.isupper() else w.capitalize())
    name = " ".join(out)
    m = _UNIT_SUFFIX.match(name)
    if m:
        unit = m.group(2).lower()
        name = f"{m.group(1)} ({'percent' if unit == 'pct' else unit})"
    return name

def _abbrev(name):
    """Derive a short uppercase abbreviation from a term name."""
    for w in name.lower().split():
        if w in ABBREV:
            return ABBREV[w]
    return ""

def classify(col):
    """Classify a column name into (pii_category, sensitivity, tags)."""
    cl = col.lower()
    for pat, excl, cat, sens, tags in PII_RULES:
        if re.search(pat, cl) and not (excl and re.search(excl, cl)):
            return cat, sens, list(tags)
    return None, "LOW", []

# The PII categories the scan classifier can legitimately assign — the
# authoritative allow-list for the guard-rail below.
PII_CATEGORIES = {cat for _, _, cat, _, _ in PII_RULES}

def guard_pii_row(r):
    """Guard-rail a row's PII_Category to what the scan actually supports.

    On an UN-PROFILED column the deterministic name classifier is the only
    legitimate source, so the value is clamped to it — rejecting any category the
    scanner wouldn't assign (e.g. an imported/legacy 'ADDRESS_INFO' on an id
    column, or 'PERSONAL_NAME' on an ssn, both of which the classifier corrects).
    A profiled column is trusted (value profiling can legitimately override the
    name), so its value is kept if valid, else cleared. Returns the guarded
    category ("" = not PII)."""
    cur = (r.get("PII_Category") or "").strip()
    profiled = bool((r.get("Value_Signature") or "").strip()
                    or (r.get("Value_Pattern") or "").strip()
                    or (r.get("Enum_Values") or "").strip())
    if profiled:
        return cur if cur in PII_CATEGORIES else ""
    col = str(r.get("Source_Column") or "").split(";")[0].strip().split(".")[-1]
    return classify(col)[0] or ""

def define(c):
    """Compose a plain-language DEFINITION for a column.

    Priority (best evidence first):
      1. The database COMMENT on the column, if the DBA wrote one — this is the
         authoritative business meaning, so it's used verbatim. A short
         comma-list comment is treated as an enumeration ("Valid values: …").
      2. A primary key  -> "Unique identifier for a <entity> record."
      3. A foreign key  -> "Reference linking this record to its related <ref>."
      4. Fallback       -> a neutral template from the humanised name.
    The LLM-enrich step can later rewrite any of these into richer prose; this
    function only guarantees every term ships with a sensible definition.
    """
    human_tbl = humanize(c["table"]).rstrip("s")   # "customers" -> "Customer"
    name = humanize(c["column"])                    # "service_address" -> "Service Address"
    if c["comment"]:
        # a comma-separated comment under ~90 chars reads as an enum of valid values
        if "," in c["comment"] and len(c["comment"].split(",")) >= 2 and len(c["comment"]) < 90:
            return f"{name} for a {human_tbl.lower()} record. Valid values: {c['comment']}."
        return c["comment"].rstrip(".") + "."       # use the DBA's comment as-is
    if c["pk"]:
        return f"Unique identifier for a {human_tbl.lower()} record."
    if c["fk"]:
        ref = humanize(c["column"]).replace(" ID", "").replace(" Id", "").strip()
        return f"Reference linking this record to its related {ref.lower()}."
    return f"{name} associated with a {human_tbl.lower()} record."

def purpose(c, category, name, pii):
    """A business 'why this matters / how it's used' sentence (the Purpose field)."""
    if c["pk"]:
        ent = humanize(c["table"]).rstrip("s").lower()
        return f"Uniquely identifies each {ent} for joins, lineage, and record integrity."
    if c["fk"]:
        ref = name.replace(" ID", "").replace(" Id", "").strip().lower() or "related record"
        return f"Links records to their related {ref} for analysis and lineage."
    if pii in ("PERSONAL_NAME", "CONTACT_INFO"):
        return "Identifies and contacts the customer; governed for privacy and regulatory compliance."
    if pii == "ADDRESS_INFO":
        return "Locates the customer for service and correspondence; governed for privacy."
    if pii == "FINANCIAL":
        return "Supports billing, revenue reporting, and financial reconciliation."
    # Definitions come from the pack, for the same reason the categories do:
    # writing one here would put words in the steward's mouth about a category
    # this engine did not choose. The templated sentence below is a neutral
    # placeholder that reads as unfinished, which is what it is.
    return _PACK.get("category_definitions", {}).get(
        category, f"Provides {category.lower()} context for reporting, governance, and discovery.")

def _slug(s):
    """Return a lower-cased, id-safe slug of a string."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

# Critical Data Element: governed with the highest care. Inferred from keys, high
# sensitivity, financial/identity PII, and critical business/compliance/safety terms.
# Always reviewable by the Data Steward in the grid.
# GENERIC signals only. This carried meter id, lead level, contaminant, pH
# and turbidity until 1.34 - drinking-water regulation deciding what counts
# as a Critical Data Element in EVERY estate, the same leak the category
# keywords had before 1.29 and the tag dictionary had before 1.33. A domain
# pack adds whatever a company's regulator actually cares about.
CDE_PATTERNS = re.compile(
    r"(account.?number|\bssn\b|social.?security|tax.?id|\bein\b|"
    r"licen[cs]e|permit|balance|amount.?(due|owed)|"
    r"complian|violation)", re.I)

def is_cde(name, sens, pii, key_like):
    """Heuristic test for a Critical Data Element — a field governed with the
    highest care (it materially affects billing, identity, safety or compliance).
    A column is flagged CDE when ANY of these hold; the steward can always override
    the call in the grid:
      - it's a primary key (an identity/anchor column),
      - it's HIGH sensitivity (already classified as risky),
      - it's financial or personal-name PII,
      - or its name matches a critical pattern (account number, meter id, balance,
        compliance/violation, lead level, pH, turbidity… — see CDE_PATTERNS).
    """
    if key_like:                       # primary key = identity anchor (plain FKs excluded)
        return True
    if sens == "HIGH":                 # already deemed high-risk by classification
        return True
    if pii in ("FINANCIAL", "PERSONAL_NAME"):   # money + direct identifiers
        return True
    return bool(CDE_PATTERNS.search(name or ""))  # domain-critical name patterns

# --------------------------------------------------------------------------- #
#  Meaningful, controlled tags — sourced from the per-company TAG DICTIONARY
#  (tagdict.py): a persisted allow-list + name->tag rules, seeded from the domain
#  and grown from scans. suggest_tags() reads the *live* dictionary, so tags stay
#  consistent with what the Registry (and, downstream, the Policy Generator) uses.
# --------------------------------------------------------------------------- #


def suggest_tags(category, sens, pii, cde, is_key, base_tags=None, name="", term=""):
    """Build a deterministic, meaningful, de-duplicated tag set for a term, drawn
    from the controlled tag dictionary (allow-list + rules):
      - PII type          -> privacy / contact / location / financial tags,
      - name/term/category-> domain tags via the dictionary's rules,
      - a meaningful category tag (dictionary category_tags), not just the slug,
      - HIGH sens -> 'maskable', CDE -> 'cde', key -> 'identifier'.
    Everything stays within the dictionary's vocabulary so tags can't drift.
    """
    t = list(base_tags or [])
    if pii == "PERSONAL_NAME":  t += ["pii", "personal-data", "direct-identifier", "privacy"]
    elif pii == "CONTACT_INFO": t += ["pii", "contact", "privacy"]
    elif pii == "ADDRESS_INFO": t += ["pii", "location", "privacy"]
    elif pii == "FINANCIAL":    t += ["financial", "sensitive"]

    hay = " ".join([str(name or ""), str(term or ""), str(category or "")])
    for rx, tags in tagdict.compiled_rules():
        if rx.search(hay):
            t += tags

    # Curated category→tags mappings apply; the old fallback — slugging the
    # category (or, at scan time, the table pseudo-category) into a tag — is
    # gone. A tag that repeats the category duplicates the domain label, and
    # a tag that repeats the table is provenance the source column already
    # records; both polluted the vocabulary gate as pending junk every scan
    # (walk-log W4/W8: eleven table echoes, "tendency to approve all").
    cat_tags = tagdict.category_tags().get(category)
    if cat_tags:
        t += cat_tags

    if sens == "HIGH":                              t.append("maskable")
    if str(cde).lower() == "yes" or cde is True:    t.append("cde")
    if is_key:                                      t.append("identifier")

    seen, out = set(), []          # standardised lower-case, de-duped, order kept
    for x in t:
        k = str(x or "").strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(k)
    return out[:7]


def retag_rows(rows):
    """Recompute meaningful Suggested_Tags for already-built review rows (e.g. a
    glossary loaded from file, or after category edits) — the 'Suggest tags' action.
    Table-level record terms keep their table-level tags."""
    for r in rows or []:
        if not isinstance(r, dict) or r.get("type") == "category":
            continue
        term = str(r.get("Term") or "").strip()
        src = str(r.get("Source_Column") or "").strip()
        if not src and re.search(r"\bRecord$", term):
            continue   # conceptual table term — leave its record/table-level tags
        col = src.split(";")[0].split(".")[-1] if src else term
        cur = [x for x in str(r.get("Suggested_Tags") or "").split(";") if x.strip()]
        is_key = ("identifier" in [c.lower() for c in cur]) or bool(re.search(r"(^|_)id$|_id(_|$)|\bcode\b", col.lower()))
        base = [x for x in cur if x.lower() in {"pii"}]   # preserve an explicit PII flag
        r["Suggested_Tags"] = ";".join(suggest_tags(
            r.get("Category"), r.get("Sensitivity", "LOW"), r.get("PII_Category", ""),
            r.get("Critical_Data_Element", "No"), is_key, base, name=col, term=term))
        lifted = tagdict.lift_sensitivity(r.get("Sensitivity", "LOW"),
                                          r["Suggested_Tags"].split(";"), term)
        if lifted != r.get("Sensitivity"):
            r["Sensitivity"] = lifted
    return rows

def rate_column(confidence=None, has_comment=False, pk=False, fk=False,
                notnull=False, uniqueness=None, completeness=None,
                sensitivity=None, has_term=True, has_definition=True):
    """Suggest a 1-5 star User Rating for a column from scan/profile signals.

    A governance-readiness + data-quality heuristic meant as a starting point a
    steward can override — NOT a substitute for Pentaho Data Quality scoring.
    Signals (all optional, degrades gracefully when profiling wasn't run):
      confidence    suggester confidence in the term mapping (High/Medium/Low)
      has_comment   column documented at the source (DDL COMMENT)
      pk/fk/notnull structural integrity / completeness guarantee
      uniqueness    distinct/non-null ratio from profiling (0-1)
      completeness  non-null/total ratio from profiling (0-1)
      sensitivity   set to a known level (column has been classified)
      has_term/has_definition  governance metadata present
    """
    score = 2.0
    c = str(confidence or "").lower()
    if c == "high":
        score += 1.0
    elif c == "medium":
        score += 0.5
    if has_comment:
        score += 0.5
    if has_definition:
        score += 0.25
    if has_term:
        score += 0.25
    if pk or notnull:
        score += 0.5
    if fk:
        score += 0.25
    if completeness is not None:
        score += (float(completeness) - 0.5)        # +/-0.5 around half-full
    if uniqueness is not None and float(uniqueness) >= 0.9:
        score += 0.5
    if sensitivity and str(sensitivity).upper() in ("LOW", "MEDIUM", "HIGH"):
        score += 0.25
    return max(1, min(5, int(round(score))))


# Default DQ dimension weights (renormalised over whichever dimensions apply
# to a given column). Completeness applies to every column; uniqueness only
# where the column is expected to be unique (keys/identifiers), so a low-
# cardinality enum is not penalised; validity only where a type/pattern was
# detected to conform against.
DQ_WEIGHTS = {"completeness": 0.4, "uniqueness": 0.3, "validity": 0.3}


def quality_score_column(completeness=None, uniqueness=None, validity=None,
                         expect_unique=False, notnull=False, weights=None):
    """Best-practice Data Quality score (0-100) from profiling signals.

    Scores only the dimensions that can be measured for this column and
    renormalises the weights over them, so a column missing a dimension is not
    unfairly dragged down:
      completeness  non-empty / sampled rows (proxy: NOT NULL -> 1.0, but only
                    when at least one dimension was actually measured)
      uniqueness    distinct / non-null, counted ONLY when uniqueness is expected
                    (primary key or identifier-like) -- otherwise a defect-free
                    low-cardinality column would score badly
      validity      share of values conforming to the detected type/pattern

    Returns an int 0-100, or None when nothing is measurable (so the caller can
    skip writing a qualityScore rather than assert a misleading 0).

    A column that was never profiled returns None even when it is NOT NULL:
    letting the schema constraint alone stand in for completeness manufactured
    a wall of DQ 100s on unprofiled scans (e.g. pasted DDL), asserting perfect
    quality about data nobody ever sampled. Not profiled now means no score,
    not 100."""
    if completeness is None and uniqueness is None and validity is None:
        return None                 # nothing was profiled — no score, not 100
    w = dict(DQ_WEIGHTS)
    if weights:
        for k in w:
            if weights.get(k) is not None:
                w[k] = float(weights[k])
    dims = []
    comp = completeness
    if comp is None and notnull:
        comp = 1.0
    if comp is not None:
        dims.append((w["completeness"], max(0.0, min(1.0, float(comp)))))
    if expect_unique and uniqueness is not None:
        dims.append((w["uniqueness"], max(0.0, min(1.0, float(uniqueness)))))
    if validity is not None:
        dims.append((w["validity"], max(0.0, min(1.0, float(validity)))))
    wsum = sum(wt for wt, _ in dims)
    if wsum <= 0:
        return None
    score = sum(wt * v for wt, v in dims) / wsum
    return int(round(score * 100))


# Auto-prune rules for columns harvested from DOCUMENTS. PDC's Data Discovery
# flattens a nested file into dotted paths, so a JSON like
#   {"export_metadata": {"units": {"flow": "gpm"}}, "readings": [{"chlorine_residual_ppm": …}]}
# arrives as columns "export_metadata.units.flow" and "readings.chlorine_residual_ppm".
#
# The distinction that matters is ENVELOPE vs PAYLOAD:
#   envelope — describes the FILE (units declarations, export date, source,
#              snapshot type, interval, sensor/record ids, timestamps). Never a
#              business term, and every JSON in a store emits a fresh batch.
#   payload  — the DATA in the file. "readings.chlorine_residual_ppm" and
#              "systems.turbidity_ntu" are regulated drinking-water measures:
#              exactly what a utility's glossary exists to govern.
#
# An earlier version pruned EVERY dotted path, which caught the envelope and then
# swept the payload up with it — 28 of 54 harvested rows pruned, including
# chlorine residual and turbidity. Nesting is a fact about the file format, not
# evidence that a value is uninteresting. So the rules now name the envelope
# explicitly and leave anything else kept, with the LEAF as the term name.
# First match wins.
_DOC_PRUNE_RULES = (
    (re.compile(r"^(export[_.]?)?meta(data)?[._]", re.I),
     "document envelope — file metadata (units, export info), not a business concept"),
    (re.compile(r"^(_|\$|@)"),
     "document control field — a reserved/system key, not a business concept"),
    # envelope fields that appear at the top of a reading/record block rather than
    # under a metadata parent — bookkeeping about the extract, not measures
    (re.compile(r"\.(timestamp|ingested_?at|extracted_?at|export_?date|"
                r"record_?id|row_?id|sensor_?id|file_?name|source|checksum)$", re.I),
     "document bookkeeping field — describes the extract, not the data in it"),
)


def document_leaf_name(column):
    """The business-meaningful tail of a flattened document path.

    'systems.chlorine_residual_ppm' -> 'chlorine_residual_ppm'. The parent is the
    JSON container ('systems', 'readings'), which names the file's shape rather
    than the concept, so the leaf is what the term should be called."""
    name = str(column or "")
    return name.rsplit(".", 1)[-1] if "." in name else name


def document_path_prune(column):
    """Why this document-derived column should start un-kept, or None to keep it.

    Only meaningful for columns harvested from a file: a database column name
    does not contain a path separator, so these rules cannot fire on one."""
    name = str(column or "")
    for rx, reason in _DOC_PRUNE_RULES:
        if rx.search(name):
            return reason
    return None


# Column-level scan noise the review should retire on sight (field-caught:
# "some of these Terms should have been retired: Length Feet, Total Revenue
# May 2026, Description"). Two CRISP signatures prune deterministically —
# restorable, reason on the row; judgment calls stay with the AI advisor.
_MONTH_RX = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
             r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
             r"nov(?:ember)?|dec(?:ember)?)")
# a period stamp at the END of a column name: total_revenue_may_2026,
# revenue_2026q1, budget_2026 — the stamp names WHEN, not what
_COL_PERIOD = re.compile(
    r"[._-](?:(?:19|20)\d{2}(?:[-_]?(?:%s|q[1-4]|h[12]|\d{2}))?"
    r"|%s[-_]?(?:19|20)\d{2})$" % (_MONTH_RX, _MONTH_RX), re.I)
# a BARE structural column — describes its table's rows, names no concept
_STRUCTURAL_GENERIC = re.compile(
    r"^(?:description|descr|desc|notes?|comments?|remarks?|memo)$", re.I)


def column_noise_prune(column):
    """Why this column name is scan noise that should start un-kept, or None.
    Engine-agnostic (database and document columns alike): a period-stamped
    snapshot column mints a NEW term per export period, and a bare
    'description'/'notes' column is structure, not vocabulary."""
    name = str(column or "").split("/")[-1].split(".")[-1].strip().lower()
    if not name:
        return None
    if _STRUCTURAL_GENERIC.match(name):
        return ("structural column name (%s) — describes its table's rows, "
                "not a business concept; restore it if it names a real "
                "concept here" % name)
    if _COL_PERIOD.search(name):
        return ("period-stamped snapshot column — the stamp names WHEN the "
                "extract was cut, not what the data is; each new period "
                "would mint another term")
    return None


def _pdc_stat(stats, *names):
    """First present, numeric value among `names` in a PDC profilingInfo.stats
       block. PDC has spelled these differently across versions, and the compare
       view already probes several aliases per figure."""
    for n in names:
        v = (stats or {}).get(n)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def quality_from_pdc_stats(stats, expect_unique=False):
    """Derive a 0-100 Data Quality score from PDC's OWN profiling of a column.

    The app normally scores from its own sampling, but it cannot read every
    format — a PDF or DOCX has no rows to sample, and a huge file is only
    partially read. PDC profiles server-side and stores real measurements, so
    where it has profiled, its numbers are better evidence than ours.

    Mapping (PDC reports percentages, this scorer takes 0..1):
      completeness  <- density        (share of non-null, non-blank values)
      uniqueness    <- uniqueness     (only counted where uniqueness is expected)
      validity      <- not exposed by PDC's stats; left unmeasured, and
                       quality_score_column renormalises over what remains.

    Returns None when PDC profiled nothing usable — never a 0 and never a 100,
    for the same reason the column scorer refuses to: an unprofiled column with
    a manufactured score is worse than an honest blank.
    """
    density = _pdc_stat(stats, "density", "completeness", "nonNullDensity")
    uniq = _pdc_stat(stats, "uniqueness", "uniquenessRatio")
    if density is None and uniq is None:
        return None
    # PDC reports these as percentages (density 100 = fully populated); the
    # scorer wants 0..1. Tolerate a source that already normalised.
    def _frac(v):
        if v is None:
            return None
        return v / 100.0 if v > 1.0 else v
    return quality_score_column(completeness=_frac(density),
                                uniqueness=_frac(uniq),
                                validity=None,
                                expect_unique=expect_unique)


def rate_document(owner=None, ext=None, sensitivity=None, recent=False, has_term=True):
    """Suggest a 1-5 rating for a FILE/object entity. The column heuristic's
    structural signals (pk/fk/uniqueness/not-null) don't exist for files, so this
    rates curation/governance instead: a steward/owner tag, a usable known format,
    a classified sensitivity, and recency. Conservative midpoint baseline."""
    score = 3.0
    if owner:
        score += 1.0                      # governed: has an owner/steward signal
    known = (ext or "").lower() in (
        "json", "csv", "tsv", "psv", "parquet", "avro", "orc",
        "xml", "xlsx", "xls", "pdf", "docx", "txt")
    if known:
        score += 0.5                      # a format PDC can profile/extract from
    if str(sensitivity or "").upper() in ("MEDIUM", "HIGH"):
        score += 0.5                      # recognised, classified document class
    if recent:
        score += 0.5                      # recently modified -> more likely current
    if not has_term:
        score -= 1.0
    return max(1, min(5, int(round(score))))


def _detection_intent(c, prof, pii):
    """'mapping_only' when data of this nature can never be detected by value
    shape; '' (Auto) otherwise. Deterministic; per-row steward override wins
    downstream ("what else would be map instead of auto?")."""
    typ = str(c.get("type") or "").lower()
    kind = str(prof.get("kind") or "")
    has_shape = bool(prof.get("pattern") or prof.get("signature"))
    enum = prof.get("enum") or []
    # dates
    if kind == "date" or re.search(r"date|timestamp|\btime\b", typ):
        return "mapping_only"
    # personal names: prose, no shape
    if str(pii or "").strip().upper() == "PERSONAL_NAME":
        return "mapping_only"
    # Booleans: a generic true/false pair detects every flag in the estate, and
    # PDC cannot content-match them at all — it evaluates patterns and
    # dictionaries against a column's VALUES, and a bit column has none to
    # evaluate (proven live 2026-08-20: BIT columns tagged nothing under a
    # name-anchored regex AND under a hand-built {0,1} dictionary). `\bbool`
    # alone missed the type PDC actually reports for a flag — BIT — so the two
    # flags on this estate stayed Auto, were flipped by a steward, and became
    # methods that imported cleanly, passed drift, and were inert forever.
    if re.search(r"\bbool|\bbit\b|tinyint\s*\(\s*1\s*\)", typ):
        return "mapping_only"
    low = {str(v).strip().lower() for v in enum}
    if low and low <= {"true", "false", "yes", "no", "y", "n", "0", "1", "t", "f"}:
        return "mapping_only"
    # free numeric measures: numeric type or numeric kind, with no format and
    # no coded vocabulary
    # substring 'int' (interval excluded): \bint missed bigint/int8/smallint,
    # so population_served-class columns never went quiet (field-caught)
    # A DOCUMENT column has no SQL type at all — a CSV or JSON column arrives
    # typeless — so a type-driven test cannot reach it, and every numeric
    # measure harvested from a file escaped this guard and arrived Auto.
    # Field-caught 2026-08-21: latitude, longitude, install_year, length_feet,
    # diameter_inches and condition_rating each minted a method backed by
    # "is a number", nine concepts deep on one shape. The profiled min/max IS
    # the evidence that a column is numeric, whatever the source could tell us
    # about its type — so when there is no type, believe the range.
    numericish = (kind in ("decimal",)
                  or re.search(r"int(?!erval)|numeric|decimal|float|double|real|money|serial", typ)
                  or (not typ and bool(_fmt_range(prof))))
    if numericish and not has_shape and not enum:
        # bounded measure whose NAME carries its unit (pH, lead_ppb,
        # turbidity_ntu): the draft's recommended flip, applied at suggest
        # time — "I thought this would be done automatically" — so these
        # arrive AUTO and mint name-anchored rules without a steward click.
        # Everything else numeric stays mapping-only: the safe posture.
        from engine.sug_shared import UNIT_NAME
        nm = re.sub(r"[^A-Za-z0-9]+", "_", str(c.get("name") or ""))
        if UNIT_NAME.search(nm) and _fmt_range(prof):
            return ""
        return "mapping_only"
    return ""


def _fmt_range(prof):
    """Compact numeric-range evidence off a profile: '201..5095'. A numeric
    column IS profiled - completeness, uniqueness, min/max - even though it
    rightly gets no value set or pattern; without this field the UI called
    it "no evidence" and the steward read that as a data bug (field-caught
    on 'Capacity'). Rides PDC's entity stats and any profiler that fills
    min/max."""
    lo, hi = prof.get("min"), prof.get("max")
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        return ""
    def _n(v):
        return str(int(v)) if float(v).is_integer() else f"{v:g}"
    return f"{_n(lo)}..{_n(hi)}"


def suggest(tables, schema=None):
    schema = schema or os.environ.get("GLOSSARY_SCHEMA", "public")
    """Build suggested glossary rows from scanned tables (term, definition, sensitivity, rating, DQ dims)."""
    rows, seen, out = [], {}, []
    # the FK-family signal: the SAME id-named column in 2+ tables is a join
    # key by construction, whether or not the source declared constraints —
    # PDC's harvest path carries no pk/fk flags, which is how customer_id and
    # system_id sailed through the structural prune ("How did Customer ID get
    # through when its a key?")
    _id_family = {}
    for _tn, _cs in tables.items():
        for _c in _cs:
            _cl = str(_c.get("column") or "").lower()
            if re.search(r"(^|_)id$|_id$|identifier", _cl):
                _id_family.setdefault(_cl, set()).add(_tn)
    for tname, cols in tables.items():
        category = categorize(tname)
        # A file name is a poor proxy for what its columns are about — one SCADA
        # snapshot holds water-quality AND water-system measures — so for
        # DOCUMENT-derived rows a column whose own name implies a category wins.
        # Scoped to documents on purpose: in a database the table IS the subject,
        # and letting a column override there would file `customer_id` in
        # `water_systems` under Customer.
        _is_document = bool(_FILE_EXT.search(tname or ""))
        # PERSON CONTEXT, judged once per table from its own columns: a table
        # with email/phone/customer/name-part columns holds people; one with
        # latitude/material/asset columns holds things. Context-dependent PII
        # classes only stand in person context — an asset's street_name is
        # WHERE A PIPE IS, not someone's address (walk-log W5: Street Name,
        # Site Name, water_systems.county and an aggregate unpaid_accounts
        # all shipped as PII).
        _PERSON_SIGNALS = re.compile(
            r"email|phone|ssn|social|dob|birth|customer_id|account_number|"
            r"customer_?name|full_?name|first_?name|last_?name|salutation|contact", re.I)
        _person_ctx = any(_PERSON_SIGNALS.search(str(c.get("column") or ""))
                          for c in cols)
        _CTX_PII = {"PERSONAL_NAME", "ADDRESS_INFO", "FINANCIAL"}

        for c in cols:
            if SKIP.match(c["column"]):
                continue
            row_category = category
            if _is_document:
                _by_col = categorize_column(document_leaf_name(c["column"]))
                if _by_col:
                    row_category = _by_col
            # A flattened document path names the file's shape, not the concept:
            # "systems.chlorine_residual_ppm" is the term "Chlorine Residual Ppm",
            # living under a JSON container that means nothing to a steward. Take
            # the leaf so it reads as a business term and merges with the same
            # concept arriving from a database column.
            name = humanize(document_leaf_name(c["column"]))
            # canonicalize divergent names to one governed term (e.g. "Cust ID" ->
            # "Customer ID"), so instances across tables collapse and merge cleanly.
            _canon = tagdict.canonical_name(name)
            _orig_name = name
            if _canon:
                name = _canon
            pii, sens, tags = classify(c["column"])
            if pii in _CTX_PII and not _person_ctx:
                # the name matched a person-PII pattern in a table that holds
                # no people — geography/asset data wearing person words
                pii, sens, tags = None, "LOW", []
            prof = c.get("profile") or {}
            if prof.get("pii"):         pii = prof["pii"]
            if prof.get("sensitivity"): sens = prof["sensitivity"]
            profiled_unique = (prof.get("uniq") or 0) >= 0.95
            is_key = bool(c["pk"] or c["fk"])
            cde = is_cde(name, sens, pii, bool(c["pk"]))
            # CONFIDENCE is an EVIDENCE signal (how sure we are of the term mapping),
            # not a data-quality score. The ladder runs strongest evidence first:
            #   High   - a real DDL comment, a key column, or a profiling hit in data
            #   Medium - the name matched a PII pattern, or weaker profiling evidence
            #   Low    - nothing but the column name to go on (templated)
            # `reason` is surfaced in the UI so the user can see WHY each term scored.
            if c["comment"]:
                conf, reason = "High", "DDL comment used for definition"
            elif is_key:
                conf, reason = "High", "Key column - identity/relationship"
            elif prof.get("confidence") == "High":
                conf, reason = "High", prof.get("reason", "Profiled from data")
            elif pii:
                conf, reason = "Medium", (prof.get("reason") if prof.get("pii") else f"Name matched {pii} pattern")
            elif prof.get("confidence") == "Medium":
                conf, reason = "Medium", prof.get("reason", "Profiled from data")
            else:
                conf, reason = "Low", "Templated from column name"
            if _canon:
                reason = f"{reason} · canonicalized from '{_orig_name}' (dictionary alias)"
            all_tags = suggest_tags(row_category, sens, pii, "Yes" if cde else "No", is_key, tags, name=c["column"], term=name)
            # lift sensitivity to the highest floor the tags / canonical term imply
            # (ordinal — the dictionary can only tighten a classification, never relax it)
            lifted = tagdict.lift_sensitivity(sens, all_tags, name)
            if lifted != sens:
                sens = lifted
                cde = is_cde(name, sens, pii, bool(c["pk"]))
                all_tags = suggest_tags(row_category, sens, pii, "Yes" if cde else "No", is_key, tags, name=c["column"], term=name)
            rating = rate_column(confidence=conf, has_comment=bool(c["comment"]),
                                 pk=c["pk"], fk=c["fk"], notnull=c["notnull"],
                                 uniqueness=prof.get("uniq"), sensitivity=sens,
                                 has_term=True, has_definition=True)
            src = f"{schema}.{tname}.{c['column']}"
            # raw DQ dimensions for this physical column (weight-independent, so
            # weights can be tuned later at Apply time without re-scanning)
            expect_unique = bool(c["pk"] or prof.get("kind") in ("identifier", "ssn", "card", "email"))
            qdims = {"c": prof.get("completeness"), "u": prof.get("uniq"),
                     "v": prof.get("valid"), "eu": expect_unique, "nn": bool(c["notnull"])}
            quality = quality_score_column(completeness=qdims["c"], uniqueness=qdims["u"],
                                           validity=qdims["v"], expect_unique=qdims["eu"],
                                           notnull=qdims["nn"])
            # Best-practice prune (deterministic, reversible): a surrogate PK / FK
            # reference-id is structural, not a business term — its concept lives
            # on the natural key it references and reaches PDC via the term↔column
            # link, so it starts un-kept. Natural/business keys (formatted → a
            # value pattern), PII, and coded columns are always kept. The PK/FK
            # relationship graph is preserved in the Registry regardless (see
            # registry/bridge.py), so pruning the term never loses the joins.
            _surrogate = bool(re.search(r"(^|_)id$|_id$|identifier", c["column"].lower()))
            # only FORMATTED evidence (a value pattern/signature like AWC-CG-001001)
            # marks a natural key worth keeping; an enum on a declared key is just
            # a low-cardinality FK — the reference-data concept lives on the
            # referenced table, so it doesn't block the structural prune
            _has_shape = bool(prof.get("pattern") or prof.get("signature"))
            # identity PII on an id-like name is a real natural identifier
            # (tax_id → GOVERNMENT_ID stays a term); FINANCIAL from a bare
            # prefix match (acct_id) is noise and doesn't block the prune
            _identity_pii = pii in ("GOVERNMENT_ID", "CONTACT_INFO", "PERSONAL_NAME",
                                    "DEMOGRAPHIC", "ADDRESS_INFO")
            # declared keys, OR the evidence stand-ins the harvest path has:
            # a near-unique id-named column is a surrogate PK in fact, and an
            # id-named column shared by 2+ tables is a join key in fact
            _fk_family = len(_id_family.get(c["column"].lower(), ())) >= 2
            _uniq_hint = (_surrogate
                          and float((c.get("profile") or {}).get("uniq") or 0) >= 0.95
                          and int((c.get("profile") or {}).get("rows") or 0) >= 20)
            _keyish = bool(c["pk"] or c["fk"] or (_surrogate and _fk_family) or _uniq_hint)
            _structural = bool(_keyish and _surrogate
                               and not _identity_pii and not _has_shape)
            # A column harvested from a document arrives as a flattened path when
            # Discovery walked a nested file. Those are structure, not concepts —
            # prune them the same way, with the reason on the row.
            _doc_prune = None if _structural else document_path_prune(c["column"])
            # Column-name noise: period-stamped snapshots and bare structural
            # columns (description/notes) — deterministic, restorable
            _col_noise = None if (_structural or _doc_prune) else column_noise_prune(c["column"])
            _pruned = bool(_structural or _doc_prune or _col_noise)
            rows.append({"Keep": ("N" if _pruned else "Y"),
                         "Prune_Reason": (("structural key — surrogate %s, tagged via the "
                                           "term↔column link, not a business term"
                                           % ("PK" if c["pk"]
                                              else "FK reference" if c["fk"]
                                              else "join key (same column in %d tables)"
                                                   % len(_id_family.get(c["column"].lower(), ()))
                                                   if _fk_family
                                              else "id (near-unique values)"))
                                          if _structural else (_doc_prune or _col_noise or "")),
                         "Category": row_category, "Term": name,
                         "Source_Column": src,
                         "Definition": define(c), "Purpose": purpose(c, row_category, name, pii),
                         "Sensitivity": sens,
                         "PII_Category": pii or "", "Critical_Data_Element": "Yes" if cde else "No",
                         "Abbreviation": _abbrev(name), "Suggested_Tags": ";".join(all_tags),
                         "Suggested_Rating": rating,
                         # per-physical-column rating, so a term mapping to several
                         # columns rates each on its own scan signals (not one shared)
                         "Source_Ratings": {src: rating},
                         # per-column DQ score + the raw dimensions behind it
                         "Suggested_Quality": quality,
                         "Source_Quality_Dims": {src: qdims},
                         # physical key facts (PK/FK + referenced column). PDC's
                         # built-in Is Primary/Foreign Key is harvest-owned metadata
                         # the public API cannot PATCH, so Apply lands these under
                         # attributes.extended and the Registry records them for
                         # the Policy Generator's relationship context.
                         "Source_Keys": ({src: {"pk": bool(c["pk"]), "fk": bool(c["fk"]),
                                                "ref": (f"{c['ref_table']}.{c['ref_col']}"
                                                        if c.get("fk") and c.get("ref_table")
                                                        else None)}}
                                         if (c["pk"] or c["fk"]) else {}),
                         # physical type per column — schema metadata the DQ
                         # expectations derive type-conformance checks from
                         "Source_Types": ({src: str(c.get("type") or "")}
                                          if c.get("type") else {}),
                         "Status": "Draft", "Confidence": conf, "Suggested_Reason": reason,
                         # scan evidence: the induced value format / reference list —
                         # carried through save + export so the Registry can hand the
                         # Policy Generator a ready-made pattern / dictionary seed
                         "Value_Signature": prof.get("signature", ""),
                         "Value_Pattern": prof.get("pattern", ""),
                         "Enum_Values": ";".join(prof.get("enum", []) or []),
                         # the profiler's VERDICT survives as data — prose
                         # markers (Suggested_Reason "Profiled: …") die the
                         # moment the AI pass rewrites the field, and the
                         # drafter then told profiled rows to "re-scan"
                         "Value_Kind": prof.get("kind", ""),
                         "Value_Range": _fmt_range(prof),
                         # mapping-only wherever the NATURE of the data
                         # precludes a discriminating shape - never merely
                         # because evidence is absent (an unsampled text column
                         # might still be a dictionary). Four classes: dates
                         # (every date matches every date), personal names
                         # (prose has no shape), free numeric measures (any
                         # number matches any number - formatted codes and
                         # coded enums stay Auto), and booleans (a Yes/No
                         # vocabulary would detect every flag in the estate).
                         # The steward can flip any row back.
                         "Detection_Intent": _detection_intent(c, prof, pii),
                         "LLM_Enriched": "No"})
    for r in rows:
        key = (r["Category"], r["Term"])
        if key in seen:
            seen[key]["Source_Column"] += "; " + r["Source_Column"]
            # carry each merged column's own rating; representative = best of them
            seen[key].setdefault("Source_Ratings", {}).update(r.get("Source_Ratings", {}))
            seen[key].setdefault("Source_Keys", {}).update(r.get("Source_Keys", {}))
            seen[key].setdefault("Source_Types", {}).update(r.get("Source_Types", {}))
            seen[key]["Suggested_Rating"] = max(seen[key].get("Suggested_Rating", 0),
                                                r.get("Suggested_Rating", 0))
            # carry each merged column's own DQ dimensions
            seen[key].setdefault("Source_Quality_Dims", {}).update(r.get("Source_Quality_Dims", {}))
            for f in ("Value_Signature", "Value_Pattern", "Enum_Values", "Value_Kind",
                      "Value_Range", "Detection_Intent"):
                if not seen[key].get(f) and r.get(f):
                    seen[key][f] = r[f]
            # A term survives the structural-key prune when ANY of its merged
            # columns is non-structural — the dictionary canonicalizes a surrogate
            # (mbr_id) and its natural key (mbr_no) onto ONE term, and the natural
            # key must win: the concept stays kept, the id column just rides along
            # as an extra linked source.
            if str(r.get("Keep", "Y")).upper() == "Y" and str(seen[key].get("Keep")).upper() != "Y":
                seen[key]["Keep"] = "Y"
                seen[key]["Prune_Reason"] = ""
            continue
        seen[key] = r
        out.append(r)
    # Add one table-level "record" term per table — created in the glossary so the
    # Steward has it to link, but conceptual (no Source_Column) so the app never
    # auto-links it. Skip any that would collide with an existing (category, term).
    # DOCUMENT "tables" (bucket/path keys) mint no record term: the file and
    # folder terms from suggest_document_files already own that role, and a
    # record term derived from a full path reads as garbage ("Awc-documents/
    # gis/asset Inventory Record" — live-test-caught before release).
    existing = {(r["Category"], r["Term"]) for r in out}
    out += [r for r in table_term_rows(
                {t: c for t, c in tables.items() if not _FILE_EXT.search(t or "")}, out)
            if (r["Category"], r["Term"]) not in existing]
    return out

