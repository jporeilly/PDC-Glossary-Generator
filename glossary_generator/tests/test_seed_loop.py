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
