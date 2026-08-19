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
import random, datetime, string, argparse

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


def _rand_date(start_days=2000, span=1800):
    return datetime.date.today() - datetime.timedelta(days=random.randint(0, start_days)) \
        + datetime.timedelta(days=random.randint(0, span) - span)


def _gen(colname, dtype, row_i, refs):
    """Generate one value for a column based on its name and SQL type."""
    n = colname.lower()
    t = (dtype or "").lower()
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
    # numeric name-driven (before categorical text, so 'capacity' isn't caught by 'city')
    if "ph_level" in n or n == "ph" or n.endswith("_ph"):
        return round(random.uniform(6.5, 8.6), 2)
    if "lead" in n:
        return round(random.uniform(0, 15), 2)
    if "turbidity" in n:
        return round(random.uniform(0, 2), 2)
    if "capacity" in n:
        return round(random.uniform(5, 50), 2)
    if ("gallon" in n or "consumption" in n or ("usage" in n and ("int" in t or "numeric" in t))):
        return random.randint(500, 25000)
    if "rate" in n or "amount" in n or "balance" in n or "price" in n or "cost" in n:
        return round(random.uniform(10, 500), 2)
    if "rating" in n or "score" in n:
        return random.randint(1, 5)
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
    if "char" in t or "text" in t:
        return "".join(random.choices(string.ascii_uppercase, k=2)) + str(row_i)
    return None


def _introspect(cur, schema):
    # BASE TABLEs only: information_schema.columns also lists VIEWS, and a
    # GROUP BY view (customer_billing_summary) is not insertable — the seed
    # died mid-run trying (field-caught on the scale-up)
    cur.execute("""SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
                          c.column_default, c.numeric_precision, c.numeric_scale
                   FROM information_schema.columns c
                   JOIN information_schema.tables t
                     ON t.table_schema=c.table_schema AND t.table_name=c.table_name
                   WHERE c.table_schema=%s AND t.table_type='BASE TABLE'
                   ORDER BY c.table_name, c.ordinal_position""", (schema,))
    tables = {}
    for tn, cn, dt, nullable, default, prec, scale in cur.fetchall():
        tables.setdefault(tn, {"cols": [], "pk": [], "fk": {}})
        is_serial = bool(default and "nextval" in str(default))
        tables[tn]["cols"].append({"name": cn, "type": dt, "nullable": nullable == "YES",
                                   "serial": is_serial, "prec": prec, "scale": scale})
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
                    for c in gen_cols:
                        v = _gen(c["name"], c["type"], i, refs)
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
                        if v is None and c["name"] in meta["fk"] and not c["nullable"]:
                            skip = True; break          # FK with no parent rows -> can't insert
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
    a = ap.parse_args()
    cfg = {"engine": "postgresql", "host": a.host, "port": a.port, "database": a.db,
           "schema": a.schema, "user": a.user, "password": a.password}
    rep = seed(cfg, rows=a.rows, only_empty=not a.all)
    print("Seeded:", rep["inserted"] or "nothing (tables already populated; use --all to top up)")
