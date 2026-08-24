"""Docs-grounded chat — "how do I?" answered FROM the shipped documentation
(spec backlog 10, requested 2026-08-22: "the app is complex... a chat window
should answer product questions from the documentation").

Doctrine, settled at design time:
  1. GROUNDED OR REFUSE. Answers come only from the shipped docs, every
     answer cites its sections, and "the documentation doesn't answer this —
     nearest section is X" is the honest miss. The model never invents
     behaviour.
  2. The index is built from THE INSTALLED BUILD'S OWN docs (they ship in
     the installer — stage-app copies docs/), stamped with the running
     version at build. The spec's release-time train step existed to
     guarantee answers describe the installed build; indexing the shipped
     files at startup gives the same guarantee with no generated artifact.
  3. Context-aware seeding: the page the question is asked from boosts its
     own sections.
  4. Retrieval stays boring: BM25 over heading chunks, deterministic and
     dependency-free. With no model at all the feature degrades to a decent
     doc SEARCH rather than vanishing.
  5. Eval-tested from birth (tests/test_docchat.py): a canned QA set pins
     retrieval — a docs chat without evals degrades silently.
"""
import math
import re
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
# the corpus, versioned with the code and shipped inside the app
DOCS = [
    ("GUIDE", _ROOT / "docs" / "GUIDE.md"),
    ("WALKTHROUGH", _ROOT / "docs" / "WALKTHROUGH.md"),
    ("REFERENCE", _ROOT / "docs" / "REFERENCE.md"),
    ("CHANGELOG", _ROOT / "docs" / "CHANGELOG.md"),
    ("README", _ROOT / "README.md"),
]

_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_HEAD = re.compile(r"^(#{1,3})\s+(.*)$")
_MAX_CHUNK = 2400   # characters; long sections split so one chunk = one idea


def _tokens(text):
    return _WORD.findall(str(text).lower())


def _chunk_doc(name, path):
    """Split one markdown file into heading-scoped chunks."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    heading, buf = name, []

    def flush():
        text = "\n".join(buf).strip()
        buf.clear()
        if not text:
            return
        # a very long section splits on paragraph seams, heading carried
        while len(text) > _MAX_CHUNK:
            cut = text.rfind("\n\n", 0, _MAX_CHUNK)
            cut = cut if cut > 200 else _MAX_CHUNK
            piece, text = text[:cut].strip(), text[cut:].strip()
            if piece:
                yield {"doc": name, "heading": heading, "text": piece}
        if text:
            yield {"doc": name, "heading": heading, "text": text}

    for ln in lines:
        m = _HEAD.match(ln)
        if m:
            yield from flush()
            heading = m.group(2).strip() or heading
        else:
            buf.append(ln)
    yield from flush()


_LOCK = threading.Lock()
_INDEX = None    # {"version", "chunks": [...], "df": {}, "avg_len": float}


def build_index(version=""):
    """Chunk the shipped docs and precompute BM25 statistics."""
    chunks = []
    for name, path in DOCS:
        chunks.extend(_chunk_doc(name, path))
    df = {}
    total_len = 0
    for c in chunks:
        toks = _tokens(c["heading"] + " " + c["text"])
        c["_toks"] = toks
        c["_tf"] = {}
        for t in toks:
            c["_tf"][t] = c["_tf"].get(t, 0) + 1
        total_len += len(toks)
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    return {"version": version, "chunks": chunks, "df": df,
            "avg_len": (total_len / len(chunks)) if chunks else 1.0}


def get_index(version=""):
    """The process-wide index, built once from the shipped docs."""
    global _INDEX
    with _LOCK:
        if _INDEX is None or (_INDEX.get("version") or "") != (version or ""):
            _INDEX = build_index(version)
        return _INDEX


_K1, _B = 1.5, 0.75


def search(query, page=None, k=6, version=""):
    """BM25 over the heading chunks. A term hit in the HEADING outranks the
    same hit in the body, and the asking page's own sections get a nudge —
    both multipliers, so relevance stays the driver."""
    idx = get_index(version)
    chunks, df, avg = idx["chunks"], idx["df"], idx["avg_len"]
    n = max(1, len(chunks))
    q = _tokens(query)
    page_toks = set(_tokens(page or ""))
    scored = []
    for c in chunks:
        score = 0.0
        dl = max(1, len(c["_toks"]))
        for t in q:
            tf = c["_tf"].get(t)
            if not tf:
                continue
            idf = math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            score += idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avg))
        if score <= 0:
            continue
        head_toks = set(_tokens(c["heading"]))
        if any(t in head_toks for t in q):
            score *= 1.3
        if page_toks and (page_toks & head_toks or page_toks & set(_tokens(c["doc"]))):
            score *= 1.15
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"doc": c["doc"], "heading": c["heading"], "text": c["text"],
             "score": round(s, 3)} for s, c in scored[:k]]


_PROMPT = """You answer questions about the PDC Glossary Generator from the documentation
excerpts below. Rules:
- Use ONLY facts stated in the excerpts. Never invent behaviour, endpoints or defaults.
- The excerpts were retrieved FOR this question — if one explains the topic the
  question asks about, ANSWER from it in plain language, citing the section
  like [GUIDE - Factory reset]. An excerpt does not need to repeat the
  question's wording to answer it.
- Only when NO excerpt covers the topic, reply exactly:
  NOT ANSWERED: <one sentence naming the nearest relevant section>.
- Be concrete and stepwise; quote exact button and field names from the excerpts.

EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""


def answer(question, page=None, ai=True, model=None, version=""):
    """Retrieve, then (when a model is reachable) compose a grounded, cited
    answer — or degrade to search results, stated honestly."""
    hits = search(question, page=page, k=6, version=version)
    out = {"hits": hits, "grounded": False, "used_llm": False,
           "cited": [{"doc": h["doc"], "heading": h["heading"]} for h in hits[:3]],
           "index_version": version}
    if not hits:
        out["answer"] = ("The documentation doesn't appear to cover this — "
                         "no section matched the question.")
        return out
    if not ai:
        return out
    try:
        from ai import llm
        context = "\n\n".join(
            f"[{h['doc']} - {h['heading']}]\n{h['text'][:1800]}" for h in hits)
        # a single composed answer is worth waiting for — the configured
        # timeout is sized for batch enrichment and a 12B model needs longer
        text = (llm._complete(_PROMPT.format(context=context, question=question),
                              model=model, timeout=120) or "").strip()
    except Exception:
        text = ""
    if not text:
        return out          # no model — honest degrade to search
    out["used_llm"] = True
    if text.upper().startswith("NOT ANSWERED"):
        out["answer"] = ("The documentation doesn't answer this. "
                         + text.split(":", 1)[-1].strip())
        return out
    out["answer"] = text
    out["grounded"] = True
    return out
