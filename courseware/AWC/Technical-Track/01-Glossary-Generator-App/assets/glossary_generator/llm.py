"""
llm.py - local LLM client for term enrichment (Ollama).

Talks to a local Ollama server for one-sentence business definitions.
Everything is best-effort: if Ollama is unreachable or returns junk, the
caller keeps the heuristic definition. Nothing here ever raises to the request.

Setup:
  ollama pull llama3.1
  ollama serve            # serves http://localhost:11434

Env:
  LLM_MODEL    model name              (default llama3.1)
  OLLAMA_URL   http://localhost:11434  (default)
  LLM_TIMEOUT  seconds per call        (default 30)
"""
import os, re, json, urllib.request
import concurrent.futures

MODEL      = os.environ.get("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
TIMEOUT    = float(os.environ.get("LLM_TIMEOUT", "30"))
COMPANY    = os.environ.get("GLOSSARY_COMPANY", "your organization")

def _clampint(val, default, lo, hi):
    try:
        return max(lo, min(int(val), hi))
    except (TypeError, ValueError):
        return default

WORKERS = _clampint(os.environ.get("LLM_WORKERS", "4"), 4, 1, 16)
BATCH   = _clampint(os.environ.get("LLM_BATCH", "6"), 6, 1, 20)

SYSTEM = ("You are a data-governance analyst writing entries for a business "
          "glossary. Definitions are precise, business-facing, and one sentence.")

def configure(ollama_url=None, model=None, timeout=None, company=None,
              workers=None, batch=None):
    """Update the runtime LLM config (used by the Settings page so the Ollama URL /
       model / timeout / company / workers / batch can change without a restart).
       Empty values are ignored, so a caller can update just one field. The module
       functions read these globals at call time, so changes take effect immediately."""
    global OLLAMA_URL, MODEL, TIMEOUT, COMPANY, WORKERS, BATCH
    if ollama_url:
        OLLAMA_URL = str(ollama_url).strip().rstrip("/")
    if model:
        MODEL = str(model).strip()
    if timeout not in (None, ""):
        try:
            TIMEOUT = float(timeout)
        except (TypeError, ValueError):
            pass
    if company:
        COMPANY = str(company).strip()
    if workers not in (None, ""):
        WORKERS = _clampint(workers, WORKERS, 1, 16)
    if batch not in (None, ""):
        BATCH = _clampint(batch, BATCH, 1, 20)
    return {"ollama_url": OLLAMA_URL, "model": MODEL, "timeout": TIMEOUT,
            "company": COMPANY, "workers": WORKERS, "batch": BATCH}

def _post(url, payload, timeout=None):
    """POST a JSON body to the local Ollama endpoint and return the parsed response."""
    if timeout is None:
        timeout = TIMEOUT
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def placement():
    """Where loaded models actually run, from Ollama /api/ps (the real truth,
       set by the SERVER's OS env + hardware - not by this app). Returns e.g.
       {'known':True,'label':'100% GPU'} or {'known':False}."""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/ps", timeout=3) as r:
            ps = json.loads(r.read().decode("utf-8"))
        models = ps.get("models", [])
        if not models:
            return {"known": False, "loaded": False}
        m = models[0]
        for mm in models:  # prefer the configured model if it's loaded
            if MODEL.split(":")[0] in mm.get("name", ""):
                m = mm; break
        total = m.get("size") or 0
        vram = m.get("size_vram") or 0
        if total <= 0:
            return {"known": False, "loaded": True}
        gpu = round(100 * vram / total)
        cpu = 100 - gpu
        if gpu >= 99:   label = "100% GPU"
        elif gpu <= 1:  label = "100% CPU"
        else:           label = f"{cpu}%/{gpu}% CPU/GPU"
        return {"known": True, "loaded": True, "label": label,
                "gpu_pct": gpu, "cpu_pct": cpu, "name": m.get("name", "")}
    except Exception:
        return {"known": False}

def status(model=None):
    """Report whether local Ollama is reachable and which model is selected."""
    model = model or MODEL
    """Return a dict describing whether Ollama is reachable and has the model."""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            tags = json.loads(r.read().decode("utf-8"))
        models = [m.get("name", "") for m in tags.get("models", [])]
        return {"online": True, "backend": "ollama", "model": model, "url": OLLAMA_URL,
                "models": models,
                "model_present": any(model.split(":")[0] in m for m in models),
                "placement": placement()}
    except Exception as e:
        return {"online": False, "backend": "ollama", "model": model,
                "url": OLLAMA_URL, "error": str(e)}

def _complete(prompt, model=None, num_gpu=None):
    """Run a single prompt through Ollama and return the completion text."""
    model = model or MODEL
    """Single completion. Returns text or None on any failure."""
    options = {"temperature": 0.2}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    try:
        out = _post(OLLAMA_URL + "/api/generate",
                    {"model": model, "system": SYSTEM, "prompt": prompt,
                     "stream": False, "options": options})
        return (out.get("response") or "").strip()
    except Exception:
        return None


def _complete_json(prompt, model=None, num_gpu=None):
    """Single completion in Ollama JSON mode. Returns a parsed dict, or None on any
       failure. Used to get definition + purpose from ONE round trip per row."""
    model = model or MODEL
    options = {"temperature": 0.2}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    try:
        out = _post(OLLAMA_URL + "/api/generate",
                    {"model": model, "system": SYSTEM, "prompt": prompt,
                     "stream": False, "format": "json", "options": options})
        raw = (out.get("response") or "").strip()
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _clean_sentence(text, *prefixes):
    """Trim a model sentence: first line, strip quotes and a leading label."""
    if not text:
        return None
    text = str(text).splitlines()[0].strip().strip('"').strip()
    for p in prefixes:
        if text.lower().startswith(p.lower()):
            text = text[len(p):].strip()
    return text if 8 <= len(text) <= 300 else None

def _clean_name(text, current):
    """Sanitise a model-proposed term NAME. Returns a cleaned name only when it is a
       genuine, sensible improvement over `current`; otherwise None (keep current).
       Guards against junk: empty, label echoes, over-long, or unchanged values."""
    if not text:
        return None
    t = str(text).splitlines()[0].strip().strip('"').strip("'").strip()
    for p in ("Term:", "Name:", "Suggested name:"):
        if t.lower().startswith(p.lower()):
            t = t[len(p):].strip()
    t = re.sub(r"\s+", " ", t).strip(" .")
    if not t or len(t) > 60 or len(t.split()) > 8:
        return None
    cur = re.sub(r"\s+", " ", str(current or "")).strip()
    if t.lower() == cur.lower():                 # no change proposed
        return None
    return t

def enrich_definition(row, model=None, num_gpu=None):
    """Ask the model for a cleaner one-sentence definition for one term.
       Returns improved text, or None to keep the heuristic definition."""
    prompt = (
        f"Write a one-sentence (max 25 words) business definition for this database "
        f"column, for {COMPANY}'s business glossary.\n"
        f"Term: {row['Term']}\n"
        f"Source column: {row['Source_Column']}\n"
        f"Current draft: {row['Definition']}\n"
        f"Category: {row['Category']}\n"
        f"Respond with ONLY the definition sentence - no preamble, no quotes."
    )
    text = _complete(prompt, model=model, num_gpu=num_gpu)
    if not text:
        return None
    text = text.splitlines()[0].strip().strip('"').strip()
    for p in ("Definition:", "definition:"):
        if text.startswith(p):
            text = text[len(p):].strip()
    if 8 <= len(text) <= 300:
        return text
    return None

def enrich_purpose(row, model=None, num_gpu=None):
    """Ask the model for a cleaner one-sentence business Purpose (why it matters /
       how it's used). Returns improved text, or None to keep the heuristic."""
    prompt = (
        f"Write a one-sentence (max 25 words) business PURPOSE for this glossary "
        f"term — why it matters or how {COMPANY} uses it. "
        f"Not a definition; focus on use, decisions, or compliance.\n"
        f"Term: {row['Term']}\n"
        f"Definition: {row.get('Definition','')}\n"
        f"Category: {row['Category']}\n"
        f"Current draft purpose: {row.get('Purpose','')}\n"
        f"Respond with ONLY the purpose sentence - no preamble, no quotes."
    )
    text = _complete(prompt, model=model, num_gpu=num_gpu)
    if not text:
        return None
    text = text.splitlines()[0].strip().strip('"').strip()
    for p in ("Purpose:", "purpose:"):
        if text.startswith(p):
            text = text[len(p):].strip()
    if 8 <= len(text) <= 300:
        return text
    return None

def enrich_one(row, model=None, num_gpu=None):
    """One combined call per row: ask for a name suggestion, definition and purpose in a
       single JSON response, halving the round trips vs. separate calls.
       Returns (name_or_None, definition_or_None, purpose_or_None). Never raises.
       Falls back to the two-call path if JSON mode misbehaves."""
    prompt = (
        f"For this {COMPANY} business glossary term, return THREE fields:\n"
        f"  - \"name\": a clearer business term name ONLY if the source column is cryptic "
        f"or abbreviated (e.g. \"cust_acct_no\" -> \"Customer Account Number\"). If the "
        f"current Term already reads well, repeat it UNCHANGED.\n"
        f"  - \"definition\": one sentence (max 25 words), precise, business-facing, what it is.\n"
        f"  - \"purpose\": one sentence (max 25 words), why it matters or how the organization "
        f"uses it — not a restatement of the definition.\n"
        f"Term: {row.get('Term','')}\n"
        f"Source column: {row.get('Source_Column','')}\n"
        f"Category: {row.get('Category','')}\n"
        f"Current definition draft: {row.get('Definition','')}\n"
        f"Current purpose draft: {row.get('Purpose','')}\n"
        f"Respond with ONLY a JSON object: "
        f"{{\"name\": \"...\", \"definition\": \"...\", \"purpose\": \"...\"}}"
    )
    obj = _complete_json(prompt, model=model, num_gpu=num_gpu)
    if isinstance(obj, dict) and (obj.get("definition") or obj.get("purpose") or obj.get("name")):
        n = _clean_name(obj.get("name"), row.get("Term", ""))
        d = _clean_sentence(obj.get("definition"), "Definition:")
        p = _clean_sentence(obj.get("purpose"), "Purpose:")
        return n, d, p
    # fallback: two plain calls (older path) so a JSON hiccup doesn't lose enrichment
    return None, enrich_definition(row, model=model, num_gpu=num_gpu), \
           enrich_purpose(row, model=model, num_gpu=num_gpu)


def enrich_batch(rows, model=None, num_gpu=None):
    """Enrich SEVERAL rows in ONE model call: ask for a JSON object with an `items`
       array (one {definition, purpose} per term, in order). This is the main speed
       win — Ollama pays the system-prompt / scheduling overhead once for the whole
       batch instead of once per term. Returns a list of (def_or_None, pur_or_None)
       aligned to `rows`. Falls back to per-row enrich_one if the batch reply is
       missing or misaligned, so one bad JSON never drops the whole chunk."""
    rows = list(rows)
    if not rows:
        return []
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(
            f'{i}. Term: {r.get("Term","")} | Category: {r.get("Category","")} | '
            f'Source: {r.get("Source_Column","")} | Draft definition: {r.get("Definition","")} | '
            f'Draft purpose: {r.get("Purpose","")}')
    prompt = (
        f"For EACH numbered {COMPANY} business glossary term below, return a "
        "\"name\" (a clearer business term name ONLY if the Source column is cryptic or "
        "abbreviated, e.g. \"cust_acct_no\" -> \"Customer Account Number\"; if the current "
        "Term already reads well, repeat it UNCHANGED), a one-sentence (max 25 words) "
        "\"definition\" (precise, business-facing, what it is) and a one-sentence (max 25 "
        "words) \"purpose\" (why it matters or how the organization uses it — not a restatement "
        "of the definition).\n"
        "Return ONLY a JSON object of the form "
        "{\"items\":[{\"n\":1,\"name\":\"...\",\"definition\":\"...\",\"purpose\":\"...\"}, ...]} with one "
        "entry per term, keeping the same numbering.\n\n" + "\n".join(lines))
    obj = _complete_json(prompt, model=model, num_gpu=num_gpu)
    items = obj.get("items") if isinstance(obj, dict) else None
    if isinstance(items, list) and items:
        # index the reply by its 1-based "n" (fall back to position) so a reordered
        # or partial array still lands on the right row
        by_n = {}
        for pos, it in enumerate(items, 1):
            if not isinstance(it, dict):
                continue
            n = it.get("n")
            try:
                n = int(n)
            except (TypeError, ValueError):
                n = pos
            by_n[n] = it
        out, ok = [], 0
        for i, r in enumerate(rows, 1):
            it = by_n.get(i) or {}
            nm = _clean_name(it.get("name"), r.get("Term", ""))
            d = _clean_sentence(it.get("definition"), "Definition:")
            p = _clean_sentence(it.get("purpose"), "Purpose:")
            if d or p or nm:
                ok += 1
            out.append((nm, d, p))
        if ok:                      # got at least some usable entries → trust the batch
            return out
    # fallback: enrich each row on its own so the chunk still gets enriched
    return [enrich_one(r, model=model, num_gpu=num_gpu) for r in rows]


def enrich_rows(rows, only_low_confidence=False, model=None, compute=None, workers=None,
                batch_size=None):
    """Enrich a batch — definition and purpose. Terms are grouped into batches of
       `batch_size` (env LLM_BATCH, default 6), each batch enriched in a SINGLE model
       call, and the batches themselves run concurrently across a small thread pool.
       Returns (rows, counts). Safe if Ollama is offline; never raises out of here."""
    rows = [r for r in rows if isinstance(r, dict)]   # drop null/malformed rows (1.5.6)
    if not status(model)["online"]:
        return rows, {"definitions": 0, "purposes": 0, "names": 0}
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    if batch_size is None:
        batch_size = BATCH
    batch_size = max(1, min(batch_size, 20))

    targets = [r for r in rows
               if not (only_low_confidence and r.get("Confidence") == "High")]
    nd = npu = nn = 0

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]

    def _do(batch):
        try:
            return batch, enrich_batch(batch, model=model, num_gpu=num_gpu)
        except Exception:
            return batch, [(None, None, None)] * len(batch)

    if workers == 1 or len(batches) <= 1:
        results = [_do(b) for b in batches]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, batches))

    for batch, triples in results:
        for r, (new_name, new_def, new_pur) in zip(batch, triples):
            if new_name and new_name != r.get("Term"):
                r["Suggested_Name"] = new_name   # surfaced in review; Term is NOT overwritten
                r["LLM_Name"] = "Yes"
                r["LLM_Enriched"] = "Yes"
                nn += 1
            elif r.get("LLM_Name") is None:
                r["LLM_Name"] = "No"
            if new_def and new_def != r.get("Definition"):
                r["Definition"] = new_def
                r["LLM_Enriched"] = "Yes"      # kept for the summary badge + back-compat
                r["LLM_Definition"] = "Yes"    # this field specifically was LLM-written
                nd += 1
            elif r.get("LLM_Definition") is None:
                r["LLM_Definition"] = "No"     # processed but unchanged -> not LLM-written
            if new_pur and new_pur != r.get("Purpose"):
                r["Purpose"] = new_pur
                r["LLM_Enriched"] = "Yes"
                r["LLM_Purpose"] = "Yes"
                npu += 1
            elif r.get("LLM_Purpose") is None:
                r["LLM_Purpose"] = "No"
    return rows, {"definitions": nd, "purposes": npu, "names": nn}


# --------------------------------------------------------------- expertise
# Words that say nothing about a person's *domain* — stripped from the offline
# fallback so it doesn't emit "owns", "terms", "optional", etc. as keywords.
_EXP_STOP = {
    "the", "and", "for", "owns", "own", "terms", "term", "data", "glossary",
    "can", "incl", "including", "displayed", "optional", "persona", "reads",
    "searches", "creates", "manages", "defines", "custom", "properties",
    "worker", "workers", "licence", "license", "view", "galaxy", "metadata",
    "connects", "sources", "profiles", "runs", "curates", "collections",
    "create", "import", "edit", "policies", "users", "account", "accounts",
    "with", "from", "into", "that", "this", "their", "they", "role", "roles",
    "steward", "stewards", "analyst", "analysts", "admin", "user",
    "dr", "mr", "mrs", "ms",
}


def _expertise_llm(person, categories, model=None, num_gpu=None):
    """Ask Ollama for 4-8 domain keywords for one person. Returns a comma-joined
       string, or "" on any failure (caller then uses the offline fallback)."""
    name = person.get("display_name") or person.get("name") or "this user"
    roles = ", ".join(person.get("roles") or []) or "unspecified"
    owns = (person.get("owns") or "").strip()
    community = (person.get("community") or "").strip()
    catline = ", ".join(categories) if categories else "(none provided)"
    prompt = (
        "Map a data-team member to the business domains they should steward.\n"
        f"Person: {name}\nRoles: {roles}\n"
        f"Responsibilities: {owns or 'unspecified'}\n"
        f"Teams / community: {community or 'unspecified'}\n"
        f"Available glossary categories: {catline}\n\n"
        'Return ONLY JSON of the form {"keywords": ["..."]} with 4 to 8 short, '
        "lowercase business-domain keywords (single words or two-word phrases) "
        "describing this person's areas of expertise. Prefer words that overlap the "
        "available categories above. No full sentences, no personal names, and no "
        'generic role words such as "steward", "owner", "admin", "user".')
    obj = _complete_json(prompt, model=model, num_gpu=num_gpu)
    if not isinstance(obj, dict):
        return ""
    kws = obj.get("keywords") or obj.get("expertise") or []
    if isinstance(kws, str):
        kws = re.split(r"[,;]", kws)
    out, seen = [], set()
    banned = {"steward", "owner", "custodian", "admin", "user", "data", "none"}
    for k in kws:
        k = str(k).strip().lower().strip(".,;")
        if k and len(k) > 1 and k not in seen and k not in banned:
            seen.add(k)
            out.append(k)
    return ", ".join(out[:8])


def _expertise_fallback(person, categories=None):
    """Deterministic, offline expertise keywords from a person's owns/community
       text and the available category labels. Keeps auto-assign usable when Ollama
       is offline or returns nothing."""
    text = " ".join(str(person.get(k) or "")
                    for k in ("owns", "community", "expertise")).lower()
    # don't echo the person's own name back as a "skill"
    name_toks = {t for t in re.split(r"[^a-z0-9]+",
                 (str(person.get("display_name") or "") + " " +
                  str(person.get("name") or "")).lower()) if t}
    skip = _EXP_STOP | name_toks
    out, seen = [], set()
    # 1) category labels the person's text overlaps with (the strongest signal)
    for c in (categories or []):
        for w in re.split(r"[^a-z0-9]+", str(c).lower()):
            if len(w) > 3 and w in text and w not in seen and w not in skip:
                seen.add(w)
                out.append(w)
    # 2) the person's own meaningful words, in order
    for w in re.split(r"[^a-z0-9]+", text):
        if len(w) > 3 and w not in seen and w not in skip:
            seen.add(w)
            out.append(w)
    # 3) last resort: lean on the role
    if not out:
        roles = " ".join(person.get("roles") or []).lower()
        if "business" in roles:
            out = ["governance", "policy", "compliance"]
        elif "data" in roles:
            out = ["data quality", "profiling", "lineage"]
        elif "admin" in roles:
            out = ["administration", "accounts", "configuration"]
    return ", ".join(out[:8])


def suggest_expertise(people, categories=None, overwrite=False, model=None,
                      num_gpu=None):
    """Generate `expertise` keywords for each roster member from their role /
       responsibilities (`owns`) / community text and the available glossary
       categories. These keywords are what the auto-assign matcher scores against.
       LLM-first via local Ollama, with a deterministic offline fallback, so it
       always returns something usable. By default only people with no expertise
       are touched; pass overwrite=True to regenerate everyone.
       Returns (people, count_updated, used_llm)."""
    cats = [str(c).strip() for c in (categories or []) if str(c).strip()]
    online = status(model)["online"]
    updated = 0
    used_llm = False
    for p in people:
        if not isinstance(p, dict):
            continue
        if (p.get("expertise") or "").strip() and not overwrite:
            continue
        kws = ""
        if online:
            kws = _expertise_llm(p, cats, model=model, num_gpu=num_gpu)
            if kws:
                used_llm = True
        if not kws:
            kws = _expertise_fallback(p, cats)
        if kws:
            p["expertise"] = kws
            updated += 1
    return people, updated, used_llm


# --------------------------------------------------------------- model management
def list_models():
    """Return installed model names from Ollama, or [] if offline."""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            tags = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in tags.get("models", [])]
    except Exception:
        return []

def pull_stream(model=None):
    """Generator that pulls a model and yields progress dicts:
       {phase, status, completed, total, percent}. Safe to iterate to completion.
       Ollama resumes cancelled pulls automatically, so re-calling is cheap."""
    model = model or MODEL
    payload = json.dumps({"model": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/pull", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=None) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if "error" in obj:
                    yield {"phase": "error", "status": obj["error"], "percent": 0}
                    return
                status = obj.get("status", "")
                total = obj.get("total") or 0
                completed = obj.get("completed") or 0
                pct = round(100 * completed / total, 1) if total else None
                yield {"phase": "success" if status == "success" else "downloading",
                       "status": status, "completed": completed, "total": total,
                       "percent": pct}
    except Exception as e:
        yield {"phase": "error", "status": f"pull failed: {e}", "percent": 0}
