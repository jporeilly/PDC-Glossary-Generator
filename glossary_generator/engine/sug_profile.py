"""Value profiling - signatures, induced patterns, profile_live, discover.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS
from engine.sug_harvest import harvest_live
from engine.sug_suggest import suggest

# ---- value-level data profiling: sample real data to determine sensitivity/CDE ----
RX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RX_SSN   = re.compile(r"^\d{3}-\d{2}-\d{4}$")
RX_CC    = re.compile(r"^\d{13,19}$")
RX_PHONE = re.compile(r"^[+(]?[\d][\d\s().-]{6,}$")
RX_ZIP   = re.compile(r"^\d{5}(-\d{4})?$")
RX_DATE  = re.compile(r"^\d{4}-\d{2}-\d{2}|^\d{1,2}/\d{1,2}/\d{2,4}")
RX_DEC   = re.compile(r"^-?\d+\.\d+$")

def _value_signature(s):
    """PDC-style position signature of one value: digits->n, upper->A, lower->a,
       common separators kept literally. None for long/exotic values."""
    if not s or len(s) > 32:
        return None
    out = []
    for ch in s:
        if ch.isdigit(): c = "n"
        elif ch.isalpha(): c = "A" if ch.isupper() else "a"
        elif ch in "-_./ :#": c = ch
        else: return None
        out.append(c)
    return "".join(out)

def _induce_pattern(strs):
    r"""Learn a value format from sampled data: when >=90% of values share one
       position signature (e.g. AAA-nnnnn for CPC-84120), derive an anchored
       regex — a stable literal prefix is kept verbatim (^CPC-\d{5}$), the rest
       generalizes by character class. This is the evidence a Data Pattern
       method needs, so it flows into the row and the Registry `detect` list.
       Returns (signature, regex, share) or (None, None, 0)."""
    sigs = {}
    for v in strs:
        g = _value_signature(v)
        if g:
            sigs.setdefault(g, []).append(v)
    if not sigs:
        return None, None, 0
    sig, vals = max(sigs.items(), key=lambda kv: len(kv[1]))
    share = len(vals) / len(strs)
    if share < 0.9 or len(vals) < 5 or len(sig) < 4:
        return None, None, 0
    if "n" not in sig or len(set(sig)) < 2:
        return None, None, 0        # want structured codes, not plain words/numbers
    prefix = os.path.commonprefix(vals)
    while prefix and (prefix[-1].isdigit() or _value_signature(prefix) is None):
        prefix = prefix[:-1]        # never let variance digits leak into the literal
    if len(prefix) < 2:
        prefix = ""
    rest = sig[len(prefix):]
    parts, i = [], 0
    while i < len(rest):
        j = i
        while j < len(rest) and rest[j] == rest[i]:
            j += 1
        k, c = j - i, rest[i]
        if c == "n":   parts.append(r"\d{%d}" % k if k > 1 else r"\d")
        elif c == "A": parts.append("[A-Z]{%d}" % k if k > 1 else "[A-Z]")
        elif c == "a": parts.append("[a-z]{%d}" % k if k > 1 else "[a-z]")
        else:          parts.append(re.escape(c) * k)
        i = j
    rx = "^" + re.escape(prefix) + "".join(parts) + "$"
    try:
        crx = re.compile(rx)
    except re.error:
        return None, None, 0
    ok = sum(1 for v in strs if crx.match(v)) / len(strs)
    if ok < 0.9:
        return None, None, 0
    return sig, rx, ok

def _profile_values(name, vals, sample_n):
    """Infer pii/sensitivity/uniqueness/type from a column's sampled values.
       Also returns DQ signals: completeness (non-empty/sampled) and, where a
       pattern/type is detected, validity (share of values conforming)."""
    strs = [str(v).strip() for v in vals if v is not None and str(v).strip() != ""]
    completeness = round(len(strs) / sample_n, 3) if sample_n else 0
    if not strs:
        return {"uniq": 0, "completeness": completeness, "kind": "empty", "reason": "Profiled: all null/blank"}
    n = len(strs)
    def frac(rx):
        """Fraction of the sampled values that match regex `rx`."""
        return sum(1 for s in strs if rx.match(s)) / n
    distinct = len(set(strs)); uniq = distinct / n
    avg_digits = sum(sum(ch.isdigit() for ch in s) for s in strs) / n
    has_sep = sum(1 for s in strs if any(c in s for c in "-() ")) / n
    base = {"uniq": uniq, "completeness": completeness}
    if frac(RX_EMAIL) >= 0.6:
        return {**base, "pii": "CONTACT_INFO", "sensitivity": "HIGH", "confidence": "High",
                "reason": "Profiled: email values", "kind": "email", "valid": round(frac(RX_EMAIL), 3)}
    if frac(RX_SSN) >= 0.6:
        return {**base, "pii": "PERSONAL_NAME", "sensitivity": "HIGH", "confidence": "High",
                "reason": "Profiled: SSN-format values", "kind": "ssn", "valid": round(frac(RX_SSN), 3)}
    if frac(RX_CC) >= 0.6 and avg_digits >= 13:
        return {**base, "pii": "FINANCIAL", "sensitivity": "HIGH", "confidence": "High",
                "reason": "Profiled: card/account-number values", "kind": "card", "valid": round(frac(RX_CC), 3)}
    if frac(RX_DATE) >= 0.6:
        return {**base, "confidence": "Medium", "reason": "Profiled: date values", "kind": "date", "valid": round(frac(RX_DATE), 3)}
    if frac(RX_ZIP) >= 0.7:
        return {**base, "pii": "ADDRESS_INFO", "sensitivity": "MEDIUM", "confidence": "High",
                "reason": "Profiled: postal-code values", "kind": "zip", "valid": round(frac(RX_ZIP), 3)}
    if frac(RX_PHONE) >= 0.6 and 7 <= avg_digits <= 15 and has_sep >= 0.3:
        return {**base, "pii": "CONTACT_INFO", "sensitivity": "MEDIUM", "confidence": "High",
                "reason": "Profiled: phone-format values", "kind": "phone", "valid": round(frac(RX_PHONE), 3)}
    # an enum is a SMALL SET OF REPEATED CODES — require actual repetition
    # (uniq <= .5): a tiny demo table's 10 distinct ids otherwise profiles as
    # an "enum", which reads as reference data and blocks the key prune.
    # The floor is RELATIVE (each value seen ~twice), not a flat row count:
    # a flat n >= 10 starved exactly the most reference-y tables there are —
    # small lookups (8 water systems' counties/types carried NO enum while a
    # busy billing table's status did; field-caught: "a pattern or values
    # must be available?"). The flat part of the floor is 5, not 6: NULLs
    # shrink the non-null sample, and a status column that is Compliant×3 /
    # Warning×2 with 3 nulls is reference data by any honest reading.
    # The ceiling is 48, not 12: real reference vocabularies run to dozens,
    # and a 15-city service area sat three past the old cap — profiling as
    # shapeless free text, so the drafter skipped the city columns with
    # "values induce no shape" (field: "could this still be a lack of
    # values, so it doesn't trigger a pattern?" — the opposite: too many).
    # The repetition floor self-scales with the sample (100 sampled rows
    # admit at most 50 distinct), so the ceiling is a backstop against
    # unbounded lists, not the working gate — and id-like columns still
    # fall to uniq <= .5. Vocabularies past ~50 need a larger sample_size
    # before a larger ceiling could ever admit them.
    if distinct <= 48 and n >= max(5, 2 * distinct) and uniq <= 0.5:
        return {**base, "confidence": "Medium", "kind": "enum",
                "reason": f"Profiled: low cardinality ({distinct} distinct - reference-data candidate)",
                "enum": sorted(set(strs))[:48]}
    sig, rx, share = _induce_pattern(strs)
    if sig:
        return {**base, "confidence": "High",
                "kind": "identifier" if uniq >= 0.95 else "code",
                "signature": sig, "pattern": rx, "valid": round(share, 3),
                "reason": f"Profiled: {int(share * 100)}% of values share position signature {sig}"}
    if uniq >= 0.95 and n >= 5 and frac(RX_DEC) < 0.5:
        return {**base, "confidence": "High", "reason": "Profiled: near-unique values (likely identifier)",
                "kind": "identifier"}
    # A CANDIDATE reference list rides along whenever profiling captured a
    # small value set that is not id-territory ("lets set for equal or more
    # than 2 values" — Service City's 8 cities were SEEN but never persisted,
    # so the drafter and DQ arrived empty-handed). The strict repeated-codes
    # gate above keeps its meaning (kind stays decimal/value here, so review
    # semantics and the key prune are untouched); this only lets the captured
    # values travel to dictionary rules and allowed-values baselines.
    candidate = (sorted(set(strs))[:48]
                 if 2 <= distinct <= 48 and uniq < 0.95 else None)
    dec = frac(RX_DEC)
    if dec >= 0.5:
        return {**base, "reason": "Profiled", "kind": "decimal", "valid": round(dec, 3),
                **({"enum": candidate} if candidate else {})}
    return {**base, "reason": "Profiled", "kind": "value",
            **({"enum": candidate} if candidate else {})}

def profile_live(cfg, tables, schema=None, sample_size=80):
    """Sample rows per table and attach a `profile` dict to each column. Best-effort;
       columns/tables that can't be sampled are left name-based."""
    from sources import dbconn
    eng = cfg.get("engine", "postgresql")
    schema = schema or cfg.get("schema") or "public"
    conn = dbconn._connect(cfg)
    try:
        with conn.cursor() as cur:
            for tname, cols in tables.items():
                try:
                    if eng == "sqlserver":
                        cur.execute(f'SELECT TOP {sample_size} * FROM "{schema}"."{tname}"')
                    else:
                        cur.execute(f'SELECT * FROM "{schema}"."{tname}" LIMIT {sample_size}')
                    names = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                except Exception:
                    conn.rollback() if hasattr(conn, "rollback") else None
                    continue
                for col in cols:
                    if col["column"] in names:
                        idx = names.index(col["column"])
                        vals = [r[idx] for r in rows]
                        col["profile"] = _profile_values(col["column"], vals, len(rows))
                        seen, ex = set(), []
                        for v in vals:
                            if v is None: continue
                            s = str(v).strip()
                            if s and s not in seen:
                                seen.add(s); ex.append(s[:40])
                            if len(ex) >= 3: break
                        col["examples"] = ex
    finally:
        conn.close()
    return tables

def discover(cfg, schema=None, sample_size=100):
    """Full data-discovery profile per table/column: row counts, completeness,
       distinct/uniqueness, sensitivity/PII/CDE, detected kind and example values.
       Mirrors the dimensions PDC's column profiling shows, for side-by-side comparison."""
    from sources import dbconn
    schema = schema or cfg.get("schema") or "public"
    tables = harvest_live(cfg, schema)
    try:
        profile_live(cfg, tables, schema, sample_size)
    except Exception:
        pass
    rows = suggest(tables, schema)
    bykey = {}
    for r in rows:
        sc = r["Source_Column"].split(";")[0].strip().split(".")
        if len(sc) >= 3:
            bykey[(sc[-2], sc[-1])] = r
    conn = dbconn._connect(cfg)
    out, summary = [], {"tables": 0, "columns": 0, "rows": 0, "pii": 0, "cde": 0,
                        "empty": 0, "sensitivity": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                        "pk_cols": 0, "fk_cols": 0, "classified": 0, "db_bytes": 0,
                        "avg_completeness": 0}
    comp_sum = comp_n = 0
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT pg_database_size(current_database())")
                summary["db_bytes"] = cur.fetchone()[0] or 0
            except Exception:
                try: conn.rollback()
                except Exception: pass
            for tname, cols in tables.items():
                sel = ["COUNT(*)"]
                for c in cols:
                    q = '"' + c["column"].replace('"', '') + '"'
                    sel += [f"COUNT({q})", f"COUNT(DISTINCT {q})"]
                try:
                    cur.execute(f'SELECT {", ".join(sel)} FROM "{schema}"."{tname}"')
                    agg = cur.fetchone()
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                    agg = None
                tbytes = 0
                try:
                    cur.execute("SELECT pg_total_relation_size(%s::regclass)", (f'"{schema}"."{tname}"',))
                    tbytes = cur.fetchone()[0] or 0
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                total = (agg[0] if agg else 0) or 0
                colout = []
                for i, c in enumerate(cols):
                    nn = (agg[1 + i * 2] if agg else 0) or 0
                    dd = (agg[2 + i * 2] if agg else 0) or 0
                    sr = bykey.get((tname, c["column"]), {})
                    prof = c.get("profile") or {}
                    sens = sr.get("Sensitivity", "LOW"); pii = sr.get("PII_Category", ""); cde = sr.get("Critical_Data_Element", "No")
                    completeness = round(nn / total, 3) if total else 0
                    colout.append({"column": c["column"], "type": c["type"], "pk": c["pk"], "fk": c["fk"],
                                   "non_null": nn, "distinct": dd,
                                   "completeness": completeness,
                                   "uniqueness": round(dd / nn, 3) if nn else 0,
                                   "sensitivity": sens, "pii": pii, "cde": cde,
                                   "kind": prof.get("kind", ""), "examples": c.get("examples", []),
                                   "term": sr.get("Term", ""), "confidence": sr.get("Confidence", "")})
                    summary["columns"] += 1
                    if pii: summary["pii"] += 1
                    if cde == "Yes": summary["cde"] += 1
                    if c["pk"]: summary["pk_cols"] += 1
                    if c["fk"]: summary["fk_cols"] += 1
                    if pii or sens != "LOW": summary["classified"] += 1
                    if total:
                        comp_sum += completeness; comp_n += 1
                    if sens in summary["sensitivity"]: summary["sensitivity"][sens] += 1
                out.append({"name": tname, "rows": total, "bytes": tbytes,
                            "empty": total == 0, "columns": colout})
                summary["tables"] += 1; summary["rows"] += total
                if total == 0: summary["empty"] += 1
    finally:
        conn.close()
    summary["avg_completeness"] = round(comp_sum / comp_n, 3) if comp_n else 0
    summary["largest_tables"] = sorted(
        [{"name": t["name"], "rows": t["rows"], "bytes": t["bytes"]} for t in out],
        key=lambda t: t["rows"], reverse=True)[:5]
    return {"schema": schema, "tables": out, "summary": summary}

