"""
seed_sample.py - populate a PostgreSQL schema with realistic sample data
so data-profiling has real values to detect (PII, patterns, cardinality).

TRAINING AND DEMO DATABASES ONLY. This WRITES fabricated rows. It fills empty
tables by default, which is not the safeguard it sounds like - a production
estate has empty tables too (a new feature's, an audit table not yet written to,
a staging table between loads) and they would be filled. The API refuses unless
the connection is explicitly marked allow_sample_data; keep it that way.

It introspects the live schema (information_schema), orders tables by foreign-key
dependencies, skips auto-generated keys, references parent PKs for FK columns, and
generates values by column name + type. By default it only fills EMPTY tables.

CLI:   python seed_sample.py --host localhost --port 5433 --db your_db \
                          --user <user> --password '<password>' --rows 200
API:   from seed_sample import seed ; seed(cfg, rows=200)
"""
import random, datetime, string, argparse, re

FIRST = ["Maria", "Robert", "Susan", "David", "John", "Emma", "Luis", "Anna", "James",
         "Olivia", "Carlos", "Linda", "Michael", "Sofia", "Daniel", "Grace"]
LAST = ["Garcia", "Hayes", "Park", "Chen", "Smith", "Brown", "Diaz", "Lee", "Johnson",
        "Martinez", "Nguyen", "Patel", "Wilson", "Khan", "Rivera", "Clark"]
STREETS = ["Main St", "Oak Ave", "Elm Dr", "Pine Rd", "Maple Ln", "Cedar Ct", "Sunset Blvd",
           "Desert Way", "Canyon Rd", "Mesa Dr"]
CITIES = ["Phoenix", "Tucson", "Mesa", "Tempe", "Chandler", "Scottsdale", "Glendale",
          "Apache Junction", "Bisbee", "Casa Grande", "Coolidge", "Oracle", "Sedona",
          "Sierra Vista", "Stanfield"]   # the estate's live 15 — keep reseeds stable
# AWC system codes: the 8 verified from the original rows (CD = Coolidge, not
# Chandler) plus 7 minted for the cities the originals never covered
SYS_CODES = ["AJ", "BIZ", "CD", "CG", "ORA", "SED", "SF", "SV",
             "CH", "GL", "ME", "PH", "SC", "TE", "TU"]
EMAIL_DOM = ["example.com", "mail.com", "gmail.com"]
STATUS = ["active", "active", "active", "inactive", "suspended"]
CUST_TYPE = ["residential", "residential", "commercial"]
ALERT_TYPE = ["high_usage", "leak_detected", "payment_due", "quality_notice", "service_interruption"]
COMPLIANCE = ["compliant", "compliant", "compliant", "violation"]
PAY_STATUS = ["Paid", "Paid", "Paid", "Unpaid", "Overdue"]
# The vocabularies below are the ESTATE'S OWN — read back off the original
# rows, not invented. Twelve columns had no name rule and fell through to the
# generic text fallback, which minted one shape (^[A-Z]{2}[0-9]{4}$) for all of
# them: county, severity, contaminant_level, system_type, source_type,
# primary_source, conservation_focus, service_county, notes x2, description
# and recommended_action all came back as 'WQ2602'. One shape across twelve
# unrelated concepts is worse than no data — the profiler induces it, the
# drafter backs every one of those concepts with it, and free-text `notes`
# arrives bound to all of them (field-caught on the 2026-08-20 identification
# run, and papered over app-side by name-anchoring the seeds).
COUNTIES = ["Pinal", "Pinal", "Cochise", "Coconino", "Maricopa", "Navajo"]
# city -> county, so service_county agrees with the service_city on its own row
CITY_COUNTY = {"Phoenix": "Maricopa", "Mesa": "Maricopa", "Tempe": "Maricopa",
               "Chandler": "Maricopa", "Scottsdale": "Maricopa", "Glendale": "Maricopa",
               "Apache Junction": "Pinal", "Casa Grande": "Pinal", "Coolidge": "Pinal",
               "Oracle": "Pinal", "Stanfield": "Pinal", "Bisbee": "Cochise",
               "Sierra Vista": "Cochise", "Sedona": "Coconino", "Tucson": "Pima"}
SEVERITY = ["Low", "Low", "Medium", "Medium", "High"]
CONTAM_LEVEL = ["Low", "Low", "Low", "Elevated"]
SYSTEM_TYPE = ["Groundwater", "Groundwater", "Groundwater", "Mixed"]
PRIMARY_SOURCE = ["Groundwater Wells", "Groundwater Wells", "Mountain Springs + Wells",
                  "Local Springs & Wells", "Military Water Allocation + Wells"]
SOURCE_TYPE = ["Wells - San Tan Valley", "Wells - Lower Hassayampa", "Wells - Mule Creek",
               "Wells - Oracle Ridge", "Wells - Harquahala Valley Aquifer",
               "Wells + Local Surface Water", "Wells + Watershed Recharge",
               "Wells + Fort Huachuca Allocation"]
CONSERVATION_FOCUS = [
    "Tier-based conservation, agricultural water reuse, desert landscaping education",
    "Residential conservation, tourism water efficiency, seasonal management",
    "Historic mining town, limited groundwater availability, reuse programs",
    "Mountain community, seasonal variation, wildlife protection",
    "Military installation coordination, population growth planning",
    "Suburban growth management, new development standards",
    "Expanding metro area, new customer acquisition, infrastructure growth",
    "Rural agriculture, small system management, reliability focus"]
QUALITY_NOTE = [
    "{sys} system performing within EPA standards. Slight hardness in central area.",
    "{sys} system showing elevated turbidity. Investigating source issue.",
    "{sys} system struggling with water hardness. Consider treatment upgrade.",
    "{sys} system maintaining excellent quality. Mountain source water naturally pure.",
    "{sys} mixed source system stable. No compliance issues."]
ALERT_DESC = [
    "May {yr} bill ${amt} unpaid and past due date ({yr}-05-15).",
    "May bill ${amt} overdue by 17 days. No payment arrangement made.",
    "Account suspended since {yr}-05-20. {sys} non-payment. Two months unpaid.",
    "Commercial customer using {gal} gallons in May (typical 120,000). 54% above normal.",
    "Agricultural account using {gal} gallons (above 90% of annual tier usage).",
    "Resort using {gal} gallons (seasonal normal for hospitality). Within expected range."]
ALERT_ACTION = [
    "Contact customer for payment. Assess risk of service suspension after 60 days.",
    "Follow collection procedure. Consider account closeout if payment not received.",
    "Issue 30-day notice. If unpaid, schedule service suspension review.",
    "Suggest leak check. Review for irrigation/HVAC efficiency opportunities.",
    "Continue monitoring. Usage consistent with summer tourism season.",
    "Remind of summer irrigation best practices per AWC conservation program."]
# a TEXT rating column takes the label scale, a NUMERIC one takes 1..5 — the
# seeder wrote randint(1,5) into varchar quality_rating, so the estate's
# governed vocabulary read '1;5;Excellent;Good': a scale mixed with labels,
# which matched nothing when the Policy Generator built a dictionary from it
RATING_LABEL = ["Excellent", "Good", "Good", "Fair", "Poor"]
# gallons ladder for tiered_rates: tier N starts where tier N-1 stopped, so
# from/to never cross and the four tiers read as one rate card
TIER_EDGE = [0, 5000, 15000, 30000, 60000]
TIER_RATE = [2.45, 3.60, 5.15, 7.40]


def _rand_date(start_days=2000, span=1800):
    return datetime.date.today() - datetime.timedelta(days=random.randint(0, start_days)) \
        + datetime.timedelta(days=random.randint(0, span) - span)


def _tier(n):
    """The 1..4 a tiered_rates column belongs to, or None."""
    m = re.search(r"tier[_ ]?([1-4])", n)
    return int(m.group(1)) if m else None


def _gen(colname, dtype, row_i, refs, row=None):
    """Generate one value for a column based on its name and SQL type.

    `row` carries the values already generated for THIS row — columns are
    visited in ordinal order, so a column may agree with an earlier one
    instead of drawing independently (service_county follows service_city).
    """
    n = colname.lower()
    t = (dtype or "").lower()
    row = row or {}
    txt = "char" in t or "text" in t
    if colname in refs:                       # foreign key -> reference an existing parent PK
        pool = refs[colname]
        return random.choice(pool) if pool else None
    # name-driven
    if "email" in n:
        return f"user{row_i}{random.randint(1,99)}@{random.choice(EMAIL_DOM)}"
    if "phone" in n:
        return f"{random.choice(['602','480','520','623'])}-555-{random.randint(0,9999):04d}"
    if "account" in n and ("number" in n or "no" in n or n.endswith("account") or "ref" in n):
        # the estate's real format — and the one Workshop 5's pattern and
        # Workshop 6's standard teach: AWC-<2-3 letter system code>-<6 digits>.
        # row_i keeps the UNIQUE constraint honest across top-ups (a top-up's
        # row_i continues from the max PK, so 100000+row_i never collides with
        # the repaired 100000+customer_id refs already on the estate).
        return f"AWC-{random.choice(SYS_CODES)}-{100000 + row_i:06d}"
    if "meter" in n and ("id" in n or "no" in n or "number" in n):
        # the estate's meter format: 2 letters + 6 digits. Without a rule the
        # column fell to the generic text fallback (2 letters + 4 digits) and
        # the profiler induced a UNION of the two shapes — a pattern that
        # describes the seeder rather than the business
        return "".join(random.choices(string.ascii_uppercase, k=2)) + f"{100000 + row_i:06d}"
    if "zip" in n or "postal" in n:
        return f"{85001 + random.randint(0,80):05d}"
    if ("first" in n and "name" in n):
        return random.choice(FIRST)
    if ("last" in n and "name" in n):
        return random.choice(LAST)
    if "name" in n and ("customer" in n or "account" in n or "holder" in n):
        return f"{random.choice(FIRST)} {random.choice(LAST)}"
    if "name" in n and "system" in n:
        # row_i-derived: system_name carries a UNIQUE constraint, and a
        # random 1..40 draw collides with existing rows and itself
        return f"{random.choice(CITIES)} System {row_i}"
    if "name" in n:
        return f"{random.choice(FIRST)} {random.choice(LAST)}"
    if "address" in n:
        return f"{100+row_i} {random.choice(STREETS)}"
    # ESTATE VOCABULARIES — the twelve columns that used to fall through to the
    # generic text fallback and share one shape. Each answers with the words
    # the original rows use, so a reseed cannot drift the governed vocabulary.
    if "county" in n:
        # agree with the city on this row where we generated one
        city = row.get("service_city") or row.get("city") or row.get("billing_city")
        return CITY_COUNTY.get(city) or random.choice(COUNTIES)
    if "severity" in n:
        return random.choice(SEVERITY)
    if "contaminant" in n:
        # varchar contaminant_level is a qualitative band, not a ppm reading
        return random.choice(CONTAM_LEVEL) if txt else round(random.uniform(0, 15), 2)
    if "system_type" in n or ("type" in n and "system" in n):
        return random.choice(SYSTEM_TYPE)
    if "source_type" in n or ("type" in n and "source" in n):
        return random.choice(SOURCE_TYPE)
    if "source" in n:                          # primary_source, water_source
        return random.choice(PRIMARY_SOURCE)
    if "conservation" in n:
        return random.choice(CONSERVATION_FOCUS)
    if "note" in n:
        return random.choice(QUALITY_NOTE).format(sys=random.choice(CITIES))
    if "description" in n or "summary" in n:
        return random.choice(ALERT_DESC).format(
            yr=2026, amt=f"{random.uniform(60, 800):.2f}",
            gal=f"{random.randrange(80, 530) * 1000:,}", sys=random.choice(CITIES))
    if "action" in n or "remediation" in n or "resolution" in n:
        return random.choice(ALERT_ACTION)
    if "cities" in n:                          # a service area lists several
        return ", ".join(random.sample(CITIES, random.randint(2, 4)))
    if n.endswith("_system"):                  # service_area_system = "Bisbee System"
        return f"{random.choice(CITIES)} System"
    # rate_period names a billing YEAR — it reached the money rule below and
    # came back '84.47', a period column full of dollar amounts
    if "period" in n:
        return str(random.choice([2024, 2025, 2026])) if txt else random.choice([2024, 2025, 2026])
    # numeric name-driven (before categorical text, so 'capacity' isn't caught by 'city')
    if "ph_level" in n or n == "ph" or n.endswith("_ph"):
        return round(random.uniform(6.5, 8.6), 2)
    if "lead" in n:
        return round(random.uniform(0, 15), 2)
    if "turbidity" in n:
        return round(random.uniform(0, 2), 2)
    # drinking-water chemistry has REAL ranges, and a profiler reports them:
    # the generic numeric fallback drew 0..1000 and gave the estate 668 mg/L
    # of chlorine residual (EPA's limit is 4) and 8089 ppm of dissolved solids
    if "chlorine" in n:
        return round(random.uniform(0.2, 4.0), 2)
    if "copper" in n:
        return round(random.uniform(0, 1.3), 2)
    if "hardness" in n:
        return random.randint(50, 400)
    if "dissolved" in n:
        return random.randint(150, 900)
    if "capacity" in n:
        return round(random.uniform(5, 50), 2)
    if "number_of_customers" in n or ("customer" in n and "number" in n and "int" in t):
        return random.randint(400, 20000)
    if "population" in n:                       # more people than connections
        cust = row.get("number_of_customers")
        return int(cust * random.uniform(2.2, 3.2)) if cust else random.randint(1200, 60000)
    # tiered_rates is a RATE CARD: tier N starts where tier N-1 stopped. The
    # gallons rule drew each edge independently, so from > to on most rows and
    # the four tiers described no ladder at all
    tier = _tier(n)
    if tier and "gallon" in n and "from" in n:
        return TIER_EDGE[tier - 1]
    if tier and "gallon" in n and "_to" in n:
        return TIER_EDGE[tier]
    if tier and "rate" in n:
        return round(TIER_RATE[tier - 1] + random.uniform(-0.2, 0.2), 2)
    if "tier" in n and "rate" in n:            # tier_rate: dollars per 1000 gal
        return round(random.choice(TIER_RATE) + random.uniform(-0.2, 0.2), 2)
    # a monthly bill's tier gallons SPLIT that row's usage across the ladder
    if tier and "gallon" in n and "usage" in n and row.get("usage_gallons"):
        used = row["usage_gallons"]
        return max(0, min(used, TIER_EDGE[tier]) - TIER_EDGE[tier - 1])
    if ("gallon" in n or "consumption" in n or ("usage" in n and ("int" in t or "numeric" in t))):
        return random.randint(500, 25000)
    # A BILL THAT ADDS UP. Every money column drew independently from
    # uniform(10, 500), so total_due bore no relation to the tier charges
    # above it and amount_paid none to either — a billing table no reconciling
    # rule can be written against.
    if tier and "charge" in n and row.get(f"usage_tier_{tier}_gallons") is not None:
        return round(row[f"usage_tier_{tier}_gallons"] / 1000.0 * TIER_RATE[tier - 1], 2)
    if n == "base_charge":
        return round(random.uniform(14, 28), 2)
    if "wastewater" in n and "charge" in n:
        return round(random.uniform(18, 45), 2)
    if "before_tax" in n or n == "subtotal":
        parts = [row.get("base_charge") or 0, row.get("wastewater_charge") or 0]
        parts += [row.get(f"tier_{i}_charge") or 0 for i in range(1, 5)]
        return round(sum(float(p) for p in parts), 2) or round(random.uniform(20, 300), 2)
    if "tax" in n and "amount" in n:
        return round(float(row.get("total_before_tax") or random.uniform(20, 300)) * 0.086, 2)
    if "total_due" in n or n == "total":
        return round(float(row.get("total_before_tax") or random.uniform(20, 300))
                     + float(row.get("tax_amount") or 0), 2)
    if "amount_paid" in n or ("paid" in n and ("numeric" in t or "double" in t)):
        due = float(row.get("total_due") or random.uniform(20, 300))
        status = str(row.get("payment_status") or "").lower()
        if status == "paid":
            return round(due, 2)
        if status == "overdue":
            return round(due * random.choice([0, 0, 0.5]), 2)
        return 0
    # money only where money fits: 'rate' matched rate_id (an integer PK) and
    # rate_period (a varchar year), and both got a dollar amount
    if (("rate" in n or "amount" in n or "balance" in n or "price" in n or "cost" in n)
            and ("numeric" in t or "double" in t or "real" in t or "decimal" in t)):
        return round(random.uniform(10, 500), 2)
    if "rating" in n or "score" in n:
        # TEXT takes the label scale, NUMERIC takes 1..5. randint into a
        # varchar quality_rating left the estate's vocabulary reading
        # '1;2;3;4;5;Excellent;Good;Fair' — a scale mixed with labels, which
        # is why a dictionary built from it matched nothing
        return random.choice(RATING_LABEL) if txt else random.randint(1, 5)
    if "month" in n and ("date" in t or "timestamp" in t):
        return _rand_date(365, 365)
    # TYPE WINS for temporal columns before any categorical NAME rule: a
    # last_compliance_check DATE matched the "compliance" name rule and
    # received the word 'compliant' (field-caught on the scale-up seed)
    if "timestamp" in t:
        return datetime.datetime.now() - datetime.timedelta(days=random.randint(0, 400),
                                                            seconds=random.randint(0, 86400))
    if "date" in t:
        return _rand_date()
    # categorical text
    if "city" in n or "cities" in n:
        return random.choice(CITIES)
    if "area" in n or "region" in n or "zone" in n:
        return random.choice(CITIES)
    if "payment" in n and "status" in n:        # a bill is Paid/Unpaid/Overdue,
        return random.choice(PAY_STATUS)        # never 'suspended'
    if "status" in n and "compl" in n:
        return random.choice(COMPLIANCE)
    if "compliance" in n:
        return random.choice(COMPLIANCE)
    if "status" in n:
        return random.choice(STATUS)
    if "type" in n and ("cust" in n or "account" in n):
        return random.choice(CUST_TYPE)
    if "alert" in n and ("type" in n or "kind" in n):
        return random.choice(ALERT_TYPE)
    # type-driven fallback
    if "timestamp" in t:
        return datetime.datetime.now() - datetime.timedelta(days=random.randint(0, 400),
                                                             seconds=random.randint(0, 86400))
    if "date" in t:
        return _rand_date()
    if "bool" in t:
        return random.choice([True, False])
    if "int" in t or "serial" in t:
        return random.randint(1, 10000)
    if "numeric" in t or "double" in t or "real" in t or "decimal" in t:
        return round(random.uniform(0, 1000), 2)
    if txt:
        # NEVER one shape for every unnamed text column. The old fallback —
        # two uppercase letters + row_i — gave twelve unrelated columns the
        # identical ^[A-Z]{2}[0-9]{4}$, so the profiler induced one pattern
        # that backed every one of those concepts and bound free-text `notes`
        # to all of them. Anchoring the value to the COLUMN NAME keeps each
        # column's shape its own, and says in the data that it is filler.
        stem = re.sub(r"[^A-Za-z0-9]+", "-", colname).strip("-").upper()
        return f"{stem}-{row_i:06d}"
    return None


def _introspect(cur, schema):
    # BASE TABLEs only: information_schema.columns also lists VIEWS, and a
    # GROUP BY view (customer_billing_summary) is not insertable — the seed
    # died mid-run trying (field-caught on the scale-up)
    cur.execute("""SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
                          c.column_default, c.numeric_precision, c.numeric_scale,
                          c.character_maximum_length
                   FROM information_schema.columns c
                   JOIN information_schema.tables t
                     ON t.table_schema=c.table_schema AND t.table_name=c.table_name
                   WHERE c.table_schema=%s AND t.table_type='BASE TABLE'
                   ORDER BY c.table_name, c.ordinal_position""", (schema,))
    tables = {}
    for tn, cn, dt, nullable, default, prec, scale, maxlen in cur.fetchall():
        tables.setdefault(tn, {"cols": [], "pk": [], "fk": {}})
        is_serial = bool(default and "nextval" in str(default))
        tables[tn]["cols"].append({"name": cn, "type": dt, "nullable": nullable == "YES",
                                   "serial": is_serial, "prec": prec, "scale": scale,
                                   "maxlen": maxlen})
    cur.execute("""SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                          ccu.table_name AS ref_table, ccu.column_name AS ref_col
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu
                     ON kcu.constraint_name=tc.constraint_name AND kcu.table_schema=tc.table_schema
                   LEFT JOIN information_schema.constraint_column_usage ccu
                     ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema
                   WHERE tc.table_schema=%s AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')""",
                (schema,))
    for tn, cn, ctype, rt, rc in cur.fetchall():
        if tn not in tables:
            continue
        if ctype == "PRIMARY KEY":
            tables[tn]["pk"].append(cn)
        elif ctype == "FOREIGN KEY":
            tables[tn]["fk"][cn] = (rt, rc)
    return tables


def _topo(tables):
    order, seen = [], set()
    def visit(t, stack):
        if t in seen or t not in tables:
            return
        for _, (rt, _rc) in tables[t]["fk"].items():
            if rt != t and rt not in stack:
                visit(rt, stack | {t})
        seen.add(t); order.append(t)
    for t in tables:
        visit(t, {t})
    return order


def plan(cfg, only_empty=True, schema=None):
    """Which tables a seed WOULD write to, without writing anything.

    Read-only: introspect, count rows, apply the same only_empty rule the real
    run does. Exists so a person can be shown the actual table names before
    agreeing - "it only fills empty tables" is a reassurance, whereas
    "it will insert into audit_log and staging_customers" is a decision.
    """
    from sources import dbconn
    schema = schema or cfg.get("schema") or "public"
    conn = dbconn._connect(cfg)
    try:
        with conn.cursor() as cur:
            tables = _introspect(cur, schema)
            targets, skipped = [], []
            for tn in _topo(tables):
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{tn}"')
                count = cur.fetchone()[0]
                (skipped if (only_empty and count > 0) else targets).append(
                    {"table": tn, "existing_rows": count})
        return {"schema": schema, "targets": targets, "skipped": skipped,
                "database": cfg.get("database") or cfg.get("db") or ""}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def seed(cfg, rows=200, only_empty=True, schema=None):
    from sources import dbconn
    schema = schema or cfg.get("schema") or "public"
    conn = dbconn._connect(cfg)
    inserted = []
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            tables = _introspect(cur, schema)
            pk_pool = {}   # table -> list of existing/seeded PK values (single-col PK)
            for tn in tables:
                pk = tables[tn]["pk"]
                if len(pk) == 1:
                    cur.execute(f'SELECT "{pk[0]}" FROM "{schema}"."{tn}"')
                    pk_pool[tn] = [r[0] for r in cur.fetchall()]
            for tn in _topo(tables):
                meta = tables[tn]
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{tn}"')
                count = cur.fetchone()[0]
                if only_empty and count > 0:
                    continue
                gen_cols = [c for c in meta["cols"] if not c["serial"]]
                refs = {col: pk_pool.get(rt, []) for col, (rt, rc) in meta["fk"].items()}
                colnames = [c["name"] for c in gen_cols]
                placeholders = ", ".join(["%s"] * len(colnames))
                collist = ", ".join(f'"{c}"' for c in colnames)
                sql = f'INSERT INTO "{schema}"."{tn}" ({collist}) VALUES ({placeholders})'
                n_rows = rows
                made = 0
                # TOP-UP SAFE: every generated value derives from the loop
                # index, so a --all run over a non-empty table regenerated
                # the ORIGINAL ids (field-caught: customers_pkey 6587).
                # Start above the table's max integer PK — ids, emails and
                # patterned account numbers all shift past the existing rows.
                off = 0
                for v in pk_pool.get(tn, []):
                    try:
                        v = int(v)          # ints arrive as Decimal on numeric PKs
                    except (TypeError, ValueError):
                        continue
                    if v > off:
                        off = v
                pk_col = meta["pk"][0] if len(meta["pk"]) == 1 else None
                for i in range(off + 1, off + n_rows + 1):
                    vals = []
                    skip = False
                    # what this row has generated so far, so a column can agree
                    # with an earlier one (service_county follows service_city)
                    sofar = {}
                    for c in gen_cols:
                        v = _gen(c["name"], c["type"], i, refs, sofar)
                        # a single-col INTEGER PK takes the sequential index
                        # directly (already offset above the existing max):
                        # the generic int fallback draws random 1..10000 and
                        # collides with existing rows AND itself over a
                        # 1000-row run (field-caught: customers_pkey)
                        if (c["name"] == pk_col
                                and ("int" in (c["type"] or "").lower()
                                     or "numeric" in (c["type"] or "").lower())):
                            v = i
                        # respect NUMERIC(p,s): the generic fallback threw
                        # 0..1000 at a NUMERIC(3,2) chlorine column
                        # (field-caught) — clamp to the column's capacity
                        pr, sc = c.get("prec"), c.get("scale")
                        if (pr and isinstance(v, (int, float))
                                and not isinstance(v, bool)):
                            cap = 10 ** (pr - (sc or 0))
                            if abs(v) >= cap:
                                v = round(random.uniform(0, cap * 0.9), sc or 0)
                        # respect varchar(n) the same way: a sentence-length
                        # value in a varchar(20) column kills the whole run
                        ml = c.get("maxlen")
                        if ml and isinstance(v, str) and len(v) > ml:
                            v = v[:ml]
                        if v is None and c["name"] in meta["fk"] and not c["nullable"]:
                            skip = True; break          # FK with no parent rows -> can't insert
                        sofar[c["name"]] = v
                        vals.append(v)
                    if skip:
                        break
                    # constraint-tolerant: a unique constraint on generated
                    # values rolls back THIS row only — the run completes
                    # with a slight shortfall instead of dying at row N
                    cur.execute("SAVEPOINT seedrow")
                    try:
                        cur.execute(sql, vals)
                    except Exception as e:
                        from psycopg2 import errors as _pgerr
                        if isinstance(e, _pgerr.UniqueViolation):
                            cur.execute("ROLLBACK TO SAVEPOINT seedrow")
                            continue
                        raise
                    made += 1
                if made:
                    # refresh PK pool for downstream children
                    pk = meta["pk"]
                    if len(pk) == 1:
                        cur.execute(f'SELECT "{pk[0]}" FROM "{schema}"."{tn}"')
                        pk_pool[tn] = [r[0] for r in cur.fetchall()]
                    inserted.append({"table": tn, "rows": made})
            conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"schema": schema, "inserted": inserted}


# the shape the pre-1.38.35 text fallback minted: two uppercase letters and
# the row index. Five digits at most, so a real 2+6 meter id is never touched.
JUNK_RE = r"^[A-Z]{2}[0-9]{1,5}$"


def repair(cfg, schema=None, pattern=JUNK_RE, apply=False):
    """Rewrite values a previous seed left as shape-collision filler.

    The old text fallback answered twelve unrelated columns with one shape, so
    the estate carried 1000 rows of 'WQ2602' in county, severity, notes and
    contaminant_level alike. This finds values matching that shape and
    regenerates them through the CURRENT rules — using each row's own earlier
    values, so a repaired service_county agrees with its service_city.

    Read-only unless apply=True: the default reports what it would rewrite.
    """
    from sources import dbconn
    schema = schema or cfg.get("schema") or "public"
    conn = dbconn._connect(cfg)
    fixed = []
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            tables = _introspect(cur, schema)
            for tn in sorted(tables):
                meta = tables[tn]
                pk = meta["pk"][0] if len(meta["pk"]) == 1 else None
                for c in meta["cols"]:
                    t = (c["type"] or "").lower()
                    if not ("char" in t or "text" in t):
                        continue
                    cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{tn}" '
                                f'WHERE "{c["name"]}" ~ %s', (pattern,))
                    hits = cur.fetchone()[0]
                    if not hits:
                        continue
                    entry = {"table": tn, "column": c["name"], "rows": hits,
                             "rewritten": 0}
                    fixed.append(entry)
                    if not apply:
                        continue
                    if not pk:
                        entry["skipped"] = "no single-column primary key"
                        continue
                    cur.execute(f'SELECT * FROM "{schema}"."{tn}" '
                                f'WHERE "{c["name"]}" ~ %s', (pattern,))
                    names = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                    for i, r in enumerate(rows, 1):
                        sofar = dict(zip(names, r))
                        key = sofar[pk]
                        try:
                            row_i = int(key)
                        except (TypeError, ValueError):
                            row_i = i
                        v = _gen(c["name"], c["type"], row_i, {}, sofar)
                        ml = c.get("maxlen")
                        if ml and isinstance(v, str) and len(v) > ml:
                            v = v[:ml]
                        cur.execute(f'UPDATE "{schema}"."{tn}" SET "{c["name"]}"=%s '
                                    f'WHERE "{pk}"=%s', (v, key))
                        entry["rewritten"] += 1
        if apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"schema": schema, "applied": bool(apply), "columns": fixed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost"); ap.add_argument("--port", default="5433")
    ap.add_argument("--db", default="sample_db"); ap.add_argument("--schema", default="public")
    # No credential defaults. These were a real lab account and password, in a
    # module api.py imports - so they shipped, and anyone running the tool
    # without arguments was quietly trying somebody else's login.
    ap.add_argument("--user", required=True); ap.add_argument("--password", required=True)
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--all", action="store_true", help="also top up non-empty tables")
    ap.add_argument("--repair", action="store_true",
                    help="rewrite shape-collision filler an earlier seed left behind "
                         "(reports only; add --apply to write)")
    ap.add_argument("--pattern", default=JUNK_RE, help=f"filler shape to repair (default {JUNK_RE})")
    ap.add_argument("--apply", action="store_true", help="with --repair: actually UPDATE")
    a = ap.parse_args()
    cfg = {"engine": "postgresql", "host": a.host, "port": a.port, "database": a.db,
           "schema": a.schema, "user": a.user, "password": a.password}
    if a.repair:
        rep = repair(cfg, schema=a.schema, pattern=a.pattern, apply=a.apply)
        if not rep["columns"]:
            print(f"No values matching {a.pattern} in schema {a.schema}.")
        for e in rep["columns"]:
            verb = f'rewrote {e["rewritten"]}' if a.apply else f'would rewrite {e["rows"]}'
            print(f'{e["table"]}.{e["column"]}: {verb}'
                  + (f' - SKIPPED ({e["skipped"]})' if e.get("skipped") else ""))
        if rep["columns"] and not a.apply:
            print("\nReport only - nothing was written. Re-run with --apply to repair.")
    else:
        rep = seed(cfg, rows=a.rows, only_empty=not a.all)
        print("Seeded:", rep["inserted"] or "nothing (tables already populated; use --all to top up)")
