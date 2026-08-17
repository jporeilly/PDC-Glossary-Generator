"""
suggester.py - core glossary-suggestion logic (importable).

Stages, all pure functions so both the CLI and the web app reuse them:
  harvest_ddl(path) / harvest_live(dsn)  -> {table: [column dicts]}
  suggest(tables)                        -> [row dicts]  (candidate terms)
  to_jsonl_records(rows, glossary_name)  -> [PDC objects] (glossary+cats+terms)

A "row" is the steward-facing review record (also what the UI edits).

FACADE (carved 1.38.18): the 3,100-line implementation now lives in role
modules - sug_harvest (relational harvest), sug_profile (value profiling),
sug_suggest (term suggestion), sug_docs (document store + doc DQ),
sug_links (enhance/ids/links), sug_generate (JSONL + checks), sug_shared
(cross-module constants) - and this module re-exports every public and
single-underscore name from each, the same shim pattern sources/pdc_api.py
uses over pdc_client, so every existing `from engine.suggester import X`
keeps working unchanged.

NOTE for tests and tools: MONKEYPATCH THE OWNING MODULE (for example
engine.sug_suggest.CAT_KEYWORDS, engine.sug_docs._s3_client) - rebinding a
name on this facade does not reach back into the module whose functions
read it.
"""
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS   # noqa: F401
from engine import (sug_harvest as _m1, sug_suggest as _m2, sug_profile as _m3,
                    sug_docs as _m4, sug_links as _m5, sug_generate as _m6)

for _mod in (_m1, _m2, _m3, _m4, _m5, _m6):
    for _n in dir(_mod):
        if not _n.startswith("__"):
            globals()[_n] = getattr(_mod, _n)
del _mod, _n
