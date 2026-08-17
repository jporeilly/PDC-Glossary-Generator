"""Relational harvest - DDL/live schema walk, keys, graph, sampling.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS

# ----------------------------------------------------------------- HARVEST
def harvest_ddl(path):
    """Parse a .sql DDL file into {table: [column dicts]} for offline scanning."""
    sql = open(path, encoding="utf-8").read()
    return harvest_ddl_text(sql)

def harvest_ddl_text(sql):
    """Parse DDL text (CREATE TABLE statements) into {table: [column dicts]},
       including foreign-key targets from inline `REFERENCES t(c)` and table-level
       `FOREIGN KEY (c) REFERENCES t(c)` so relationship edges can be drawn."""
    tables = {}
    ref_inline = re.compile(r"REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)", re.I)
    fk_tablelevel = re.compile(
        r"FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s*REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)", re.I)
    for m in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\n\)\s*;", sql, re.S | re.I):
        tname, body = m.group(1), m.group(2)
        cols = []
        tbl_fks = {}  # column -> (ref_table, ref_col) from table-level constraints
        for fm in fk_tablelevel.finditer(body):
            tbl_fks[fm.group(1)] = (fm.group(2), fm.group(3))
        for raw in body.split("\n"):
            line = raw.strip().rstrip(",")
            if not line:
                continue
            comment = ""
            if "--" in line:
                line, comment = line.split("--", 1)
                line, comment = line.strip().rstrip(","), comment.strip()
            parts = line.split()
            if len(parts) < 2:
                continue
            col = parts[0]
            if col.upper() in {"PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK", "REFERENCES"}:
                continue
            up = line.upper()
            ref = ref_inline.search(line)
            ref_table = ref.group(1) if ref else None
            ref_col = ref.group(2) if ref else None
            cols.append({"table": tname, "column": col, "type": parts[1],
                         "pk": "PRIMARY KEY" in up, "fk": "REFERENCES" in up,
                         "ref_table": ref_table, "ref_col": ref_col,
                         "notnull": "NOT NULL" in up, "unique": "UNIQUE" in up,
                         "comment": comment})
        # apply table-level FK constraints to their columns
        for c in cols:
            if c["column"] in tbl_fks:
                c["fk"] = True
                c["ref_table"], c["ref_col"] = tbl_fks[c["column"]]
        if cols:
            tables[tname] = cols
    return tables

def _harvest_oracle(conn, owner):
    """Oracle live scan. Oracle has no information_schema — the metadata lives in
    the ALL_* dictionary views — and python-oracledb uses :name binds, not %s.
    `owner` is the schema (Oracle schema == user, usually uppercase). Requires only
    SELECT on the dictionary views every account already has for its own objects."""
    tables = {}
    with conn.cursor() as cur:
        # columns (skip recycle-bin and system-generated $ objects)
        cur.execute(
            """SELECT table_name, column_name, data_type, column_id, nullable
               FROM all_tab_columns
               WHERE owner = :o
                 AND table_name NOT LIKE 'BIN$%'
                 AND table_name NOT LIKE '%$%'
               ORDER BY table_name, column_id""", o=owner)
        colrows = cur.fetchall()
        # primary keys
        cur.execute(
            """SELECT acc.table_name, acc.column_name
               FROM all_constraints ac
               JOIN all_cons_columns acc
                 ON acc.owner = ac.owner AND acc.constraint_name = ac.constraint_name
               WHERE ac.constraint_type = 'P' AND ac.owner = :o""", o=owner)
        pks = {(t, c) for t, c in cur.fetchall()}
        # foreign keys + their targets, position-aligned (handles composite keys)
        cur.execute(
            """SELECT a.table_name, a.column_name, pk.table_name, b.column_name
               FROM all_constraints c
               JOIN all_cons_columns a
                 ON a.owner = c.owner AND a.constraint_name = c.constraint_name
               JOIN all_constraints pk
                 ON pk.owner = c.r_owner AND pk.constraint_name = c.r_constraint_name
               JOIN all_cons_columns b
                 ON b.owner = pk.owner AND b.constraint_name = pk.constraint_name
                AND b.position = a.position
               WHERE c.constraint_type = 'R' AND c.owner = :o""", o=owner)
        fks, fkref = set(), {}
        for t, c, rt, rc in cur.fetchall():
            fks.add((t, c))
            fkref[(t, c)] = (rt, rc)
        # column comments
        cur.execute(
            """SELECT table_name, column_name, comments
               FROM all_col_comments
               WHERE owner = :o AND comments IS NOT NULL""", o=owner)
        comments = {(t, col): desc for t, col, desc in cur.fetchall()}
    for t, col, dt, pos, nullable in colrows:
        ref = fkref.get((t, col))
        tables.setdefault(t, []).append(
            {"table": t, "column": col, "type": dt,
             "pk": (t, col) in pks, "fk": (t, col) in fks,
             "ref_table": ref[0] if ref else None,
             "ref_col": ref[1] if ref else None,
             "notnull": (nullable == "N"), "unique": False,
             "comment": comments.get((t, col), "") or ""})
    return tables

def _inherit_view_keys(tables, views, pks, fks, fkref):
    """Views can't declare constraints, but information_schema.columns lists
    them like tables — so a summary view's re-exposed id column arrives
    key-less and dodges the structural prune. A view column that name-matches
    a KEY column of a scanned BASE table is a passthrough of that key, not a
    new business term: inherit the key flag (as an FK reference to the key's
    home — a PK match wins; an FK match resolves to ITS referenced column)."""
    key_home = {}
    for (t, c) in fks:
        if t not in views:
            key_home.setdefault(c, fkref.get((t, c)) or (t, c))
    for (t, c) in pks:
        if t not in views:
            key_home[c] = (t, c)          # PK owner is the canonical home
    for v in views:
        for col in tables.get(v, []):
            home = key_home.get(col["column"])
            if home and not (col["pk"] or col["fk"]):
                col["fk"] = True
                col["ref_table"], col["ref_col"] = home


def harvest_live(cfg, schema=None):
    """Live scan via a Python DB-API driver (see dbconn.py). cfg is a dict:
       {engine, host, port, database, schema, user, password, ssl}.
       Reads columns + keys + comments from information_schema (pg/mysql/mssql)
       or the ALL_* dictionary views (oracle — schema/owner defaults to the
       connecting user, uppercased)."""
    from sources import dbconn
    eng = cfg.get("engine", "postgresql")
    schema = schema or cfg.get("schema") or ("public" if eng == "postgresql" else None)
    conn = dbconn._connect(cfg)
    tables = {}
    try:
        if eng == "oracle":
            owner = (schema or cfg.get("user") or "").strip().upper()
            if not owner:
                raise ValueError("Oracle scan needs a schema (owner) or a user to derive it from")
            return _harvest_oracle(conn, owner)
        with conn.cursor() as cur:
            # columns
            cur.execute(
                """SELECT table_name, column_name, data_type, ordinal_position,
                          (is_nullable='NO')
                   FROM information_schema.columns
                   WHERE table_schema = %s
                   ORDER BY table_name, ordinal_position""",
                (schema,))
            colrows = cur.fetchall()
            pks = fks = fkref = None
            if eng == "postgresql":
                # PRIMARY: read keys from pg_catalog, NOT information_schema. The
                # information_schema key views (key_column_usage / table_constraints)
                # are privilege-filtered and frequently come back EMPTY for a
                # connection user that can read columns but doesn't own the tables —
                # which is exactly why the diagram showed 0 PK / 0 FK. pg_catalog is
                # authoritative and reflects the constraints regardless of ownership.
                try:
                    cur.execute(
                        """SELECT c.relname, a.attname
                           FROM pg_index i
                           JOIN pg_class c ON c.oid = i.indrelid
                           JOIN pg_namespace n ON n.oid = c.relnamespace
                           JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
                           WHERE i.indisprimary AND n.nspname = %s""",
                        (schema,))
                    pks = {(t, c) for t, c in cur.fetchall()}
                    # FKs + their targets, column-aligned (handles composite keys),
                    # using generate_subscripts (older/portable) rather than multi-unnest.
                    cur.execute(
                        """SELECT c.relname, a.attname, cf.relname, af.attname
                           FROM pg_constraint con
                           JOIN pg_class c  ON c.oid  = con.conrelid
                           JOIN pg_namespace n ON n.oid = c.relnamespace
                           JOIN pg_class cf ON cf.oid = con.confrelid
                           JOIN generate_subscripts(con.conkey, 1) AS gs(i) ON true
                           JOIN pg_attribute a  ON a.attrelid  = con.conrelid  AND a.attnum  = con.conkey[gs.i]
                           JOIN pg_attribute af ON af.attrelid = con.confrelid AND af.attnum = con.confkey[gs.i]
                           WHERE con.contype = 'f' AND n.nspname = %s""",
                        (schema,))
                    fks, fkref = set(), {}
                    for t, c, rt, rc in cur.fetchall():
                        fks.add((t, c))
                        fkref[(t, c)] = (rt, rc)
                except Exception:
                    try:
                        conn.rollback()  # clear any aborted tx so the fallback can run
                    except Exception:
                        pass
                    pks = fks = fkref = None  # fall back to information_schema below
            if pks is None:
                # information_schema fallback (other engines, or if pg_catalog failed)
                cur.execute(
                    """SELECT kcu.table_name, kcu.column_name
                       FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage kcu
                         ON kcu.constraint_name = tc.constraint_name
                        AND kcu.table_schema = tc.table_schema
                       WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s""",
                    (schema,))
                pks = {(t, c) for t, c in cur.fetchall()}
                cur.execute(
                    """SELECT kcu.table_name, kcu.column_name
                       FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage kcu
                         ON kcu.constraint_name = tc.constraint_name
                        AND kcu.table_schema = tc.table_schema
                       WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s""",
                    (schema,))
                fks = {(t, c) for t, c in cur.fetchall()}
                fkref = {}
                try:
                    cur.execute(
                        """SELECT kcu.table_name, kcu.column_name,
                                  ccu.table_name AS ref_table, ccu.column_name AS ref_col
                           FROM information_schema.table_constraints tc
                           JOIN information_schema.key_column_usage kcu
                             ON kcu.constraint_name = tc.constraint_name
                            AND kcu.table_schema = tc.table_schema
                           JOIN information_schema.constraint_column_usage ccu
                             ON ccu.constraint_name = tc.constraint_name
                            AND ccu.table_schema = tc.table_schema
                           WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s""",
                        (schema,))
                    fkref = {(t, c): (rt, rc) for t, c, rt, rc in cur.fetchall()}
                except Exception:
                    fkref = {}
            # column comments (PostgreSQL)
            comments = {}
            if eng == "postgresql":
                cur.execute(
                    """SELECT c.relname, a.attname, d.description
                       FROM pg_description d
                       JOIN pg_class c ON c.oid = d.objoid
                       JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = %s AND d.objsubid > 0""",
                    (schema,))
                comments = {(t, col): desc for t, col, desc in cur.fetchall()}
        for t, col, dt, pos, notnull in colrows:
            ref = fkref.get((t, col))
            tables.setdefault(t, []).append(
                {"table": t, "column": col, "type": dt,
                 "pk": (t, col) in pks, "fk": (t, col) in fks,
                 "ref_table": ref[0] if ref else None,
                 "ref_col": ref[1] if ref else None,
                 "notnull": bool(notnull), "unique": False,
                 "comment": comments.get((t, col), "") or ""})
        if eng == "postgresql" and (pks or fks):
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT c.relname FROM pg_class c
                           JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = %s AND c.relkind IN ('v', 'm')""",
                        (schema,))
                    views = {r[0] for r in cur.fetchall()}
                _inherit_view_keys(tables, views, pks, fks, fkref or {})
            except Exception:
                pass  # best-effort: without relkind info, views scan as before
    finally:
        conn.close()
    return tables

def schema_graph(tables):
    """Shape scanned {table: [col dicts]} into an ER graph for the diagram:
       tables[{name, columns[{name,type,pk,fk,notnull,ref_table,ref_col}], pk_count,
       fk_count}] and relationships[{from,from_col,to,to_col}] (only FKs whose target
       table is present in the scan are marked resolved)."""
    names = set(tables.keys())
    out_tables, rels = [], []
    for tname, cols in tables.items():
        out_cols = []
        for c in cols:
            out_cols.append({
                "name": c.get("column"), "type": c.get("type", ""),
                "pk": bool(c.get("pk")), "fk": bool(c.get("fk")),
                "notnull": bool(c.get("notnull")),
                "ref_table": c.get("ref_table"), "ref_col": c.get("ref_col"),
                "comment": c.get("comment", "") or ""})
            if c.get("fk") and c.get("ref_table"):
                rels.append({"from": tname, "from_col": c.get("column"),
                             "to": c.get("ref_table"), "to_col": c.get("ref_col"),
                             "resolved": c.get("ref_table") in names})
        out_tables.append({
            "name": tname, "columns": out_cols,
            "pk_count": sum(1 for x in out_cols if x["pk"]),
            "fk_count": sum(1 for x in out_cols if x["fk"]),
            "col_count": len(out_cols)})
    out_tables.sort(key=lambda t: t["name"])
    return {"tables": out_tables, "relationships": rels,
            "table_count": len(out_tables),
            "rel_count": sum(1 for r in rels if r["resolved"])}


def keymap_from_tables(tables):
    """Reduce scanned {table: [col dicts]} to the keys we'd want set on the DB:
       {table: {pk:[cols], fks:[{col, ref_table, ref_col}]}}."""
    km = {}
    for tname, cols in tables.items():
        pk = [c["column"] for c in cols if c.get("pk")]
        fks = [{"col": c["column"], "ref_table": c.get("ref_table"), "ref_col": c.get("ref_col")}
               for c in cols if c.get("fk") and c.get("ref_table") and c.get("ref_col")]
        if pk or fks:
            km[tname] = {"pk": pk, "fks": fks}
    return km


def sample_distinct_values(cfg, sources, limit=200):
    """Live-data probe for the duplicate-group recommender: sample up to `limit`
       DISTINCT non-null values for each 'schema.table.column' source. Direct
       value overlap between two same-named columns is the strongest same-vs-
       different-concept evidence there is (better than cached profile shapes,
       because it compares the actual populations). Returns {source: [values]};
       sources that fail to read are simply absent. Postgres/MySQL/MSSQL via
       dbconn (Oracle uses FETCH FIRST)."""
    from sources import dbconn
    eng = cfg.get("engine", "postgresql")
    conn = dbconn._connect(cfg)
    out = {}
    try:
        with conn.cursor() as cur:
            for src in sources or []:
                bits = str(src).strip().split(".")
                if len(bits) < 3:
                    continue
                schema, table, col = bits[-3], bits[-2], bits[-1]
                if not all(re.fullmatch(r"[A-Za-z0-9_$]+", x) for x in (schema, table, col)):
                    continue                      # identifiers only — never quote-inject
                n = max(1, min(int(limit), 1000))
                if eng == "oracle":
                    q = (f'SELECT DISTINCT "{col.upper()}" FROM "{schema.upper()}"."{table.upper()}" '
                         f'WHERE "{col.upper()}" IS NOT NULL FETCH FIRST {n} ROWS ONLY')
                else:
                    q = (f'SELECT DISTINCT "{col}" FROM "{schema}"."{table}" '
                         f'WHERE "{col}" IS NOT NULL LIMIT {n}')
                try:
                    cur.execute(q)
                    out[src] = [str(r[0]) for r in cur.fetchall()]
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return out


def apply_keys_live(cfg, schema, keymap, dry_run=True):
    """Add the PRIMARY KEY / FOREIGN KEY constraints in `keymap` to a live PostgreSQL
       schema via ALTER TABLE, so PDC's catalog ingest (and our own scan) can read
       them. Idempotent: existing keys are skipped. Each statement runs in its own
       sub-transaction so one failure (e.g. an orphan FK value) doesn't block the
       rest. Returns a per-statement report; dry_run just returns the planned SQL."""
    from sources import dbconn
    eng = cfg.get("engine", "postgresql")
    schema = schema or cfg.get("schema") or "public"
    if eng != "postgresql":
        raise RuntimeError("Writing keys is currently supported for PostgreSQL only.")
    conn = dbconn._connect(cfg)
    stmts = []
    skipped_pk = skipped_fk = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.relname FROM pg_constraint con
                   JOIN pg_class c ON c.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE con.contype='p' AND n.nspname=%s""", (schema,))
            haspk = {r[0] for r in cur.fetchall()}
            cur.execute(
                """SELECT c.relname, a.attname FROM pg_constraint con
                   JOIN pg_class c ON c.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   JOIN generate_subscripts(con.conkey, 1) AS gs(i) ON true
                   JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[gs.i]
                   WHERE con.contype='f' AND n.nspname=%s""", (schema,))
            fkcols = {(t, c) for t, c in cur.fetchall()}
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (schema,))
            existing = {r[0] for r in cur.fetchall()}

            def q(t):
                return '"%s"."%s"' % (schema, t)

            plan = []
            for t, km in keymap.items():
                if t not in existing:
                    continue
                if km["pk"]:
                    if t in haspk:
                        skipped_pk += 1
                    else:
                        cols = ", ".join('"%s"' % c for c in km["pk"])
                        plan.append(("pk", t, 'ALTER TABLE %s ADD PRIMARY KEY (%s)' % (q(t), cols)))
                for fk in km["fks"]:
                    if fk["ref_table"] not in existing:
                        continue
                    if (t, fk["col"]) in fkcols:
                        skipped_fk += 1
                        continue
                    cn = "%s_%s_fkey" % (t, fk["col"])
                    plan.append(("fk", t, 'ALTER TABLE %s ADD CONSTRAINT "%s" FOREIGN KEY ("%s") REFERENCES %s ("%s")'
                                 % (q(t), cn, fk["col"], q(fk["ref_table"]), fk["ref_col"])))

            if dry_run:
                for kind, t, sql in plan:
                    stmts.append({"kind": kind, "table": t, "sql": sql, "status": "pending"})
            else:
                for kind, t, sql in plan:
                    try:
                        cur.execute(sql)
                        conn.commit()
                        stmts.append({"kind": kind, "table": t, "sql": sql, "status": "applied"})
                    except Exception as e:
                        conn.rollback()
                        stmts.append({"kind": kind, "table": t, "sql": sql, "status": "error",
                                      "message": str(e).splitlines()[0][:200]})
    finally:
        conn.close()
    return {"schema": schema, "statements": stmts, "dry_run": dry_run,
            "applied": sum(1 for s in stmts if s["status"] == "applied"),
            "errors": sum(1 for s in stmts if s["status"] == "error"),
            "pending": sum(1 for s in stmts if s["status"] == "pending"),
            "skipped_pk": skipped_pk, "skipped_fk": skipped_fk,
            "pk_planned": sum(1 for s in stmts if s["kind"] == "pk"),
            "fk_planned": sum(1 for s in stmts if s["kind"] == "fk")}

