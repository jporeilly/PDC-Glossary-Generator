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
import os, re, json
import concurrent.futures

import httpx

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
          "glossary. Definitions are precise, business-facing, and one sentence. "
          "Always write in English, whatever language the model was trained in.")

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
    r = httpx.post(url, json=payload, timeout=timeout)
    r.raise_for_status()          # match the old urllib behavior: HTTP errors raise
    return r.json()


def placement():
    """Where loaded models actually run, from Ollama /api/ps (the real truth,
       set by the SERVER's OS env + hardware - not by this app). Returns e.g.
       {'known':True,'label':'100% GPU'} or {'known':False}."""
    try:
        ps = httpx.get(OLLAMA_URL + "/api/ps", timeout=3).json()
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
        tags = httpx.get(OLLAMA_URL + "/api/tags", timeout=3).json()
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


_NON_LATIN = re.compile(r"[Ͱ-᳿　-鿿가-힯぀-ヿ豈-﫿]")

def _mostly_english(text):
    """Language guardrail: True when the text is essentially Latin-script.
       Multilingual local models (qwen, deepseek, ...) sometimes drift into
       their home language mid-batch; a proposal that fails this check is
       DISCARDED so the existing English text stays."""
    t = str(text or "")
    if not t:
        return True
    hits = len(_NON_LATIN.findall(t))
    return hits == 0 or hits / len(t) < 0.05


def _clean_sentence(text, *prefixes):
    """Trim a model sentence: first line, strip quotes and a leading label."""
    if not text:
        return None
    text = str(text).splitlines()[0].strip().strip('"').strip()
    for p in prefixes:
        if text.lower().startswith(p.lower()):
            text = text[len(p):].strip()
    if not _mostly_english(text):
        return None
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
    if not t or len(t) > 60 or len(t.split()) > 8 or not _mostly_english(t):
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
        tags = httpx.get(OLLAMA_URL + "/api/tags", timeout=3).json()
        return [m.get("name", "") for m in tags.get("models", [])]
    except Exception:
        return []

def pull_stream(model=None):
    """Generator that pulls a model and yields progress dicts:
       {phase, status, completed, total, percent}. Safe to iterate to completion.
       Ollama resumes cancelled pulls automatically, so re-calling is cheap."""
    model = model or MODEL
    try:
        with httpx.stream("POST", OLLAMA_URL + "/api/pull",
                          json={"model": model, "stream": True}, timeout=None) as resp:
            for raw in resp.iter_lines():
                line = raw.strip()
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


# ------------------------------------------------------------ AI evidence pass
def _suggest_one(row, allow_tags, categories, model=None, num_gpu=None):
    """One evidence-grounded classification call. Returns the parsed proposal
       dict or None. The prompt is grounded in SCAN EVIDENCE (profiled value
       signature / induced regex / reference values), not just the name."""
    ev = []
    if row.get("Source_Column"):
        ev.append("physical column(s): %s" % row["Source_Column"])
    if row.get("Definition"):
        ev.append("current definition: %s" % row["Definition"][:220])
    if row.get("Value_Signature"):
        ev.append("profiled position signature: %s" % row["Value_Signature"])
    if row.get("Value_Pattern"):
        ev.append("induced value regex: %s" % row["Value_Pattern"])
    enum_vals = (row.get("Enum_Values") or "").strip()
    if enum_vals:
        ev.append("profiled reference values: %s" % enum_vals[:200])
    if row.get("PII_Category"):
        ev.append("PII category: %s" % row["PII_Category"])
    if row.get("Suggested_Reason"):
        ev.append("scan reasoning: %s" % row["Suggested_Reason"][:160])
    prompt = (
        "You classify a database column into a governed business glossary%s.\n"
        "Current suggestion: term \"%s\" in category \"%s\", sensitivity %s, tags: %s.\n"
        "Evidence from scanning the actual data:\n- %s\n\n"
        "Categories (choose one): %s\n"
        "Governed tag allow-list (use ONLY these): %s\n\n"
        "Return JSON with keys: term (concise singular business name), category, "
        "tags (array, only from the allow-list, the most relevant 2-5), sensitivity "
        "(LOW, MEDIUM or HIGH - never lower than the current value), rationale "
        "(one short sentence grounded in the evidence)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        row.get("Term", ""), row.get("Category", ""), row.get("Sensitivity", "LOW"),
        row.get("Suggested_Tags", "") or "(none)",
        "\n- ".join(ev) if ev else "(name only - no profile evidence)",
        ", ".join(categories or []) or "(keep current)",
        ", ".join(allow_tags or []) or "(none)",
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)

_SENS_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

def suggest_terms_rows(rows, allow_tags=None, categories=None, only_low_confidence=False,
                       model=None, compute=None, workers=None):
    """AI agent pass over review rows. For each row the model proposes term /
       category / tags / sensitivity FROM THE SCAN EVIDENCE, and the code applies
       it under governance guardrails: tags are filtered to the governed
       allow-list, sensitivity can only tighten, the term is surfaced as
       Suggested_Name (never overwriting the steward's Term), and the rationale
       lands in Suggested_Reason. Returns (rows, counts, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    counts = {"names": 0, "tags": 0, "sensitivity": 0, "category": 0}
    if not status(model)["online"]:
        return rows, counts, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    allow = [t for t in (allow_tags or [])]
    allow_set = {str(t).strip().lower() for t in allow}
    cats = [c for c in (categories or [])]
    targets = [r for r in rows
               if not (only_low_confidence and r.get("Confidence") == "High")]

    # warm the model first: a cold load can outlive LLM_TIMEOUT and would make
    # the first batch fail silently (calls return None until the model is resident)
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(r):
        try:
            return r, _suggest_one(r, allow, cats, model=model, num_gpu=num_gpu)
        except Exception:
            return r, None

    if workers == 1 or len(targets) <= 1:
        results = [_do(r) for r in targets]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, targets))

    for r, out in results:
        if not isinstance(out, dict):
            continue
        changed = False
        # term: propose, never overwrite (same contract as enrich's name pass)
        term = _clean_name(str(out.get("term") or ""), r.get("Term", ""))
        if term and term != r.get("Term") and term != r.get("Suggested_Name"):
            r["Suggested_Name"] = term
            r["LLM_Name"] = "Yes"
            counts["names"] += 1
            changed = True
        # category: accept only a known category
        cat = str(out.get("category") or "").strip()
        if cat and cats and cat in cats and cat != r.get("Category"):
            r["Category"] = cat
            counts["category"] += 1
            changed = True
        # tags: union, governed-only
        proposed = out.get("tags") or []
        if isinstance(proposed, list):
            cur = [t for t in (r.get("Suggested_Tags") or "").split(";") if t]
            cur_l = {t.strip().lower() for t in cur}
            # append in standardised lower-case (the governed vocabulary's form)
            added = [str(t).strip().lower() for t in proposed
                     if str(t).strip() and str(t).strip().lower() in allow_set
                     and str(t).strip().lower() not in cur_l]
            if added:
                r["Suggested_Tags"] = ";".join(cur + added)
                counts["tags"] += 1
                changed = True
        # sensitivity: tighten only
        sens = str(out.get("sensitivity") or "").strip().upper()
        cur_s = str(r.get("Sensitivity") or "LOW").upper()
        if sens in _SENS_ORDER and _SENS_ORDER[sens] > _SENS_ORDER.get(cur_s, 0):
            r["Sensitivity"] = sens
            counts["sensitivity"] += 1
            changed = True
        if changed:
            r["AI_Suggested"] = "Yes"
            r["LLM_Enriched"] = "Yes"
            why = str(out.get("rationale") or "").strip()
            if not _mostly_english(why):
                why = ""
            if why:
                base = r.get("Suggested_Reason") or ""
                if "AI(evidence)" not in base:
                    r["Suggested_Reason"] = (base + " · " if base else "") + "AI(evidence): " + why[:180]
    return rows, counts, True


# ------------------------------------------------------------ AI merge adjudicator
_ADJ_ACTIONS = {"merge": "merge", "split": "split", "disambiguate": "split",
                "separate": "separate", "keep separate": "separate"}

def _adjudicate_one(group, model=None, num_gpu=None):
    """One duplicate-group judgment call. The prompt lays out each candidate's
       scan evidence side by side and asks for ONE of the grid's three actions.
       Returns the parsed proposal dict or None."""
    lines = []
    for i, m in enumerate(group.get("members") or [], 1):
        bits = []
        if m.get("Category"):
            bits.append("category: %s" % m["Category"])
        if m.get("Source_Column"):
            bits.append("column(s): %s" % m["Source_Column"])
        if m.get("Definition"):
            bits.append("definition: %s" % str(m["Definition"])[:180])
        if m.get("Value_Pattern"):
            bits.append("induced format: %s" % m["Value_Pattern"])
        elif m.get("Value_Signature"):
            bits.append("value signature: %s" % m["Value_Signature"])
        ev = (m.get("Enum_Values") or "").strip()
        if ev:
            bits.append("profiled values: %s" % ev[:160])
        if m.get("PII_Category"):
            bits.append("PII class: %s" % m["PII_Category"])
        lines.append("Candidate %d - %s" % (i, "; ".join(bits) or "(name only)"))
    prompt = (
        "You are a data-governance steward%s. %d glossary term candidates share "
        "the name \"%s\" but come from different scans/tables. Decide ONE action:\n"
        "- merge: they are the SAME business concept; one term should link all columns.\n"
        "- disambiguate: the same word hides DIFFERENT concepts; rename with qualifiers.\n"
        "- separate: different concepts in different categories; both can stand as-is.\n\n"
        "%s\n\n"
        "Judge by MEANING and by the data evidence (formats, value lists, PII class), "
        "not by the shared name. Return JSON with keys: action (merge, disambiguate "
        "or separate), rationale (one short sentence grounded in the evidence)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        len(group.get("members") or []),
        group.get("name", ""),
        "\n".join(lines),
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def adjudicate_groups(groups, model=None, compute=None, workers=None):
    """AI agent pass over AMBIGUOUS duplicate groups — the ones the deterministic
       evidence rubric could not settle. For each group the model weighs the
       members' definitions and scan evidence and proposes merge / disambiguate /
       separate; the code applies guardrails (action must be one of the grid's
       three; rationale trimmed) and NEVER auto-applies — the result is a hint on
       the group header, the steward still clicks. Returns ({name: {action,
       reason}}, used_llm)."""
    groups = [g for g in (groups or []) if isinstance(g, dict) and g.get("name")]
    if not groups or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))

    # warm the model first (a cold load can outlive LLM_TIMEOUT and fail silently)
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(g):
        try:
            return g, _adjudicate_one(g, model=model, num_gpu=num_gpu)
        except Exception:
            return g, None

    if workers == 1 or len(groups) <= 1:
        results = [_do(g) for g in groups]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, groups))

    out = {}
    for g, res in results:
        if not isinstance(res, dict):
            continue
        action = _ADJ_ACTIONS.get(str(res.get("action") or "").strip().lower())
        if not action:
            continue
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        out[g["name"]] = {"action": action,
                          "reason": ("AI: " + why) if why else "AI adjudication"}
    return out, True


# ------------------------------------------------------------ AI policy hints
def _policy_hint_one(concept, allow_tags, model=None, num_gpu=None):
    """One rule-polish call for the policy drafter: given a concept's term,
       physical columns and evidence, propose a better column-name regex and
       the 2-3 most relevant governed tags. Returns the parsed dict or None."""
    prompt = (
        "You help author a data-identification rule%s for the business term \"%s\".\n"
        "Physical columns it was found in: %s.\n"
        "Value evidence: %s.\n"
        "Governed tag allow-list (use ONLY these): %s.\n\n"
        "Return JSON with keys: column_regex (a single case-insensitive regex "
        "starting with (?i) that matches these column NAMES and their likely "
        "synonyms/abbreviations, nothing overly broad), tags (array, the 2-3 most "
        "relevant tags from the allow-list)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        concept.get("term", ""),
        concept.get("columns", "") or "(unknown)",
        concept.get("evidence", "") or "(none)",
        ", ".join(allow_tags or []) or "(none)",
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def policy_hints_rows(concepts, allow_tags=None, model=None, compute=None, workers=None):
    """AI polish pass for the policy drafter. concepts: [{term, columns,
       evidence}]. Returns ({term: {column_regex, tags}}, used_llm). Guardrails
       live in policy_draft.draft_from_rows (regex must compile, tags must stay
       governed) — this only proposes."""
    concepts = [c for c in (concepts or []) if isinstance(c, dict) and c.get("term")]
    if not concepts or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    allow = [t for t in (allow_tags or [])]
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(c):
        try:
            return c, _policy_hint_one(c, allow, model=model, num_gpu=num_gpu)
        except Exception:
            return c, None

    if workers == 1 or len(concepts) <= 1:
        results = [_do(c) for c in concepts]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, concepts))
    out = {}
    for c, res in results:
        if isinstance(res, dict):
            hint = {}
            rx = str(res.get("column_regex") or "").strip()
            if rx:
                hint["column_regex"] = rx
            tags = res.get("tags")
            if isinstance(tags, list):
                hint["tags"] = [str(t).strip() for t in tags if str(t).strip()][:3]
            if hint:
                out[c["term"]] = hint
    return out, True


# ------------------------------------------------------------ AI definition QA
def _qa_one(row, model=None, num_gpu=None):
    """One definition-quality judgment. Returns the parsed dict or None."""
    prompt = (
        "You review a business glossary definition%s for quality.\n"
        "Term: \"%s\" (category: %s; physical column(s): %s).\n"
        "Definition under review: \"%s\"\n\n"
        "A GOOD definition says what the thing IS in business language, is "
        "specific to this term, and would let a new analyst use the data "
        "correctly. It is BAD if it is circular, generic enough to fit any "
        "term, jargon-only, or wrong for the evidence.\n"
        "Return JSON with keys: ok (true/false), issue (one short phrase, empty "
        "when ok), better (an improved one-sentence definition, empty when ok)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        row.get("Term", ""), row.get("Category", "") or "-",
        row.get("Source_Column", "") or "-",
        str(row.get("Definition") or "")[:300],
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def qa_definitions_rows(rows, model=None, compute=None, workers=None):
    """AI definition-QA pass over kept rows. Stamps QA_Issues / QA_Suggestion on
       rows the model flags (merging with any linter findings already present).
       Proposals only — the steward applies a suggestion explicitly. Returns
       (rows, flagged_count, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not status(model)["online"]:
        return rows, 0, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    targets = [r for r in rows
               if str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")
               and (r.get("Term") or "").strip()]
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(r):
        try:
            return r, _qa_one(r, model=model, num_gpu=num_gpu)
        except Exception:
            return r, None

    if workers == 1 or len(targets) <= 1:
        results = [_do(r) for r in targets]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, targets))
    flagged = 0
    for r, res in results:
        if not isinstance(res, dict):
            continue
        ok = res.get("ok")
        issue = str(res.get("issue") or "").strip()
        if not _mostly_english(issue):
            continue
        if ok is False and issue:
            cur = [x for x in str(r.get("QA_Issues") or "").split(";") if x.strip()]
            if issue not in cur:
                cur.append(issue)
            r["QA_Issues"] = ";".join(cur)
            better = _clean_sentence(res.get("better"))
            if better and better.lower() != str(r.get("Definition") or "").strip().lower():
                r["QA_Suggestion"] = better
            flagged += 1
    return rows, flagged, True


# ------------------------------------------------------------ AI categorizer
def categorize_rows(rows, categories, model=None, compute=None, workers=None,
                    only_blank=True):
    """AI category assignment: for rows with no meaningful category (or all rows
       when only_blank=False) the model picks ONE category from the known list.
       Guardrails: the choice must be in the list, everything else is ignored.
       Returns (rows, updated_count, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    cats = [str(c).strip() for c in (categories or []) if str(c).strip()]
    if not cats or not status(model)["online"]:
        return rows, 0, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    generic = {"", "general", "uncategorized", "uncategorised", "other", "misc"}
    targets = [r for r in rows
               if str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")
               and (r.get("Term") or "").strip()
               and (not only_blank or str(r.get("Category") or "").strip().lower() in generic)]
    if not targets:
        return rows, 0, True
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(r):
        prompt = (
            "Assign the business-glossary category%s for the term \"%s\".\n"
            "Definition: %s\nPhysical column(s): %s\n"
            "Categories (choose EXACTLY one): %s\n\n"
            "Return JSON with keys: category."
        ) % (
            (" at " + COMPANY) if COMPANY else "",
            r.get("Term", ""), str(r.get("Definition") or "")[:200],
            r.get("Source_Column", "") or "-", ", ".join(cats),
        )
        try:
            return r, _complete_json(prompt, model=model, num_gpu=num_gpu)
        except Exception:
            return r, None

    if workers == 1 or len(targets) <= 1:
        results = [_do(r) for r in targets]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, targets))
    updated = 0
    by_lower = {c.lower(): c for c in cats}
    for r, res in results:
        if not isinstance(res, dict):
            continue
        cat = by_lower.get(str(res.get("category") or "").strip().lower())
        if cat and cat != r.get("Category"):
            r["Category"] = cat
            r["AI_Suggested"] = "Yes"
            updated += 1
    return rows, updated, True


# ------------------------------------------------------------ AI pending-term review
_PENDING_ACTIONS = {"approve": "approve", "reject": "reject", "alias": "alias"}

def _pending_one(item, governed, model=None, num_gpu=None):
    """One candidate-term judgment. Returns the parsed proposal dict or None."""
    bits = []
    if item.get("category"):
        bits.append("category seen: %s" % item["category"])
    if item.get("definition"):
        bits.append("definition: %s" % str(item["definition"])[:200])
    if item.get("sources"):
        bits.append("seen in: %s" % "; ".join(item["sources"][:3]))
    if item.get("sensitivity"):
        bits.append("sensitivity: %s" % item["sensitivity"])
    if item.get("tags"):
        bits.append("tags: %s" % "; ".join(item["tags"][:5]))
    prompt = (
        "You are the data steward%s reviewing a CANDIDATE business term a scan "
        "found, deciding whether it enters the governed vocabulary.\n"
        "Candidate: \"%s\"\n- %s\n\n"
        "Existing governed terms: %s\n\n"
        "Decide ONE action:\n"
        "- approve: a genuine, well-named business concept that belongs in the vocabulary.\n"
        "- alias: the SAME concept as one existing governed term (a synonym, "
        "abbreviation or misspelling of it) - name that term as target.\n"
        "- reject: scan noise, a fragment, a technical artifact, or too vague "
        "to govern.\n\n"
        "Return JSON with keys: action (approve, alias or reject), target (the "
        "existing governed term when action is alias, else empty), rationale "
        "(one short sentence)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        item.get("name", ""),
        "\n- ".join(bits) if bits else "(no context captured)",
        ", ".join(governed[:80]) or "(none)",
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def review_pending_terms(pending, governed, model=None, compute=None, workers=None):
    """AI adjudication of scan-found candidate terms. For each pending item the
       model proposes approve / alias-of / reject with a rationale; guardrails:
       the action must be one of the three, an alias target must be an existing
       governed term (else the advice downgrades to approve), and nothing is
       applied - the steward clicks. Returns ({name: {action, target, reason}},
       used_llm)."""
    pending = [x for x in (pending or []) if isinstance(x, dict) and x.get("name")]
    gov = [str(g) for g in (governed or []) if str(g).strip()]
    if not pending or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    gov_lower = {g.lower(): g for g in gov}
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(item):
        try:
            return item, _pending_one(item, gov, model=model, num_gpu=num_gpu)
        except Exception:
            return item, None

    if workers == 1 or len(pending) <= 1:
        results = [_do(x) for x in pending]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, pending))

    out = {}
    for item, res in results:
        if not isinstance(res, dict):
            continue
        action = _PENDING_ACTIONS.get(str(res.get("action") or "").strip().lower())
        if not action:
            continue
        target = gov_lower.get(str(res.get("target") or "").strip().lower(), "")
        if action == "alias" and not target:
            action = "approve"                     # bad target: fail safe
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        out[item["name"]] = {"action": action, "target": target,
                             "reason": ("AI: " + why) if why else "AI review"}
    return out, True


# ------------------------------------------------------------ AI domain pick
def suggest_domain(company, categories, terms, domains, model=None, compute=None):
    """Pick the ONE PDC business-domain classifier that best fits this company,
       from the caller-supplied list. Guardrail: the answer must be in the list
       (else None). Returns (domain|None, used_llm)."""
    doms = [str(d) for d in (domains or []) if str(d).strip()]
    if not doms or not status(model)["online"]:
        return None, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    prompt = (
        "Classify the business domain of this organization for a data catalog.\n"
        "Company: %s\n"
        "Glossary categories: %s\n"
        "Sample business terms: %s\n\n"
        "Choose EXACTLY one domain from this list: %s\n"
        "Return JSON with keys: domain."
    ) % (
        company or "(unknown)",
        ", ".join((categories or [])[:12]) or "(none)",
        ", ".join((terms or [])[:15]) or "(none)",
        ", ".join(doms),
    )
    res = _complete_json(prompt, model=model, num_gpu=num_gpu)
    if isinstance(res, dict):
        by_lower = {d.lower(): d for d in doms}
        return by_lower.get(str(res.get("domain") or "").strip().lower()), True
    return None, True


# ------------------------------------------------------------ AI term matcher
def match_terms(items, model=None, compute=None, workers=None):
    """Resolve-stage adjudicator: an outstanding term name (usually renamed or
       disambiguated locally AFTER the glossary was imported) against the
       candidate term names that actually exist in PDC. The model picks the
       candidate that is the SAME business concept, or none. Guardrails: the
       answer must be one of the candidates; nothing is bound automatically —
       the steward clicks. items: [{name, definition?, candidates: [names]}].
       Returns ({name: {match|None, reason}}, used_llm)."""
    items = [x for x in (items or [])
             if isinstance(x, dict) and x.get("name") and x.get("candidates")]
    if not items or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass

    def _do(it):
        prompt = (
            "A business glossary term was renamed locally AFTER the glossary was "
            "imported into the data catalog, so its old name still lives there.\n"
            "Local term: \"%s\"\n%s"
            "Candidate terms that exist in the catalog: %s\n\n"
            "Pick the ONE candidate that is the SAME business concept (an earlier "
            "name, a less/more qualified form, an abbreviation), or none if none "
            "match. Return JSON with keys: match (the candidate name or empty), "
            "rationale (one short sentence)."
        ) % (
            it["name"],
            ("Definition: %s\n" % str(it["definition"])[:200]) if it.get("definition") else "",
            ", ".join(it["candidates"][:25]),
        )
        try:
            return it, _complete_json(prompt, model=model, num_gpu=num_gpu)
        except Exception:
            return it, None

    if workers == 1 or len(items) <= 1:
        results = [_do(x) for x in items]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, items))

    out = {}
    for it, res in results:
        if not isinstance(res, dict):
            continue
        by_lower = {c.lower(): c for c in it["candidates"]}
        match = by_lower.get(str(res.get("match") or "").strip().lower())
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        out[it["name"]] = {"match": match,
                           "reason": ("AI: " + why) if why else ("AI match" if match else "AI: no candidate is the same concept")}
    return out, True
