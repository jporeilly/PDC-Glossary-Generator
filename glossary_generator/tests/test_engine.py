"""Engine invariants — ports the offline checks the old selftest.py ran into
pytest: tagdict governance lifecycle, the similarity evidence rubric, the
definition linter, the pack flywheel merge, policy drafting guard-rails and
the llm language guard. No PDC, no Ollama, no network."""
import json
import os

from engine import defqa
from ai import llm
from engine import packgen
from engine import policy_draft
from engine import similarity
from engine import suggester

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
        # Was 'separate' — on the reasoning that differing categories let PDC hold
        # two same-named terms. PDC can; Resolve cannot, because it matches purely
        # by name and takes the first hit. Different concepts sharing a name must
        # be renamed whatever their categories, so this is 'split' now.
        r = similarity.recommend_resolution([a, dict(c, Category="Operations")])
        assert r["action"] == "split" and r["band"] == "high"


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

    def test_small_reference_tables_still_profile_as_enums(self):
        """A flat n >= 10 floor starved exactly the most reference-y tables
           there are: 8 water systems' counties and types carried NO enum
           while a busy billing table's status did (field: "a pattern or
           values must be available?"). The floor is now relative — each
           value seen about twice — and the key-prune guard (near-unique
           stays out) is untouched."""
        vals = ["Maricopa", "Pima", "Maricopa", "Pinal", "Pima",
                "Maricopa", "Pinal", "Maricopa"]           # 8 rows, 3 distinct
        prof = suggester._profile_values("county", vals, len(vals))
        assert prof.get("kind") == "enum", prof
        assert set(prof["enum"]) == {"Maricopa", "Pima", "Pinal"}
        ids = [f"ID{i}" for i in range(10)]                 # 10 rows, all distinct
        prof2 = suggester._profile_values("code", ids, len(ids))
        assert prof2.get("kind") != "enum", \
            "near-unique values must never read as reference data"
        # NULLs must not starve the gate: 8 sampled rows, 3 null — the 5
        # non-null values are Compliant×3 / Warning×2, reference data by any
        # honest reading (live-caught on system_water_quality_status)
        vals3 = [None, "Compliant", None, "Warning", "Compliant",
                 None, "Warning", "Compliant"]
        prof3 = suggester._profile_values("compliance_status", vals3, len(vals3))
        assert prof3.get("kind") == "enum", prof3
        assert set(prof3["enum"]) == {"Compliant", "Warning"}

    def test_skip_reason_tells_profiled_from_unprofiled(self):
        """"no profiled evidence — re-scan with profiling on" was wrong
           advice for rows profiling DID touch (numeric content induces no
           shape). The reason now says which case the steward is in."""
        rows = [_row("Ph Level", "awc.quality.ph_level",
                     Suggested_Reason="Profiled"),
                _row("Mystery Field", "awc.quality.mystery_field")]
        art = policy_draft.draft_from_rows(rows, prefix="AWC")
        why = {s["term"]: s["why"] for s in art["skipped"]}
        assert why["Ph Level"].startswith("profiled, but"), why
        assert why["Mystery Field"].startswith("no profiled evidence"), why

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
        from ai import llm_detect
        name, vram, count = llm_detect.parse_nvidia_smi(
            "NVIDIA GeForce RTX 3060, 12288\nNVIDIA GeForce RTX 3060, 12288\n")
        assert count == 2 and name.startswith("2×") and vram == 24.0

    def test_recommend_dual_gpu_sets_sched_spread(self):
        from ai import llm_detect
        rec = llm_detect.recommend(ram_gb=64.0, vram_gb=24.0, gpu_count=2)
        assert rec.env_suggestions.get("OLLAMA_SCHED_SPREAD") == "1"
        assert rec.model  # a concrete model is always recommended
        assert "GPUs" in rec.reason

    def test_recommend_cpu_floor(self):
        from ai import llm_detect
        rec = llm_detect.recommend(ram_gb=8.0, vram_gb=None, gpu_count=0)
        assert rec.model == "llama3.2:1b"
        assert "OLLAMA_SCHED_SPREAD" not in rec.env_suggestions


class TestDataQualityScore:
    """DQ scores must be earned by measurement — never manufactured by the
    NOT-NULL fallback when nothing was profiled (the 'wall of DQ 100s')."""

    def test_unprofiled_column_scores_none_not_100(self):
        from engine import suggester
        # pasted-DDL / unprofiled scan: no dimensions measured — a NOT NULL
        # constraint alone must not assert perfect quality
        assert suggester.quality_score_column(notnull=True) is None
        assert suggester.quality_score_column() is None
        assert suggester.quality_score_column(notnull=True, expect_unique=True) is None

    def test_notnull_proxy_still_counts_alongside_a_real_measurement(self):
        from engine import suggester
        q = suggester.quality_score_column(validity=0.5, notnull=True)
        assert q == round((0.4 * 1.0 + 0.3 * 0.5) / 0.7 * 100)

    def test_profiled_dimensions_score_and_renormalise(self):
        from engine import suggester
        assert suggester.quality_score_column(completeness=1.0) == 100
        assert suggester.quality_score_column(completeness=0.5) == 50
        q = suggester.quality_score_column(completeness=1.0, uniqueness=0.8,
                                           expect_unique=True)
        assert q == round((0.4 * 1.0 + 0.3 * 0.8) / 0.7 * 100)

    def test_data_element_links_leave_unprofiled_quality_empty(self):
        from engine import suggester
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


class TestDuplicateNamesMustBecomeDistinctTerms:
    """A duplicate group is keyed ON the shared name. If the evidence says the
       members are different concepts, the only safe action is to RENAME them:
       pdc_client.terms.resolve_terms matches by name and takes the first hit,
       so two terms called "Status" resolve to whichever PDC returns first and
       one group's columns get silently mis-linked. A differing category does
       not rescue it — PDC can store both, but Resolve still cannot tell them
       apart."""

    def _rows(self, cat_a, cat_b):
        from conftest import make_row
        return [make_row("Status", "db.accounts.status", Category=cat_a,
                         Enum_Values="OPEN;CLOSED", Keep="Yes"),
                make_row("Status", "db.loans.status", Category=cat_b,
                         Enum_Values="CURRENT;DEFAULT", Keep="Yes")]

    def test_same_category_disambiguates(self):
        from engine import similarity
        rec = similarity.recommend_resolution(self._rows("Account", "Account"))
        assert rec["action"] == "split"

    def test_differing_category_also_disambiguates(self):
        """The regression: this used to recommend 'separate' because PDC can
           hold two same-named terms in different categories — which is true,
           and irrelevant, because Resolve never looks at the category."""
        from engine import similarity
        rec = similarity.recommend_resolution(self._rows("Governance", "Billing & Rates"))
        assert rec["action"] == "split", \
            "different concepts sharing a name must be renamed, whatever their categories"
        assert rec["band"] == "high"
        assert "resolve" in rec["reason"].lower()


class TestQualityFromPdcStats:
    """Where PDC has profiled a column server-side, its measurements are better
       evidence than the app's own partial sampling — and for formats the app
       cannot read at all, they are the ONLY evidence."""

    def test_derives_a_score_from_pdc_density(self):
        from engine import suggester
        # a fully populated column PDC profiled: density 100%
        assert suggester.quality_from_pdc_stats({"density": 100}) == 100

    def test_accepts_percentages_or_fractions(self):
        from engine import suggester
        assert (suggester.quality_from_pdc_stats({"density": 75})
                == suggester.quality_from_pdc_stats({"density": 0.75}))

    def test_uniqueness_counts_only_where_expected(self):
        """A low-cardinality enum must not be marked poor quality for repeating."""
        from engine import suggester
        stats = {"density": 100, "uniqueness": 10}
        assert suggester.quality_from_pdc_stats(stats, expect_unique=False) == 100
        assert suggester.quality_from_pdc_stats(stats, expect_unique=True) < 100

    def test_unprofiled_returns_none_not_zero(self):
        """The same rule the column scorer follows: no measurement, no score."""
        from engine import suggester
        assert suggester.quality_from_pdc_stats({}) is None
        assert suggester.quality_from_pdc_stats({"cardinality": 8}) is None
        assert suggester.quality_from_pdc_stats(None) is None

    def test_reads_pdc_alias_spellings(self):
        from engine import suggester
        assert suggester.quality_from_pdc_stats({"nonNullDensity": 100}) == 100


class TestFormatIdentityIsNotConceptIdentity:
    r"""`identical induced value format` was scored as 'same concept' for ANY
        matching regex. On a real glossary that ranked lead_ppb ← turbidity_ntu
        and tier1_rate ← tier2_rate at 0.85 'strong' — above the one genuinely
        correct merge in the same run — because ^0\.\d{2}$ merely means "a small
        decimal". Merging those would put a regulated contaminant's limits on the
        wrong term."""

    def _rows(self, pat):
        return ({"Term": "A", "Value_Pattern": pat, "Source_Column": "s.t.a"},
                {"Term": "B", "Value_Pattern": pat, "Source_Column": "s.t.b"})

    def test_a_bare_number_is_no_longer_evidence_of_one_concept(self):
        from engine import similarity
        for pat in (r"^0\.\d{2}$", r"^\d\.\d{4}$", r"^\d{6}$", r"^\d+$"):
            a, b = self._rows(pat)
            verdict, why = similarity.compare_evidence(a, b)
            assert verdict is None, (pat, verdict)
            assert "too generic" in why

    def test_a_minted_code_still_is(self):
        """A prefixed key is issued by one system for one purpose."""
        from engine import similarity
        for pat in (r"^AWC-[A-Z]{2}-\d{6}$", r"^CSCU-\d{6}$"):
            a, b = self._rows(pat)
            verdict, why = similarity.compare_evidence(a, b)
            assert verdict == "same", (pat, verdict)
            assert "identical induced value format" in why

    def test_differing_formats_still_say_different(self):
        from engine import similarity
        a = {"Term": "A", "Value_Pattern": r"^\d{6}$", "Source_Column": "s.t.a"}
        b = {"Term": "B", "Value_Pattern": r"^AWC-\d{6}$", "Source_Column": "s.t.b"}
        verdict, _ = similarity.compare_evidence(a, b)
        assert verdict == "different"

    def test_the_bias_is_toward_asking_the_steward(self):
        """A letter CLASS is a shape, not a minted marker. Returning None sends
           it to the steward; a false 'same' would merge unrelated concepts."""
        from engine import similarity
        assert similarity._is_distinctive_format(r"^[A-Z]{2}\d{4}$") is False


class TestValueOverlapIsNotConceptIdentity:
    """Overlapping value sets identify a concept only for a CODED VOCABULARY.
       {OPEN, CLOSED, PENDING} is a controlled domain; {0,1,2,3} is just small
       integers. On the AWC glossary the old rule scored
       'Paid Bills <- Outstanding Bills' at 100% overlap / 0.85 strong — opposite
       states of a bill whose counts happen to share a range."""

    def _row(self, name, enums):
        return {"Term": name, "Enum_Values": ";".join(enums),
                "Source_Column": f"s.t.{name}"}

    def test_numeric_overlap_no_longer_claims_one_concept(self):
        from engine import similarity
        v, why = similarity.compare_evidence(self._row("paid", ["1", "2", "3"]),
                                             self._row("outstanding", ["1", "2", "3"]))
        assert v is None
        assert "plain numbers" in why

    def test_a_code_list_still_decides(self):
        from engine import similarity
        v, why = similarity.compare_evidence(self._row("a", ["OPEN", "CLOSED"]),
                                             self._row("b", ["OPEN", "CLOSED"]))
        assert v == "same" and "overlap" in why

    def test_disjoint_code_lists_still_say_different(self):
        from engine import similarity
        v, why = similarity.compare_evidence(self._row("a", ["OPEN", "CLOSED"]),
                                             self._row("b", ["CURRENT", "DEFAULT"]))
        assert v == "different" and "code lists" in why

    def test_a_single_value_is_too_thin_to_be_a_vocabulary(self):
        from engine import similarity
        assert similarity._is_coded_vocabulary({"ACTIVE"}) is False

    def test_decimals_and_counts_are_not_vocabularies(self):
        from engine import similarity
        assert similarity._is_coded_vocabulary({"1.5", "2.25"}) is False
        assert similarity._is_coded_vocabulary({"12", "45", "78"}) is False


def test_engine_ships_no_categories():
    """The engine must assert NO taxonomy of its own.

    It shipped 14 builtin keywords until 1.29 - "Billing & Rates", "Usage",
    "Records & Documents" - which was the water-utility scenario leaked into the
    engine: a credit union scanning `invoice_total` got a category nobody had
    chosen, and it read as a considered default rather than a leak. Categories
    come from the domain pack, which is grown from the company's own scan.
    Renaming them to neutral words would have kept the same flaw.
    """
    from engine import suggester
    assert suggester.CAT_KEYWORDS == [], \
        "a builtin category keyword has crept back into the engine"
    assert not hasattr(suggester, "BUILTIN_CAT_KEYWORDS")
    assert suggester.categorize_column("invoice_total") is None
    # Packless, the fallback is the PHYSICAL name - evidence, not invention.
    # A wall of "Uncategorized" left stewards guessing; a table's own name gives
    # them a group to RENAME once instead.
    assert suggester.categorize("billing_invoice") == "Billing Invoice"
    assert suggester.humanize_physical("monthly_usage") == "Monthly Usage"
    assert suggester.humanize_physical("gis/asset_inventory.csv") == "Gis"
    assert suggester.humanize_physical("inspection_report.docx") == "Inspection Report"
    assert suggester.humanize_physical("") == "Uncategorized"

    # The single documented exception: the engine creates document rows itself,
    # so it must name a category for them - and a pack can rename it.
    from engine import tagdict
    assert tagdict.document_category() == "Records & Documents"


def test_document_category_is_pack_overridable(fresh_dict, tmp_path, monkeypatch):
    """The one category name the engine still carries must not be fixed. A
       glossary that calls this bucket something else has to be able to say so,
       or the harvest files its rows under a name nobody chose."""
    import json
    from engine import tagdict
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"document_category": "Unstructured Content"}), encoding="utf-8")
    monkeypatch.setenv("GLOSSARY_DOMAIN_PACK", str(pack))
    assert tagdict.document_category() == "Unstructured Content"


def test_document_rows_keep_the_governed_tag(fresh_dict):
    """Removing the builtin category->tag seeds once cost the harvest its
       governed "document" tag - rows fell back to the slug "records-documents",
       which is not in the vocabulary."""
    from engine import suggester
    from engine import tagdict
    tags = suggester.suggest_tags(tagdict.document_category(), "LOW", "", "No", False, [],
                                  name="conservation_letter.pdf", term="Conservation Letter")
    assert "document" in tags
    assert "records-documents" not in tags


def test_the_generic_layer_carries_no_industry_vocabulary():
    """The dictionary's built-in seed is GOVERNANCE vocabulary, not somebody's
    industry.

    It shipped "Meter Reading" as a governed term, plus metering/usage/rate tags
    and a usage|consumption|meter rule - the water-utility scenario leaking into
    the engine, exactly as "Billing & Rates" did in CAT_KEYWORDS before 1.29. A
    credit union has no use for "Metering", and offering it as governed
    vocabulary implies somebody chose it.

    Anything domain-specific belongs in a domain pack, where extra_tags puts it
    straight into the allow-list.
    """
    from engine import tagdict

    banned = {"metering", "usage", "rate", "billing", "revenue", "asset"}
    assert not (banned & set(tagdict._SEED_TAGS)), \
        "industry tags back in the generic layer: {}".format(banned & set(tagdict._SEED_TAGS))

    terms = " ".join(tagdict._SEED_TERMS).lower()
    for word in ("meter", "tariff", "premise"):
        assert word not in terms, "industry term in the generic seed: " + word

    for pattern, tags in tagdict._SEED_RULES:
        leaked = banned & set(tags)
        assert not leaked, "rule {!r} assigns industry tags {}".format(pattern, leaked)

    # The regulatory vocabulary every estate needs must NOT have gone with it.
    for keep in ("pii", "personal-data", "maskable", "cde", "temporal", "compliance"):
        assert keep in tagdict._SEED_TAGS, "governance vocabulary was lost: " + keep


def test_no_industry_vocabulary_decides_critical_data_elements():
    """CDE_PATTERNS governs which columns are marked Critical Data Element.

    It carried meter id, lead level, contaminant, pH and turbidity - drinking
    water regulation applied to every estate, the third place the water utility
    had leaked into the engine after the category keywords and the tag
    dictionary. A bank's CDEs are not decided by a water quality rule.

    What stays is regulatory vocabulary that crosses industries: national
    identifiers, tax ids, licences, balances, amounts due, compliance and
    violations.
    """
    from engine import suggester

    pattern = suggester.CDE_PATTERNS.pattern.lower()
    for word in ("meter", "turbidity", "contaminant", "ph.?level", "lead.?"):
        assert word not in pattern, "industry term still decides CDE: " + word

    for name in ("chlorine_residual_ppm", "turbidity_ntu", "meter_id"):
        assert not suggester.CDE_PATTERNS.search(name), \
            "{} should not be a CDE by name alone".format(name)

    for name in ("account_number", "ssn", "tax_id", "amount_due", "violation_code"):
        assert suggester.CDE_PATTERNS.search(name), \
            "{} is cross-industry regulatory vocabulary and must still match".format(name)
