"""
seed_sample.py - populate a PostgreSQL schema with realistic sample data
so data-profiling has real values to detect (PII, patterns, cardinality).

It introspects the live schema (information_schema), orders tables by foreign-key
dependencies, skips auto-generated keys, references parent PKs for FK columns, and
generates values by column name + type. By default it only fills EMPTY tables.

CLI:   python seed_sample.py --host localhost --port 5433 --db your_db \
                          --user pdc_user --password 'catalog123!' --rows 200
API:   from seed_sample import seed ; seed(cfg, rows=200)
"""
import random, datetime, string, argparse

FIRST = ["Maria", "Robert", "Susan", "David", "John", "Emma", "Luis", "Anna", "James",
         "Olivia", "Carlos", "Linda", "Michael", "Sofia", "Daniel", "Grace"]
LAST = ["Garcia", "Hayes", "Park", "Chen", "Smith", "Brown", "Diaz", "Lee", "Johnson",
        "Martinez", "Nguyen", "Patel", "Wilson", "Khan", "Rivera", "Clark"]
STREETS = ["Main St", "Oak Ave", "Elm Dr", "Pine Rd", "Maple Ln", "Cedar Ct", "Sunset Blvd",
           "Desert Way", "Canyon Rd", "Mesa Dr"]
CITIES = ["Phoenix", "Tucson", "Mesa", "Tempe", "Chandler", "Scottsdale", "Glendale"]
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
    if "account" in n and ("number" in n or "no" in n or n.endswith("account")):
        return "ACC" + f"{row_i:08d}"
    if "zip" in n or "postal" in n:
        return f"{85001 + random.randint(0,80):05d}"
    if ("first" in n and "name" in n):
        return random.choice(FIRST)
    if ("last" in n and "name" in n):
        return random.choice(LAST)
    if "name" in n and ("customer" in n or "account" in n or "holder" in n):
        return f"{random.choice(FIRST)} {random.choice(LAST)}"
    if "name" in n and "system" in n:
        return f"{random.choice(CITIES)} System {random.randint(1,40)}"
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
    cur.execute("""SELECT table_name, column_name, data_type, is_nullable, column_default
                   FROM information_schema.columns WHERE table_schema=%s
                   ORDER BY table_name, ordinal_position""", (schema,))
    tables = {}
    for tn, cn, dt, nullable, default in cur.fetchall():
        tables.setdefault(tn, {"cols": [], "pk": [], "fk": {}})
        is_serial = bool(default and "nextval" in str(default))
        tables[tn]["cols"].append({"name": cn, "type": dt, "nullable": nullable == "YES",
                                   "serial": is_serial})
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


def seed(cfg, rows=200, only_empty=True, schema=None):
    import dbconn
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
                for i in range(1, n_rows + 1):
                    vals = []
                    skip = False
                    for c in gen_cols:
                        v = _gen(c["name"], c["type"], i, refs)
                        if v is None and c["name"] in meta["fk"] and not c["nullable"]:
                            skip = True; break          # FK with no parent rows -> can't insert
                        vals.append(v)
                    if skip:
                        break
                    cur.execute(sql, vals)
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
    ap.add_argument("--user", default="pdc_user"); ap.add_argument("--password", default="catalog123!")
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--all", action="store_true", help="also top up non-empty tables")
    a = ap.parse_args()
    cfg = {"engine": "postgresql", "host": a.host, "port": a.port, "database": a.db,
           "schema": a.schema, "user": a.user, "password": a.password}
    rep = seed(cfg, rows=a.rows, only_empty=not a.all)
    print("Seeded:", rep["inserted"] or "nothing (tables already populated; use --all to top up)")
