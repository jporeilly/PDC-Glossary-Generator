"""
dbconn.py - driver-aware connection helpers for live scans.

This app scans through Python DB-API drivers (not JDBC). Each engine declares
the pip package it needs; the UI checks presence and tells the user how to add
it - mirroring PDC's "Manage Drivers / download the vendor driver" step, but for
the Python driver this app actually loads.

All four engine drivers install with the app by default (requirements.txt, since 1.6.20).
Other engines are optional installs.
"""
import importlib

# engine -> {label, module, pip, default_port, dsn build}
ENGINES = {
    "postgresql": {"label": "PostgreSQL", "module": "psycopg2",
                   "pip": "psycopg2-binary", "port": 5432,
                   "jdbc_hint": "postgresql-42.7.x.jar (for PDC's Manage Drivers)"},
    "sqlserver":  {"label": "SQL Server", "module": "pymssql",
                   "pip": "pymssql", "port": 1433,
                   "jdbc_hint": "mssql-jdbc / sqljdbc (for PDC's Manage Drivers)"},
    "mysql":      {"label": "MySQL / MariaDB", "module": "pymysql",
                   "pip": "pymysql", "port": 3306,
                   "jdbc_hint": "mysql-connector-j / mariadb jar (for PDC)"},
    "oracle":     {"label": "Oracle", "module": "oracledb",
                   "pip": "oracledb", "port": 1521,
                   "jdbc_hint": "ojdbc11.jar (for PDC's Manage Drivers)"},
}

def driver_status():
    """Report, per engine, whether its Python driver is importable."""
    out = []
    for key, e in ENGINES.items():
        try:
            importlib.import_module(e["module"])
            present, ver = True, getattr(importlib.import_module(e["module"]), "__version__", "")
        except Exception:
            present, ver = False, ""
        out.append({"engine": key, "label": e["label"], "module": e["module"],
                    "pip": e["pip"], "port": e["port"], "present": present,
                    "version": ver, "install": f"pip install {e['pip']}",
                    "jdbc_hint": e["jdbc_hint"]})
    return out

def _connect(cfg):
    """Open a connection for cfg={engine,host,port,database,user,password,ssl}."""
    eng = cfg.get("engine", "postgresql")
    host = cfg.get("host", "localhost")
    port = int(cfg.get("port") or ENGINES[eng]["port"])
    db   = cfg.get("database", "")
    user = cfg.get("user", "")
    pw   = cfg.get("password", "")
    ssl  = bool(cfg.get("ssl", False))
    if eng == "postgresql":
        import psycopg2
        return psycopg2.connect(host=host, port=port, dbname=db, user=user,
                                password=pw, sslmode="require" if ssl else "prefer",
                                connect_timeout=8)
    if eng == "sqlserver":
        import pymssql
        return pymssql.connect(server=host, port=str(port), database=db,
                               user=user, password=pw, login_timeout=8)
    if eng == "mysql":
        import pymysql
        return pymysql.connect(host=host, port=port, database=db, user=user,
                               password=pw, connect_timeout=8,
                               ssl={"ssl": {}} if ssl else None)
    if eng == "oracle":
        import oracledb
        return oracledb.connect(user=user, password=pw,
                                dsn=f"{host}:{port}/{db}")
    raise ValueError(f"unsupported engine: {eng}")

def test_connection(cfg):
    """Return {ok, message, server_version?} without scanning anything."""
    eng = cfg.get("engine", "postgresql")
    e = ENGINES.get(eng)
    if not e:
        return {"ok": False, "message": f"Unknown engine {eng}"}
    try:
        importlib.import_module(e["module"])
    except Exception:
        return {"ok": False, "needs_driver": True,
                "message": f"{e['label']} driver not installed - run: pip install {e['pip']}"}
    try:
        conn = _connect(cfg)
        with conn.cursor() as cur:
            if eng == "oracle":
                # v$version needs a grant many read-only accounts lack; fall back to
                # a plain liveness probe so Test doesn't false-fail on least privilege.
                try:
                    cur.execute("SELECT * FROM v$version WHERE rownum=1")
                except Exception:
                    cur.execute("SELECT 'Oracle (version view not granted)' FROM dual")
            else:
                cur.execute("SELECT version()" if eng in ("postgresql", "mysql")
                            else "SELECT @@version")
            row = cur.fetchone()
        conn.close()
        return {"ok": True, "message": "Connection OK",
                "server_version": str(row[0])[:80] if row else ""}
    except Exception as ex:
        return {"ok": False, "message": f"Connection failed: {ex}"}

def build_dsn(cfg):
    """Convenience: a libpq DSN string (used by the Postgres harvest path)."""
    parts = [f"host={cfg.get('host','localhost')}",
             f"port={cfg.get('port') or ENGINES.get(cfg.get('engine','postgresql'),{}).get('port',5432)}",
             f"dbname={cfg.get('database','')}",
             f"user={cfg.get('user','')}",
             f"password={cfg.get('password','')}"]
    if cfg.get("ssl"):
        parts.append("sslmode=require")
    return " ".join(parts)
