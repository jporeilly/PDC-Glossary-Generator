"""Engine invariants — ports the offline checks the old selftest.py ran into
pytest: tagdict governance lifecycle, the similarity evidence rubric, the
definition linter, the pack flywheel merge, policy drafting guard-rails and
the llm language guard. No PDC, no Ollama, no network."""
import json
import os

import defqa
import llm
import packgen
import policy_draft
import similarity

from conftest import make_row as _row


class TestTagdict:
    def test_lowercase_governance_and_steward_lifecycle(self, fresh_dict):
        tagdict = fresh_dict
        assert tagdict.norm_tag("PII") == "pii"
        tagdict.accrete([_row("Member Number", "cscu_core.members.mbr_no",
                              Suggested_Tags="PII;Identifier", Sensitivity="HIGH"),
                         _row("Column_3", "cscu_core.members.column_3")], persist=True)
        d = tagdict.load()
        assert "Column_3" not in d.get("terms", {}), "junk terms (column_N) blocked at accrete"
        assert (d["terms"].get("Member Number") or {}).get("status") == "pending"
        assert set(d["terms"]["Member Number"].get("tags") or []) >= {"pii", "identifier"}
        assert "Member Number" not in tagdict.governed_terms(), "pending does not govern"
        tagdict.review("term", ["Member Number"], "approve")
        assert "Member Number" in tagdict.governed_terms(), "approve -> governs"
        tagdict.accrete([_row("Mbr No", "cscu_core.cards.mbr_no", Sensitivity="HIGH")], persist=True)
        tagdict.review("term", ["Mbr No"], "alias", target="Member Number")
        d = tagdict.load()
        assert "Mbr No" in (d["terms"]["Member Number"].get("aliases") or [])
        assert "Mbr No" not in d["terms"]
        assert tagdict.alias_index().get("mbr no") == "Member Number"
        tagdict.accrete([_row("Scan Noise", "cscu_core.x.noise")], persist=True)
        tagdict.reset(preserve_approved=True)
        d = tagdict.load()
        assert (d["terms"].get("Member Number") or {}).get("status") == "approved"
        assert "Scan Noise" not in d["terms"], "reset keeps approved, drops pending"
        assert tagdict.lift_sensitivity("LOW", [], term="Member Number") == "HIGH"
        assert tagdict.lift_sensitivity("HIGH", [], term=None) == "HIGH"

    def test_pack_seeded_vocabulary_and_durable_retire(self, fresh_dict):
        tagdict = fresh_dict
        # pack-seeded vocabulary is company/approved and STAYS so across loads
        # (regression: _merge_seed relabeled every pack term generic on load,
        # which locked the whole curated vocabulary out of steward actions)
        with open(os.environ["GLOSSARY_DOMAIN_PACK"], "w", encoding="utf-8") as f:
            json.dump({"domain": "credit_union", "extra_tags": ["pci"],
                       "terms": {"Card Number": {"aliases": ["PAN"], "sensitivity": "HIGH",
                                                 "tags": ["pci"]}}}, f)
        tagdict.reset(preserve_approved=True)
        m = (tagdict.load().get("terms") or {}).get("Card Number") or {}
        assert m.get("layer") == "company" and m.get("status") == "approved"
        assert tagdict.review("term", ["Card Number"], "approve") == 0  # already approved
        assert tagdict.review("term", ["Card Number"], "reject") == 1
        # the reject tombstones the pack entry — retiring is durable
        d2 = tagdict.load()
        assert "Card Number" not in d2.get("terms", {})
        assert "Card Number" in (d2.get("retired") or {}).get("terms", [])
        tagdict.reset(preserve_approved=True)
        assert "Card Number" not in tagdict.load().get("terms", {}), \
            "tombstone survives Reseed"
        pk, rp = packgen.build_pack([], base={"terms": {"Card Number": {
            "aliases": [], "sensitivity": "HIGH", "tags": ["pci"]}}})
        assert "Card Number" not in pk.get("terms", {})
        assert any(c["key"] == "terms" and c["name"] == "Card Number" and c["use"] == "scan"
                   for c in rp["conflicts"]), "pack export removes a retired entry as a conflict row"
        pk2, _ = packgen.build_pack(
            [], base={"terms": {"Card Number": {"aliases": [], "sensitivity": "HIGH",
                                                "tags": ["pci"]}}},
            resolutions={"terms::Card Number": "pack"})
        assert "Card Number" in pk2.get("terms", {}), "pack removal overridable back to keep"
        tagdict.accrete([_row("Card Number", "s.cards.card_no", Sensitivity="HIGH")], persist=True)
        tagdict.review("term", ["Card Number"], "approve")
        d2 = tagdict.load()
        assert "Card Number" in d2.get("terms", {})
        assert "Card Number" not in (d2.get("retired") or {}).get("terms", []), \
            "re-approval lifts the tombstone"


class TestUsageIdempotence:
    """Search-facet preview counts = DISTINCT current terms carrying each tag,
    from identity-keyed sets, not accreted counters. Regression for the day-one
    bug where rescanning the same sources doubled the facet preview ('cde: 281
    terms' with ~141 terms in the dictionary)."""

    ROWS = [_row("Member Number", "cscu_core.members.mbr_no",
                 Suggested_Tags="PII;Identifier", Sensitivity="HIGH"),
            _row("Card Number", "cscu_core.cards.card_no",
                 Suggested_Tags="pii", Sensitivity="HIGH")]

    def _facet(self, tagdict):
        return {x["tag"]: x["count"] for x in tagdict.facet_health()["facet"]}

    def test_rescan_does_not_change_facet_counts(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([dict(r) for r in self.ROWS], source="db", persist=True)
        f1 = self._facet(tagdict)
        assert f1["pii"] == 2, "pii carried by 2 distinct terms"
        assert f1["identifier"] == 1
        # scan the SAME rows again (same source rescanned)
        tagdict.accrete([dict(r) for r in self.ROWS], source="db", persist=True)
        f2 = self._facet(tagdict)
        assert f2 == f1, "rescanning the same rows must not change facet counts"
        s = {t["tag"]: t["count"] for t in tagdict.summary()["tags"]}
        assert s["pii"] == 2 and s["identifier"] == 1
        # per-term count = distinct source columns, also idempotent
        terms = {t["term"]: t["count"] for t in tagdict.summary()["terms"]}
        assert terms["Member Number"] == 1
        # the retire-empty gate rests on "a scan happened" (sources), not counts
        assert "db" in tagdict.load().get("sources", [])
        # junk Column-N rows never become a term identity in the facet
        tagdict.accrete([_row("Column_7", "s.t.column_7", Suggested_Tags="pii")],
                        persist=True)
        assert self._facet(tagdict)["pii"] == 2

    def test_steward_actions_keep_counts_current(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([dict(r) for r in self.ROWS], source="db", persist=True)
        tagdict.review("term", ["Card Number"], "reject")
        assert self._facet(tagdict)["pii"] == 1, "retired term leaves the facet count"
        tagdict.accrete([_row("Mbr No", "cscu_core.cards.mbr_no",
                              Suggested_Tags="pii", Sensitivity="HIGH")], persist=True)
        assert self._facet(tagdict)["pii"] == 2
        tagdict.review("term", ["Mbr No"], "alias", target="Member Number")
        assert self._facet(tagdict)["pii"] == 1, \
            "folding a duplicate merges its usage into the canonical term"
        # empty-bucket detection still works on the derived counts
        assert "cde" in tagdict.facet_health()["empty_governed_tags"]

    def test_steward_save_preserves_usage_and_gate(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([dict(r) for r in self.ROWS], source="db", persist=True)
        s = tagdict.summary()
        # rebuild the doc exactly as the UI's toDoc() does: vocabulary only,
        # with no usage / counts / sources / examples in the payload
        doc = {"schema": s["schema"], "domain": s["domain"],
               "rules": json.loads(json.dumps(s["rules"])),
               "category_tags": json.loads(json.dumps(s["category_tags"])),
               "tags": {t["tag"]: {"label": t["label"], "layer": t["layer"],
                                   **({"status": t["status"]} if t["layer"] != "generic"
                                      and t["status"] != "generic" else {})}
                        for t in s["tags"]},
               "terms": {t["term"]: {"aliases": t["aliases"], "sensitivity": t["sensitivity"],
                                     "tags": t["tags"], "layer": t["layer"],
                                     **({"status": t["status"]} if t["layer"] != "generic"
                                        and t["status"] != "generic" else {})}
                         for t in s["terms"]}}
        tagdict.replace(doc)
        assert self._facet(tagdict)["pii"] == 2, "a steward Save keeps the facet preview"
        assert "db" in tagdict.load().get("sources", []), "and the grown-from-a-scan gate"
        # removing a term in the Save drops its usage key
        doc2 = json.loads(json.dumps(doc))
        doc2["terms"].pop("Card Number")
        tagdict.replace(doc2)
        assert self._facet(tagdict)["pii"] == 1

    def test_legacy_numeric_counts_migrate_to_term_sets(self, fresh_dict):
        tagdict = fresh_dict
        legacy = {"schema": "term-tag-dictionary/1", "domain": "generic",
                  "tags": {"pii": {"label": "PII", "layer": "generic"},
                           "cde": {"label": "Critical Data Element", "layer": "generic"}},
                  "terms": {"Member Number": {"aliases": [], "sensitivity": "HIGH",
                                              "tags": ["pii", "cde"], "layer": "company",
                                              "status": "approved",
                                              "sources": ["cscu_core.members.mbr_no"]}},
                  "counts": {"pii": 281, "cde": 281},      # accreted over many rescans
                  "term_counts": {"Member Number": 12},
                  "examples": {}, "sources": ["db"]}
        with open(os.environ["GLOSSARY_TAG_DICTIONARY"], "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        d = tagdict.load()
        assert "counts" not in d and "term_counts" not in d, "legacy counters dropped"
        f1 = self._facet(tagdict)
        assert f1["pii"] == 1 and f1["cde"] == 1, \
            "unknown-provenance ints rebuilt as distinct scan-grown terms per tag"
        terms = {t["term"]: t["count"] for t in tagdict.summary()["terms"]}
        assert terms["Member Number"] == 1, "term count = distinct source columns"
        assert "db" in d.get("sources", []), "gate evidence survives migration"


class TestSimilarity:
    def test_evidence_rubric(self):
        a = _row("State", "geo.addresses.state_cd", Enum_Values="AZ;CA;NV;UT")
        b = _row("State", "hr.employees.state_cd", Enum_Values="AZ;CA;NV")
        c = _row("State", "wf.tickets.state_cd", Enum_Values="OPEN;CLOSED;PENDING")
        assert similarity.compare_evidence(a, b)[0] == "same"
        assert similarity.compare_evidence(a, c)[0] == "different"
        fk_child = _row("Member Number", "cscu_core.cards.mbr_no",
                        Source_Keys={"cscu_core.cards.mbr_no": {"pk": False, "fk": True,
                                                                "ref": "members.mbr_no"}})
        fk_parent = _row("Member Number", "cscu_core.members.mbr_no")
        assert similarity.compare_evidence(fk_child, fk_parent)[0] == "same", "FK link"
        assert similarity.compare_evidence(
            _row("Id", "s.t1.c", Value_Pattern=r"^A\d{3}$"),
            _row("Id", "s.t2.c", Value_Pattern=r"^B\d{6}$"))[0] == "different"
        assert similarity.compare_value_sets(["a", "b", "c"],
                                             ["A", "B", "c", "d", "e"])[0] == "same"

    def test_advisor_bands(self):
        a = _row("State", "geo.addresses.state_cd", Enum_Values="AZ;CA;NV;UT")
        b = _row("State", "hr.employees.state_cd", Enum_Values="AZ;CA;NV")
        c = _row("State", "wf.tickets.state_cd", Enum_Values="OPEN;CLOSED;PENDING")
        r = similarity.recommend_resolution([a, b])
        assert r["action"] == "merge" and r["band"] == "high"
        r = similarity.recommend_resolution([a, c])  # same category, disjoint enums
        assert r["action"] == "split" and r["band"] == "high"
        r = similarity.recommend_resolution([a, dict(c, Category="Operations")])
        assert r["action"] == "separate" and r["band"] == "high"


class TestDefQA:
    def test_deterministic_linter(self):
        rows = [_row("APR Rate", "s.loans.apr",
                     Definition="Annual percentage rate as a decimal. Regulation Z disclosure value."),
                _row("Memo", "s.tx.memo", Definition="Memo."),
                _row("Member Number", "s.m.no", Definition="The member number of the member."),
                _row("Fee Code", "s.f.c", Definition="Data about fees and other information.")]
        issues = defqa.lint_rows(rows)
        assert 0 not in issues, "clean definition passes"
        assert any("short" in x for x in issues.get(1, []))
        assert any("circular" in x for x in issues.get(2, []))
        assert any("vague" in x for x in issues.get(3, []))


class TestPackgen:
    def test_abbreviation_alignment(self):
        assert packgen._abbrev_pairs("mbr_no", "Member Number") == [("mbr", "Member")]
        assert packgen._abbrev_pairs("state", "State") == []
        assert packgen._abbrev_pairs("x", "Long Name") == []

    def test_merge_conflicts_and_resolutions(self, fresh_dict):
        scan = [_row("Member Number", "cscu_core.members.mbr_no", Category="Customer",
                     Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn"),
                _row("Member Name", "cscu_core.members.full_nm", Category="Customer")]
        base = {"table_category": {"members": "Membership"},
                "curated_seeds": {"Member Number": {"type": "pattern", "regex": r"^\d{6}$",
                                                    "signature": None}},
                "terms": {"Member Number": {"aliases": ["Member ID"], "sensitivity": "LOW",
                                            "tags": ["member"]}}}
        # accrete + approve so the scan side carries the HIGH sensitivity + pii tag
        tagdict = fresh_dict
        tagdict.accrete([_row("Member Number", "cscu_core.members.mbr_no",
                              Suggested_Tags="PII", Sensitivity="HIGH"),
                         _row("Mbr No", "cscu_core.cards.mbr_no", Sensitivity="HIGH")], persist=True)
        tagdict.review("term", ["Member Number"], "approve")
        tagdict.review("term", ["Mbr No"], "alias", target="Member Number")
        pack, rep = packgen.build_pack(scan, base=dict(base))
        conf = {(x["key"], x["name"]): x for x in rep["conflicts"]}
        assert pack["table_category"]["members"] == "Membership", "pack (curation) wins scalars"
        assert conf[("table_category", "members")]["use"] == "pack"
        assert pack["curated_seeds"]["Member Number"]["regex"] == r"^CSCU-\d{6}$", \
            "curated_seeds: fresher scan evidence wins"
        assert conf[("curated_seeds", "Member Number")]["use"] == "scan"
        t = pack["terms"]["Member Number"]
        assert "Member ID" in t["aliases"] and "Mbr No" in t["aliases"]
        assert "pii" in t["tags"] and t["sensitivity"] == "HIGH"
        pack2, _ = packgen.build_pack(scan, base=dict(base),
                                      resolutions={"table_category::members": "scan",
                                                   "curated_seeds::Member Number": "pack"})
        assert pack2["table_category"]["members"] == "Customer"
        assert pack2["curated_seeds"]["Member Number"]["regex"] == r"^\d{6}$"

    def test_sensitivity_loosening_blocked(self, fresh_dict):
        tagdict = fresh_dict
        base3 = {"terms": {"X High": {"aliases": [], "sensitivity": "HIGH", "tags": []}}}
        tagdict.accrete([_row("X High", "s.t.x")], persist=True)  # accretes at LOW
        tagdict.review("term", ["X High"], "approve")
        pack3, rep3 = packgen.build_pack([], base=base3)
        assert pack3["terms"]["X High"]["sensitivity"] == "HIGH"
        assert any(x["key"] == "terms.sensitivity" and x["name"] == "X High"
                   for x in rep3["conflicts"])


class TestPolicyDraft:
    def test_seeds_to_methods_guard_railed(self):
        rows = [_row("Member Number", "cscu_core.members.mbr_no",
                     Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn",
                     Suggested_Tags="pii;identifier"),
                _row("Risk Rating", "cscu_core.kyc.risk_cd", Enum_Values="LOW;MEDIUM;HIGH",
                     Suggested_Tags="compliance"),
                _row("SSN", "cscu_core.members.ssn", PII_Category="GOVERNMENT_ID"),
                _row("Memo Text", "cscu_core.tx.memo_txt")]
        art = policy_draft.draft_from_rows(rows, prefix="CSCU",
                                           hints={"Member Number": {"column_regex": "([bad",
                                                                    "tags": ["pii", "rogue-tag"]}},
                                           governed_tags=["pii", "identifier", "compliance"])
        # Custom-only: patterns come solely from profiled scan evidence. SSN has
        # none, so with the inbuilt canonical shapes removed it is SKIPPED (not
        # given a hardcoded pattern that could drift against the real data).
        assert len(art["patterns"]) == 1
        assert {p["seed"] for p in art["patterns"]} == {"profiled"}
        assert len(art["dictionaries"]) == 1 and "LOW" in art["dictionaries"][0]["csv"]
        assert any(s["term"] == "SSN" for s in art["skipped"])
        assert any(s["term"] == "Memo Text" for s in art["skipped"])
        mn = [p for p in art["patterns"] if p["term"] == "Member Number"][0]
        blob = json.dumps(mn["rule"])
        assert "([bad" not in blob and "rogue-tag" not in blob and '"pii"' in blob, \
            "AI hints guard-railed"

    def test_draft_zips_into_import_bundle(self):
        import io
        import zipfile
        # profiled pattern + profiled dictionary — custom-only, no inbuilt seeds
        rows = [_row("Member Number", "cscu_core.members.mbr_no",
                     Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn"),
                _row("Risk Rating", "cscu_core.kyc.risk_cd", Enum_Values="LOW;MEDIUM;HIGH")]
        art = policy_draft.draft_from_rows(rows, prefix="CSCU", governed_tags=["pii"])
        z = zipfile.ZipFile(io.BytesIO(policy_draft.to_zip_bytes(art)))
        assert len(z.namelist()) >= 3


class TestLLMGuardrails:
    def test_mostly_english(self):
        assert llm._mostly_english("The member's unique account identifier.")
        assert not llm._mostly_english("成员的唯一标识符。")


class TestDetection:
    def test_parse_nvidia_smi_multi_gpu(self):
        import llm_detect
        name, vram, count = llm_detect.parse_nvidia_smi(
            "NVIDIA GeForce RTX 3060, 12288\nNVIDIA GeForce RTX 3060, 12288\n")
        assert count == 2 and name.startswith("2×") and vram == 24.0

    def test_recommend_dual_gpu_sets_sched_spread(self):
        import llm_detect
        rec = llm_detect.recommend(ram_gb=64.0, vram_gb=24.0, gpu_count=2)
        assert rec.env_suggestions.get("OLLAMA_SCHED_SPREAD") == "1"
        assert rec.model  # a concrete model is always recommended
        assert "GPUs" in rec.reason

    def test_recommend_cpu_floor(self):
        import llm_detect
        rec = llm_detect.recommend(ram_gb=8.0, vram_gb=None, gpu_count=0)
        assert rec.model == "llama3.2:1b"
        assert "OLLAMA_SCHED_SPREAD" not in rec.env_suggestions


class TestDataQualityScore:
    """DQ scores must be earned by measurement — never manufactured by the
    NOT-NULL fallback when nothing was profiled (the 'wall of DQ 100s')."""

    def test_unprofiled_column_scores_none_not_100(self):
        import suggester
        # pasted-DDL / unprofiled scan: no dimensions measured — a NOT NULL
        # constraint alone must not assert perfect quality
        assert suggester.quality_score_column(notnull=True) is None
        assert suggester.quality_score_column() is None
        assert suggester.quality_score_column(notnull=True, expect_unique=True) is None

    def test_notnull_proxy_still_counts_alongside_a_real_measurement(self):
        import suggester
        q = suggester.quality_score_column(validity=0.5, notnull=True)
        assert q == round((0.4 * 1.0 + 0.3 * 0.5) / 0.7 * 100)

    def test_profiled_dimensions_score_and_renormalise(self):
        import suggester
        assert suggester.quality_score_column(completeness=1.0) == 100
        assert suggester.quality_score_column(completeness=0.5) == 50
        q = suggester.quality_score_column(completeness=1.0, uniqueness=0.8,
                                           expect_unique=True)
        assert q == round((0.4 * 1.0 + 0.3 * 0.8) / 0.7 * 100)

    def test_data_element_links_leave_unprofiled_quality_empty(self):
        import suggester
        rows = [_row("Member Number", "cscu_core.members.mbr_no",
                     Source_Quality_Dims={"cscu_core.members.mbr_no":
                                          {"c": None, "u": None, "v": None,
                                           "eu": True, "nn": True}}),
                _row("Member Name", "cscu_core.members.full_nm",
                     Source_Quality_Dims={"cscu_core.members.full_nm":
                                          {"c": 0.9, "u": 0.5, "v": None,
                                           "eu": False, "nn": False}})]
        links = suggester.data_element_links(rows, policy={"mode": "all"})
        by = {l["column_name"]: l for l in links}
        assert by["mbr_no"]["quality"] is None, "unprofiled -> no score, not 100"
        assert by["full_nm"]["quality"] == 90, "measured completeness scores as before"
