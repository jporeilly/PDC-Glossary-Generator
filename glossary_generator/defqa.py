"""
defqa.py — definition quality checks for the review rows, before anything imports.

Deterministic linter (always runs, offline): catches the classic glossary
anti-patterns — circular definitions, name echoes, vague filler, near-empty
text, and copy-paste duplicates across different terms. The AI agent
(llm.qa_definitions_rows) then judges the survivors for the subtler problem a
regex can't see: a definition that parses fine but doesn't actually explain the
business meaning. Both only FLAG (and propose) — the steward applies fixes.
"""
from __future__ import annotations
import re

_VAGUE = re.compile(r"^\s*(data|information|details?|values?|fields?)\s+(about|for|of|related to)\b", re.I)
_ECHO = re.compile(r"^\s*(the\s+)?%s\s*[.]?\s*$", re.I)


def _tokens(s):
    return [t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t]


def lint_rows(rows):
    """Deterministic pass. Returns {index: [issues]} over the KEPT rows —
    row order is preserved so the caller can stamp results back."""
    issues = {}
    kept = [(i, r) for i, r in enumerate(rows or [])
            if isinstance(r, dict)
            and str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")]
    # duplicate definitions across DIFFERENT terms (copy-paste drift)
    by_def = {}
    for i, r in kept:
        d = re.sub(r"\s+", " ", str(r.get("Definition") or "")).strip().lower()
        if len(d) > 20:
            by_def.setdefault(d, []).append(i)
    dupes = {i for lst in by_def.values() if len(lst) > 1 for i in lst}
    for i, r in kept:
        term = (r.get("Term") or "").strip()
        d = re.sub(r"\s+", " ", str(r.get("Definition") or "")).strip()
        out = []
        if len(d) < 15:
            out.append("too short to inform (under 15 characters)")
        else:
            tt = set(_tokens(term))
            dt = _tokens(d)
            if tt and dt:
                # circular: the definition is mostly the term's own words
                core = [t for t in dt if t not in ("the", "a", "an", "of", "for", "record", "identifier", "unique")]
                if core and sum(1 for t in core if t in tt) / len(core) >= 0.8:
                    out.append("circular — restates the term instead of explaining it")
            if re.match(_ECHO.pattern % re.escape(term), d) if term else False:
                out.append("echoes the term name only")
            if _VAGUE.match(d):
                out.append("vague opener ('data about…') — say what it IS and why it matters")
        if i in dupes:
            out.append("identical definition shared by multiple different terms")
        if out:
            issues[i] = out
    return issues
