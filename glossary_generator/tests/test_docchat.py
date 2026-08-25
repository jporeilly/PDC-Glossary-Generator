"""Docs-chat evals (spec backlog 10, doctrine 5: eval tests from birth).

A docs chat without evals degrades silently: reorganise a doc, break the
chunker, and retrieval quietly rots while the UI still answers. This canned
QA set pins that the questions stewards actually asked retrieve the sections
that answer them — deterministic (retrieval only, no model), so it runs in
every suite.
"""
from engine import docchat


def _hit_texts(question, page=None, k=6):
    hits = docchat.search(question, page=page, k=k, version="test")
    return [(h["doc"], h["heading"], h["text"]) for h in hits]


class TestRetrievalEvals:
    def test_dictionaries_fire_but_patterns_dont_finds_buildsamples(self):
        """THE canonical eval from the spec: the 2026-08-22 investigation's
           answer lives in the CHANGELOG and must be retrievable by the
           question a steward would actually ask."""
        hits = _hit_texts("why do my dictionaries fire but not my patterns?")
        assert any("buildSamples" in t for _, _, t in hits), \
            [f"{d} - {h}" for d, h, _ in hits]

    def test_zero_stars_finds_the_rater_fix(self):
        hits = _hit_texts("ratings show 0 stars on every column")
        assert any("rater" in t or "users" in t for _, _, t in hits), \
            [f"{d} - {h}" for d, h, _ in hits]

    def test_factory_reset_is_covered(self):
        hits = _hit_texts("how do I factory reset the app?")
        assert any("factory reset" in t.lower() for _, _, t in hits)

    def test_import_walkthrough_is_covered(self):
        hits = _hit_texts("how do I import the glossary JSONL into PDC?")
        docs = {d for d, _, _ in hits}
        assert docs & {"GUIDE", "WALKTHROUGH", "REFERENCE"}, docs

    def test_page_context_boosts_its_own_sections(self):
        """Doctrine 3: the same question asked FROM the Review page should
           rank Review-headed sections at least as high as without context."""
        plain = docchat.search("how do duplicates get resolved", k=8, version="test")
        boosted = docchat.search("how do duplicates get resolved", page="review",
                                 k=8, version="test")
        def rank_of_review(hits):
            for i, h in enumerate(hits):
                if "review" in (h["heading"] + " " + h["doc"]).lower():
                    return i
            return len(hits)
        assert rank_of_review(boosted) <= rank_of_review(plain)


class TestGroundedOrRefuse:
    def test_no_model_degrades_to_cited_search(self):
        """Doctrine 4: with ai=False the feature is a doc search — hits and
           citations present, nothing invented, grounded stays False."""
        out = docchat.answer("why do my dictionaries fire but not my patterns?",
                             ai=False, version="test")
        assert out["hits"] and out["cited"]
        assert out["grounded"] is False and out["used_llm"] is False
        assert "answer" not in out

    def test_nonsense_gets_the_honest_miss(self):
        out = docchat.answer("zzqx flurble kwyjibo", ai=False, version="test")
        assert out["hits"] == []
        assert "doesn't appear to cover" in out["answer"]

    def test_index_is_stamped_with_the_running_version(self):
        idx = docchat.get_index("9.9.9-test")
        assert idx["version"] == "9.9.9-test"
        assert len(idx["chunks"]) > 100, "the shipped corpus should chunk richly"


class TestPackagingGuards:
    def test_categories_is_covered(self):
        """Field 2026-08-24: "can you please explain categories?" refused in
           the installed app - because the corpus never shipped, not because
           the docs lack it. Pin that the corpus answers it."""
        hits = docchat.search("can you please explain categories?", version="test")
        assert hits, "the corpus must cover categories"
        assert any("categor" in (h["heading"] + h["text"]).lower() for h in hits)

    def test_empty_corpus_says_packaging_not_docs(self, monkeypatch):
        """An empty index is an installation defect and must SAY so - never
           'the documentation doesn't cover this', which slanders a corpus
           that was never consulted."""
        monkeypatch.setattr(docchat, "DOCS", [])
        monkeypatch.setattr(docchat, "_INDEX", None)
        out = docchat.answer("anything at all", ai=False, version="empty-test")
        assert "installation defect" in out["answer"]
        docchat._INDEX = None   # rebuild for later tests

    def test_stage_script_ships_the_corpus(self):
        """The chat is only as good as what the installer stages."""
        import pathlib
        stage = (pathlib.Path(docchat._ROOT) / "desktop" / "scripts"
                 / "stage-app.ps1").read_text(encoding="utf-8")
        assert 'Join-Path $repoRoot "docs"' in stage
        assert 'README.md' in stage


class TestFileCheck:
    """W21: 'lets say i want to check my JSONL for errors' - the uploaded-file
       validator against the contract Generate itself writes. Deterministic:
       the app's own export must round-trip clean, and each field-caught trap
       (ampersand names, uppercase tags, BOM, orphans) must be named."""

    def _own_export(self):
        from engine import sug_generate
        from conftest import make_row
        rows = [make_row("Customer Name", "awc.customers.customer_name",
                         Category="Customer Management",
                         Definition="The account holder's name.",
                         Suggested_Tags="pii;privacy",
                         Critical_Data_Element="No", Sensitivity="HIGH"),
                make_row("Turbidity (ntu)", "awc.samples.turbidity_ntu",
                         Category="Water Quality and Compliance",
                         Definition="Measured water turbidity.",
                         Critical_Data_Element="No", Sensitivity="LOW")]
        recs = sug_generate.to_jsonl_records(rows, "AWC Check")
        return sug_generate.records_to_jsonl(recs)

    def test_the_apps_own_export_round_trips_clean(self):
        from engine import filecheck
        res = filecheck.check_glossary_jsonl(self._own_export(), name="own.jsonl")
        errs = [f for f in res["findings"] if f["severity"] != "warn"]
        assert errs == [], errs
        assert res["repaired"] is None
        assert res["counts"]["term"] == 2 and res["counts"]["glossary"] == 1
        assert "IMPORTABLE as-is" in res["summary"]

    def test_broken_line_reports_its_number_and_traps_are_named(self):
        from engine import filecheck
        import json as _json
        lines = self._own_export().splitlines()
        # sabotage: malformed line, '&' name, UPPER tag, blank line, BOM
        rec = _json.loads(lines[-1])
        rec["name"] = "Water Quality & Compliance"
        rec["attributes"]["tags"] = [{"name": "PII"}]
        lines[-1] = _json.dumps(rec)
        text = "﻿" + "\n".join(lines[:2] + ["{not json"] + [""] + lines[2:])
        res = filecheck.check_glossary_jsonl(text, name="bad.jsonl")
        codes = {f["code"] for f in res["findings"]}
        assert {"bom", "parse", "blank-line", "ampersand", "tag-case"} <= codes, codes
        parse = next(f for f in res["findings"] if f["code"] == "parse")
        assert parse["line"] == 3 and parse["severity"] == "error"
        assert res["repaired"] is not None
        # the repaired file has only the non-mechanical problems left
        again = filecheck.check_glossary_jsonl(res["repaired"], name="r.jsonl")
        codes2 = {f["code"] for f in again["findings"]}
        assert "bom" not in codes2 and "tag-case" not in codes2 \
            and "blank-line" not in codes2
        assert "parse" in codes2 and "ampersand" in codes2, \
            "identity and true breakage are never silently rewritten"

    def test_duplicate_ids_and_orphan_terms_are_errors(self):
        from engine import filecheck
        import json as _json
        lines = self._own_export().splitlines()
        term = _json.loads(lines[-1])
        dup = dict(term); dup["name"] = "Twin"
        orphan = dict(term); orphan["_id"] = "ffffffffffffffffffffffff"
        orphan["parentId"] = "eeeeeeeeeeeeeeeeeeeeeeee"; orphan["name"] = "Orphan"
        text = "\n".join(lines + [_json.dumps(dup), _json.dumps(orphan)]) + "\n"
        res = filecheck.check_glossary_jsonl(text, name="dup.jsonl")
        codes = {f["code"] for f in res["findings"]}
        assert {"duplicate-id", "orphan-term"} <= codes, codes
        assert "NOT importable" in res["summary"]

    def test_check_file_endpoint_serves_findings_and_context(self, client):
        res = client.post("/api/check-file",
                          json={"name": "x.jsonl", "content": self._own_export()})
        d = res.json()
        assert d["summary"].startswith("x.jsonl:")
        assert d["context_note"].startswith("[YOUR FILE - x.jsonl]")
        bad = client.post("/api/check-file", json={"content": ""})
        assert bad.status_code == 400
