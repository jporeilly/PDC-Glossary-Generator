"""The Glossary half of the no-seed feedback loop (1.11.0).

Registry writer: every concept states its detection intent — "seeded" when it
carries induced/curated detection seeds, "mapping_only" when the steward
flagged the row (Detection toggle on the Review grid; the flag always wins),
and the field is OMITTED when neither applies (that gap is what makes the
Policy Generator write a seed-request).

Seed-request pickup: the Policy Generator drops seed-request*.json into the
registries/ directory; GET /api/seed-requests lists the pending ones and
POST /api/seed-requests/handle renames a file to *.handled.json.
"""
import json
import os

from conftest import make_row as _row

REG_DIR = os.environ["GLOSSARY_REGISTRY_DIR"]


class TestDetectionIntent:
    def _concept(self, **kw):
        from registry.bridge import build_registry
        reg = build_registry([_row("Loop Term", "s.t.loop_col", **kw)], "Seed Loop G")
        assert len(reg["concepts"]) == 1
        return reg["concepts"][0]

    def test_seeded_when_profiled_seeds_exist(self):
        c = self._concept(Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn")
        assert c["detect"] and c["detection_intent"] == "seeded"

    def test_mapping_only_flag_wins_over_seeds(self):
        c = self._concept(Value_Pattern=r"^CSCU-\d{6}$", Detection_Intent="mapping_only")
        assert c["detect"], "the seeds still travel — only the intent changes"
        assert c["detection_intent"] == "mapping_only"

    def test_omitted_when_no_seeds_and_no_flag(self):
        c = self._concept()
        assert c["detect"] == []
        assert "detection_intent" not in c, \
            "no seeds + no steward flag -> field absent (legacy shape; Policy may request seeds)"


class TestSeedRequestEndpoints:
    def _write(self, name="seed-request.json"):
        os.makedirs(REG_DIR, exist_ok=True)
        req = {"requested_at": "2026-07-18T12:00:00Z",
               "registry_file": "registry.deadbeef.json",
               "terms": [{"name": "Member Name", "reason": "no_seed"},
                         {"name": "Notes", "reason": "no_seed"}]}
        with open(os.path.join(REG_DIR, name), "w", encoding="utf-8") as f:
            json.dump(req, f)
        return name

    def test_list_then_handle_roundtrip(self, client):
        name = self._write()
        d = client.get("/api/seed-requests").json()
        mine = [r for r in d["requests"] if r["file"] == name]
        assert mine and mine[0]["registry_file"] == "registry.deadbeef.json"
        assert [t["name"] for t in mine[0]["terms"]] == ["Member Name", "Notes"]

        h = client.post("/api/seed-requests/handle", json={"file": name}).json()
        assert h["handled"] == name and h["renamed_to"] == "seed-request.handled.json"
        assert os.path.isfile(os.path.join(REG_DIR, h["renamed_to"]))
        assert not os.path.exists(os.path.join(REG_DIR, name))
        # handled files stop showing but keep the paper trail on disk
        d2 = client.get("/api/seed-requests").json()
        assert all(r["file"] != name for r in d2["requests"])

    def test_handle_rejects_bad_names(self, client):
        # not a seed-request file (also covers traversal — basename() strips dirs)
        r = client.post("/api/seed-requests/handle", json={"file": "../registry.x.json"})
        assert r.status_code == 400 and "error" in r.json()
        r = client.post("/api/seed-requests/handle", json={"file": "seed-request.handled.json"})
        assert r.status_code == 400
        r = client.post("/api/seed-requests/handle", json={"file": "seed-request.missing.json"})
        assert r.status_code == 404


class TestForeignTermIds:
    """resolve_terms matches on NAME, and PDC's search exposes neither
    glossaryId nor rootId for a term. Field-caught 2026-08-21: ADWR's glossary
    sat alongside Arizona Water, both held a term called "GIS", and the AWC
    concept was about to be bound to ADWR's term id — valid, resolving cleanly,
    in the wrong glossary, and invisible to drift because the contract and the
    catalog agreed about it.

    The app does not need PDC to answer this: it minted the ids it imported.
    """
    def _registry(self, tmp_path):
        import json
        from registry.bridge import build_registry
        from conftest import make_row as _row
        reg = build_registry([_row("GIS", "s.t.gis", Category="Water System Operations"),
                              _row("Meter ID", "s.t.meter_id", Category="Asset Management")],
                             "Arizona Water")
        p = tmp_path / "registry.test.json"
        p.write_text(json.dumps(reg), encoding="utf-8")
        return str(p)

    def test_a_same_named_term_from_another_glossary_is_refused(self, tmp_path):
        import json
        from registry.bridge import backfill_term_ids
        from engine.sug_links import det_term_id
        path = self._registry(tmp_path)
        ours_meter = det_term_id("Arizona Water", "Asset Management", "Meter ID")
        name_map = {"Meter ID": {"id": ours_meter},
                    "GIS": {"id": "5842f70a-6e96-5770-981f-8267a8cf60b9"}}  # ADWR's
        filled = backfill_term_ids(path, name_map, glossary_name="Arizona Water")
        reg = json.loads(open(path, encoding="utf-8").read())
        by = {c["term_name"]: c for c in reg["concepts"]}
        assert filled == 1, "the stranger must not count as filled"
        assert by["Meter ID"]["term_id"] == ours_meter
        assert not by["GIS"].get("term_id"), "bound a concept to another glossary's term"
        assert reg["foreign_term_ids"][0]["term_name"] == "GIS", \
            "a refusal must be reported, not silent"

    def test_our_own_ids_backfill_normally(self, tmp_path):
        import json
        from registry.bridge import backfill_term_ids
        from engine.sug_links import det_term_id
        path = self._registry(tmp_path)
        name_map = {n: {"id": det_term_id("Arizona Water", c, n)}
                    for n, c in (("GIS", "Water System Operations"),
                                 ("Meter ID", "Asset Management"))}
        assert backfill_term_ids(path, name_map, glossary_name="Arizona Water") == 2
        reg = json.loads(open(path, encoding="utf-8").read())
        assert "foreign_term_ids" not in reg, "no strangers, no report"

    def test_the_check_stands_down_when_pdc_minted_its_own_ids(self, tmp_path):
        """If PDC re-mints ids on import, NONE will be ours and provenance can
        no longer tell friend from stranger. Refusing everything then would
        break every estate that behaves that way."""
        import json
        from registry.bridge import backfill_term_ids
        path = self._registry(tmp_path)
        name_map = {"GIS": {"id": "aaaaaaaa-0000-0000-0000-000000000001"},
                    "Meter ID": {"id": "bbbbbbbb-0000-0000-0000-000000000002"}}
        assert backfill_term_ids(path, name_map, glossary_name="Arizona Water") == 2
        reg = json.loads(open(path, encoding="utf-8").read())
        assert "foreign_term_ids" not in reg

    def test_a_name_search_miss_falls_back_to_the_deterministic_id(self, tmp_path):
        """PDC's search chokes on an ampersand in a term name - "Status
        (Infrastructure & Assets)" resolved to nothing while its neighbours
        resolved fine (field-caught 2026-08-23), leaving two dictionary-seeded
        concepts unbound and their methods headed for the name-binding refusal
        at Deploy. When provenance is live (some resolved ids are provably
        ours, so the import preserved our minted ids), the deterministic id IS
        the real id - the same trust basis the deterministic glossaryId fill
        has always used."""
        import json
        from registry.bridge import backfill_term_ids
        from engine.sug_links import det_term_id
        path = self._registry(tmp_path)
        ours_meter = det_term_id("Arizona Water", "Asset Management", "Meter ID")
        # GIS misses entirely (the & class of failure); Meter ID proves provenance
        name_map = {"Meter ID": {"id": ours_meter}}
        filled = backfill_term_ids(path, name_map, glossary_name="Arizona Water")
        reg = json.loads(open(path, encoding="utf-8").read())
        by = {c["term_name"]: c for c in reg["concepts"]}
        assert filled == 2, "the miss must be filled deterministically, and counted"
        assert by["GIS"]["term_id"] == det_term_id("Arizona Water",
                                                   "Water System Operations", "GIS")
        assert reg["deterministic_term_ids"] == ["GIS"], \
            "a deterministic fill must be reported, not silent"

    def test_no_provenance_means_no_deterministic_fill(self, tmp_path):
        """When NONE of the resolved ids are ours, PDC re-minted on import and
        the deterministic id would be an invention - leave the miss unbound."""
        import json
        from registry.bridge import backfill_term_ids
        path = self._registry(tmp_path)
        name_map = {"Meter ID": {"id": "aaaaaaaa-0000-0000-0000-000000000001"}}
        backfill_term_ids(path, name_map, glossary_name="Arizona Water")
        reg = json.loads(open(path, encoding="utf-8").read())
        by = {c["term_name"]: c for c in reg["concepts"]}
        assert not by["GIS"].get("term_id"), \
            "an invented id is worse than an absent one"
        assert "deterministic_term_ids" not in reg
