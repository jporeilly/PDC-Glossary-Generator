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

    def test_generic_tags_retire_with_tombstones_except_core(self, fresh_dict):
        """"cant retire generic tags" — now they can, durably, EXCEPT the
        load-bearing core six the engine stands on (those refuse and the UI
        says why). Retiring a tag also strips it from every rule that emits
        it — a rule left with no tags is dropped — so the rules-reference-
        governed-tags invariant holds without special-casing the layer."""
        tagdict = fresh_dict
        d = tagdict.load()
        assert (d["tags"].get("temporal") or {}).get("layer") == "generic"
        d.setdefault("rules", []).append(
            {"pattern": "_ts$", "tags": ["temporal"], "layer": "company"})
        assert tagdict.review("tag", ["temporal"], "reject") == 1
        d2 = tagdict.load()
        assert "temporal" not in d2.get("tags", {})
        assert "temporal" in (d2.get("retired") or {}).get("tags", [])
        assert all("temporal" not in (r.get("tags") or []) for r in d2.get("rules", [])), \
            "rules that emitted the retired tag lose it"
        assert not any(r.get("pattern") == "_ts$" for r in d2.get("rules", [])), \
            "a rule with no tags left is dropped, not left inert"
        # the tombstone survives BOTH the load-time re-inject and a Reseed
        tagdict.reset(preserve_approved=True)
        assert "temporal" not in tagdict.load().get("tags", {})
        assert "temporal" in (tagdict.load().get("retired") or {}).get("tags", [])
        # the load-bearing core refuses — nothing changes, nothing tombstones
        assert tagdict.review("tag", ["pii"], "reject") == 0
        d3 = tagdict.load()
        assert (d3["tags"].get("pii") or {}).get("layer") == "generic"
        assert "pii" not in (d3.get("retired") or {}).get("tags", [])

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

    def test_mid_size_vocabularies_profile_as_enums(self):
        """The reseeded estate's 15 service cities sat three past the old
           12-distinct ceiling and profiled as shapeless free text, so the
           drafter skipped every city column with "values induce no shape"
           (field: "could this still be a lack of values, so it doesn't
           trigger a pattern?" — the opposite: too many). Real reference
           vocabularies run to dozens; the ceiling (48) is a backstop, and
           the n >= 2*distinct repetition floor stays the working gate."""
        cities = ["City%02d" % (i % 15) for i in range(100)]  # 15 distinct, repeated
        prof = suggester._profile_values("billing_city", cities, len(cities))
        assert prof.get("kind") == "enum", prof
        assert len(prof["enum"]) == 15
        # the backstop: 50 distinct across 100 rows passes the repetition
        # floor (uniq exactly .5) but sits past the ceiling — not a dictionary
        wide = ["V%02d" % (i % 50) for i in range(100)]
        prof2 = suggester._profile_values("wide_code", wide, len(wide))
        assert prof2.get("kind") != "enum", prof2

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

    def test_profiled_survives_the_ai_pass_rewriting_the_reason(self):
        """The AI pass rewrites Suggested_Reason with the model's rationale,
           which killed the prose marker — enriched profiled rows were told
           to "re-scan with profiling on" (field-caught on the .65 walk).
           The profile's own data on the row is the durable witness."""
        rows = [_row("Peak Usage", "awc.usage.peak_usage",
                     Suggested_Reason="LLM: seasonal demand indicator",
                     Source_Quality_Dims={"awc.usage.peak_usage": {"c": 1.0}})]
        art = policy_draft.draft_from_rows(rows, prefix="AWC")
        why = {s["term"]: s["why"] for s in art["skipped"]}
        assert why["Peak Usage"].startswith("profiled, but"), why

    def test_recognised_kinds_mint_custom_patterns(self):
        """Clarified in the field: custom-only means WE ship every policy
           (PDC's inbuilt set stays unused) — it never meant generic concepts
           go undetected. A column the profiler recognised as email/phone/zip
           in THIS estate's values mints a CUSTOM Data Pattern carrying the
           profiler's own shape ("so we do need these policies to be
           built")."""
        from engine.suggester import RX_EMAIL
        rows = [_row("Customer Email", "awc.customers.email",
                     Suggested_Reason="LLM: contact detail",
                     Value_Kind="email", Suggested_Tags="pii")]
        art = policy_draft.draft_from_rows(rows, prefix="AWC",
                                           governed_tags=["pii"])
        pats = {p["term"]: p for p in art["patterns"]}
        assert "Customer Email" in pats, art["skipped"]
        assert pats["Customer Email"]["seed"] == "recognised"
        blob = json.dumps(pats["Customer Email"]["rule"]).replace("\\\\", "\\")
        assert RX_EMAIL.pattern in blob, \
            "the rule carries the profiler's own shape — one definition"

    def test_date_kind_never_mints_bare_date_pattern(self):
        """A BARE date Data Pattern would match every date column in the
           estate. The nature default keeps dates mapping-only; a date row
           arriving Auto is the steward's explicit flip and mints the
           name-anchored form — identity on the column name, the date shape
           as sanity only — never a bare date shape."""
        rows = [_row("Effective", "awc.rates.effective",
                     Suggested_Reason="LLM: when the rate starts",
                     Value_Kind="date", Detection_Intent="mapping_only"),
                _row("Payment Date", "awc.payments.payment_date",
                     Value_Kind="date")]
        art = policy_draft.draft_from_rows(rows, prefix="AWC")
        assert [m["term"] for m in art["mapping_only"]] == ["Effective"]
        pats = {p["term"]: p for p in art["patterns"]}
        assert set(pats) == {"Payment Date"}
        rule = pats["Payment Date"]["rule"][0]
        assert rule["columnNameRegex"], "the mint must ride the name anchor"
        assert rule["columnNameWeight"] == 0.5

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


class TestRecognisedKindDQ:
    def test_email_column_gets_a_format_expectation(self):
        """Full-coverage commission: recognised kinds ship on BOTH sides —
           a custom Data Pattern for detection and a DQ format expectation
           for conformance, each carrying the profiler's one shape."""
        from engine.suggester import RX_EMAIL
        rows = [_row("Customer Email", "awc.customers.email",
                     Value_Kind="email")]
        dq = policy_draft.dq_rules_from_rows(rows, prefix="AWC")
        assert dq, "a recognised kind must produce a DQ artifact"
        blob = json.dumps(dq[0]["rule"]).replace("\\\\", "\\")
        assert RX_EMAIL.pattern in blob and '"recognised"' in json.dumps(dq[0]["rule"])


class TestLabelSuggestions:
    """Labels are derived from proven evidence and never invented — and PDC
       caps a label at a handful of values, so a key that explodes is not a
       label at all."""

    def _rows(self):
        return [
            _row("Customer Email", "awc.customers.email", Category="Customer Management",
                 Sensitivity="HIGH", PII_Category="CONTACT_INFO",
                 Critical_Data_Element="Yes"),
            _row("Meter Size", "awc.meters.meter_size", Category="Asset Management",
                 Sensitivity="LOW", PII_Category="", Critical_Data_Element="No"),
        ]

    def test_derived_keys_read_classification(self):
        """PII Type uses the steward's own three-tier taxonomy (modelled live
           in PDC's Create Custom Property form): CONTACT_INFO identifies a
           person on its own -> Confidential."""
        from engine import labels
        got = labels.suggest_labels(self._rows())
        keys = {k["key"]: k for k in got["keys"]}
        assert set(keys) >= {"PII Type", "access-tier", "criticality", "domain"}
        pii = {v["value"]: v["terms"] for v in keys["PII Type"]["values"]}
        assert pii["Confidential"] == ["Customer Email"], pii
        assert keys["PII Type"]["descriptions"]["Restricted"].startswith("serious harm")
        tiers = {v["value"] for v in keys["access-tier"]["values"]}
        assert tiers == {"tier-1", "tier-3"}

    def test_retention_is_never_invented(self):
        from engine import labels
        got = labels.suggest_labels(self._rows())
        assert not any(k["key"] == "retention" for k in got["keys"])
        assert any("domain pack" in n for n in got["notes"]), got["notes"]

    def test_retention_comes_from_the_pack(self):
        from engine import labels
        rows = [_row("Report Date", "bucket.compliance/epa_2026.pdf.date",
                     Category="Water Quality", Sensitivity="LOW",
                     PII_Category="", Critical_Data_Element="No")]
        pack = {"labels": {"retention": {"compliance": "7y", "correspondence": "3y"}}}
        got = labels.suggest_labels(rows, pack=pack)
        ret = next(k for k in got["keys"] if k["key"] == "retention")
        assert ret["source"] == "pack"
        assert ret["values"][0]["value"] == "7y"

    def test_a_key_with_too_many_values_is_refused(self):
        from engine import labels
        rows = [_row(f"T{i}", f"awc.t.c{i}", Category=f"Category {i}",
                     Sensitivity="LOW", PII_Category="", Critical_Data_Element="No")
                for i in range(9)]
        got = labels.suggest_labels(rows)
        assert not any(k["key"] == "domain" for k in got["keys"])
        assert any("too many for a PDC label" in n for n in got["notes"])


class TestNumericRangeDQ:
    def test_profiled_range_becomes_a_dq_check(self):
        """A numeric column IS profiled - min/max observed become the DQ
           expectation's baseline ("we know that the data has been ingested
           and profiled"). Rows without a range mint no range check."""
        from engine import policy_draft
        rows = [_row("Capacity", "awc.water_systems.capacity",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Range="201..5095"),
                _row("Notes Text", "awc.water_systems.notes_text",
                     Critical_Data_Element="No", PII_Category="")]
        arts = policy_draft.dq_rules_from_rows(rows, "AWC Glossary")
        cap = next(a for a in arts if a["term"] == "Capacity")
        checks = [c for e in cap["rule"]["expectations"] for c in e["checks"]]
        rng = next(c for c in checks if c["check"] == "range")
        assert rng["min"] == 201 and rng["max"] == 5095
        assert rng["source"] == "profiled baseline"
        notes = [a for a in arts if a["term"] == "Notes Text"]
        if notes:
            nchecks = [c for e in notes[0]["rule"]["expectations"] for c in e["checks"]]
            assert not any(c["check"] == "range" for c in nchecks)


class TestMappingOnlySkipsNothing:
    def test_mapping_only_terms_leave_the_skip_list(self):
        """mapping-only is a DECLARATION, not a failure: the skip list names
           missing evidence, and an intentional mapping term is not missing
           anything (found by the end-to-end run - dates/booleans/amounts
           cluttered the skips their intent flag existed to silence)."""
        from engine import policy_draft
        rows = [_row("Service Start Date", "awc.customers.service_start_date",
                     Critical_Data_Element="No", PII_Category="",
                     Detection_Intent="mapping_only"),
                _row("Notes Text", "awc.customers.notes_text",
                     Critical_Data_Element="No", PII_Category="")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        assert [m["term"] for m in d["mapping_only"]] == ["Service Start Date"]
        skip_terms = [s["term"] for s in d["skipped"]]
        assert "Service Start Date" not in skip_terms
        assert "Notes Text" in skip_terms, "evidence-less Auto rows still report honestly"


class TestNameAnchoredMeasureRules:
    """A steward-flipped Auto row with a date kind or a numeric range must be
    honoured with a name-anchored rule, not dumped in the skips ("Im also sure
    some of these mappings can be auto ... pH level can only go to 14"). The
    content shape is sanity only - identity rides the column name, the range
    rides the DQ rule - and the weights must rebalance to 0.5/0/0.5 because a
    rule with no contentPatterns can never clear 0.7 under the stock blend."""

    def test_flipped_date_mints_name_anchored_pattern(self):
        from engine import policy_draft
        import re
        rows = [_row("Payment Date", "awc.payments.payment_date",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Kind="date", Detection_Intent="")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        assert [p["term"] for p in d["patterns"]] == ["Payment Date"]
        p = d["patterns"][0]
        assert p["seed"] == "name-anchored"
        rule = p["rule"][0]
        assert rule["columnNameWeight"] == 0.5
        assert rule["contentPatternWeight"] == 0.0
        assert rule["contentRegexWeight"] == 0.5
        assert rule["columnNameRegex"], "no name anchor would over-match every date column"
        crx = rule["contentRegex"][0]["regex"]
        assert re.match(crx, "2026-05-14") and re.match(crx, "5/14/2026")
        assert not re.match(crx, "not a date")
        import json
        conf = json.dumps(rule["confidenceScore"])
        assert "patternScore" not in conf, "zero-weight term must leave the blend"
        # regexScore is not a PDC condition variable, so the name-AND-shape
        # conjunction lives in the blend; the condition adds PDC's own
        # template guard - a constant column can never satisfy a sanity shape
        cond = json.dumps(rule["condition"])
        assert "columnCardinality" in cond, cond
        assert "Payment Date" not in [s["term"] for s in d["skipped"]]

    def test_dictionary_condition_matches_pdc_template(self):
        """The shipped Pentaho Personal Data Identifier template wraps the
        (confidence OR name-hint) branch with a cardinality guard - our
        dictionaries carry the same shape, guarded at > 1 to match the
        enum floor instead of the template's > 5 (which would veto a
        legitimate 3-value LOW/MEDIUM/HIGH vocabulary)."""
        from engine import policy_draft
        import json
        rows = [_row("Risk Rating", "cscu_core.kyc.risk_cd",
                     Critical_Data_Element="No", PII_Category="",
                     Enum_Values="LOW;MEDIUM;HIGH")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        rule = d["dictionaries"][0]["rule"][0]
        cond = json.dumps(rule["condition"])
        assert "columnCardinality" in cond, cond
        assert '"or"' in cond and '"and"' in cond, cond

    def test_flipped_measure_mints_numeric_sanity_rule(self):
        from engine import policy_draft
        import re
        rows = [_row("pH Level", "awc.water_quality.ph_level",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Range="6.1..8.4", Detection_Intent="")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        assert [p["term"] for p in d["patterns"]] == ["pH Level"]
        rule = d["patterns"][0]["rule"][0]
        crx = rule["contentRegex"][0]["regex"]
        assert re.match(crx, "7.2") and re.match(crx, "-3")
        assert not re.match(crx, "acidic"), "the RANGE lives in DQ; the rule only asserts numeric shape"

    def test_signature_does_not_gate_the_flip(self):
        """A profiled date CARRIES a shape signature (dddd-dd-dd), and the
        mint used to hide behind 'no signature' — a flipped Payment Date
        landed in 'no stable shape' on the live mass-flip walk. The
        name-anchor check now comes first; the signature rides the rule's
        contentPatterns at weight 0, informative and inert."""
        from engine import policy_draft
        rows = [_row("Payment Date", "awc.payments.payment_date",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Kind="date", Value_Signature="dddd-dd-dd",
                     Detection_Intent="")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        assert [p["term"] for p in d["patterns"]] == ["Payment Date"], d["skipped"]
        assert d["patterns"][0]["seed"] == "name-anchored"
        rule = d["patterns"][0]["rule"][0]
        assert rule["contentPatterns"] == [{"pattern": "dddd-dd-dd"}]
        assert rule["contentPatternWeight"] == 0.0

    def test_unit_named_measures_default_to_auto_at_suggest_time(self):
        """"I thought this would be done automatically" — a bounded measure
        whose name carries its unit (class knowledge) now arrives AUTO from
        the nature classifier; generic numerics keep the safe mapping-only
        default."""
        from engine import sug_suggest
        rng = {"min": 6.1, "max": 8.4}
        assert sug_suggest._detection_intent(
            {"name": "ph_level", "type": "numeric"}, dict(rng), "") == ""
        assert sug_suggest._detection_intent(
            {"name": "lead_ppb", "type": "numeric"}, dict(rng), "") == ""
        assert sug_suggest._detection_intent(
            {"name": "amount_paid", "type": "numeric"}, dict(rng), "") == "mapping_only"
        # unit name WITHOUT range evidence stays mapping-only — the shape
        # half of the conjunction must exist before Auto means anything
        assert sug_suggest._detection_intent(
            {"name": "ph_level", "type": "numeric"}, {}, "") == "mapping_only"

    def test_mapping_only_marks_safe_flip_candidates(self):
        """"we're flipping to auto when we could have done this before" — the
        draft now pre-sorts the queue: a bounded measure whose name carries
        its unit (class knowledge — ppm is ppm in any estate) is starred as
        a recommended flip; generic amounts and dates stay unmarked. The
        flip itself remains the steward's click."""
        from engine import policy_draft
        rows = [_row("pH Level", "awc.water_quality.ph_level",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Range="6.1..8.4", Detection_Intent="mapping_only"),
                _row("Lead (ppb)", "awc.water_quality.lead_ppb",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Range="0..12", Detection_Intent="mapping_only"),
                _row("Amount Paid", "awc.billing.amount_paid",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Range="10..900", Detection_Intent="mapping_only"),
                _row("Payment Date", "awc.payments.payment_date",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Kind="date", Detection_Intent="mapping_only")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        flags = {m["term"]: m["auto_candidate"] for m in d["mapping_only"]}
        assert flags == {"pH Level": True, "Lead (ppb)": True,
                         "Amount Paid": False, "Payment Date": False}, flags

    def test_default_natures_still_divert_and_skip(self):
        """The mint fires ONLY on the explicit flip: mapping-only rows divert
        before the ladder, and Auto rows without range/date evidence skip."""
        from engine import policy_draft
        rows = [_row("Collected Date", "awc.samples.collected_date",
                     Critical_Data_Element="No", PII_Category="",
                     Value_Kind="date", Detection_Intent="mapping_only"),
                _row("Recommended Action", "awc.alerts.recommended_action",
                     Critical_Data_Element="No", PII_Category="",
                     Detection_Intent="")]
        d = policy_draft.draft_from_rows(rows, glossary_name="X")
        assert d["patterns"] == []
        assert [m["term"] for m in d["mapping_only"]] == ["Collected Date"]
        assert "Recommended Action" in [s["term"] for s in d["skipped"]]


class TestSingularizeKeepsRealWords:
    """A table term's name reaches PDC and is stored in the domain pack, so a
    mangled singular is not cosmetic. Field-caught 2026-08-21:
    `system_water_quality_status` shipped "System Water Quality Statu Record"
    into a customer-facing glossary, and the bad name was baked into the pack,
    where the lookup then returned it faithfully.
    """
    def test_singular_nouns_ending_in_s_survive(self):
        from engine.sug_suggest import _singularize
        for w in ("status", "census", "bonus", "radius", "analysis", "basis",
                  "axis", "diagnosis", "series", "species", "news", "alias",
                  "address", "system_water_quality_status"):
            assert _singularize(w) == w, f"{w!r} was mangled to {_singularize(w)!r}"

    def test_real_plurals_still_singularize(self):
        from engine.sug_suggest import _singularize
        cases = {"customers": "customer", "water_systems": "water_system",
                 "tiered_rates": "tiered_rate", "account_alerts": "account_alert",
                 "statuses": "status", "addresses": "address",
                 "companies": "company", "policies": "policy"}
        for plural, want in cases.items():
            assert _singularize(plural) == want, \
                f"{plural!r} -> {_singularize(plural)!r}, expected {want!r}"

    def test_the_table_term_reads_as_english(self):
        from engine.sug_suggest import table_term_name
        assert table_term_name("system_water_quality_status") == \
            "System Water Quality Status Record"
        assert table_term_name("customers") == "Customer Record"


class TestTypelessNumericsAreStillNumeric:
    """A CSV or JSON column arrives with NO SQL type, so a type-driven test
    cannot reach it. Field-caught 2026-08-21: every numeric measure harvested
    from a document escaped the free-numeric guard and arrived Auto, so
    latitude, longitude, install_year, length_feet, diameter_inches and
    condition_rating each minted a method backed by "is a number" — nine
    concepts on one shape, which identifies none of them.

    The profiled min/max IS evidence the column is numeric, whatever the
    source could say about its type.
    """
    def _intent(self, name, prof, typ=""):
        from engine.sug_suggest import _detection_intent
        return _detection_intent({"name": name, "type": typ}, prof, "")

    def test_a_typeless_column_with_a_numeric_range_is_a_free_measure(self):
        for name, lo, hi in (("latitude", 31.43, 35.19), ("install_year", 1958, 2023),
                             ("condition_rating", 1, 5), ("length_feet", 201, 5095)):
            got = self._intent(name, {"min": lo, "max": hi})
            assert got == "mapping_only", \
                f"{name} came back {got!r} — a bare number identifies every number"

    def test_a_typeless_column_with_no_range_is_untouched(self):
        """No type AND no range is not evidence of anything - don't invent it."""
        assert self._intent("some_note", {}) != "mapping_only"

    def test_a_unit_named_measure_still_arrives_auto(self):
        """The deliberate exception: a bounded measure whose NAME carries its
        unit mints a name-anchored rule without a steward click."""
        assert self._intent("pressure_psi", {"min": 59.4, "max": 66.9}) == ""

    def test_typed_numerics_are_unaffected(self):
        assert self._intent("population_served", {"min": 1, "max": 9}, "integer") == "mapping_only"


class TestUnitNamedMeasures:
    """Which measures earn the Auto default, and why inches/feet do NOT.

    The doctrine: a unit in the column NAME says the column measures a bounded
    physical property, so a name-anchored rule is an honest claim. Extending
    that to diameter_inches and length_feet was weighed on 2026-08-22 and
    REJECTED, for two reasons that only became visible after the AWC walk:

      1. It contradicts the free-numeric guard directly — length_feet is a
         bounded numeric measure with no discriminating value shape, which is
         the definition of mapping-only. See TestTypelessNumericsAreStillNumeric.
      2. A name-anchored numeric rule is a column-name rule wearing a pattern's
         clothes, and the 2026-08-21 identification run showed those patterns
         cannot score above their name hint anyway (see docs/SPEC-BACKLOG).
         Widening the set adds methods that cannot fire.

    Revisit when the pattern-scoring investigation lands, not before.
    """
    def test_the_recognised_units_are_chemistry_and_pressure(self):
        from engine.sug_shared import UNIT_NAME
        for n in ("pressure_psi", "flow_gpm", "ph_level", "lead_ppb",
                  "turbidity_ntu", "reservoir_level_pct"):
            assert UNIT_NAME.search(n), f"{n} should read as a unit-named measure"

    def test_dimension_and_consumption_units_are_deliberately_excluded(self):
        from engine.sug_shared import UNIT_NAME
        for n in ("diameter_inches", "length_feet", "usage_gallons",
                  "usage_tier_1_gallons", "latitude", "install_year",
                  "condition_rating", "population_served"):
            assert not UNIT_NAME.search(n),                 f"{n} must not default to Auto — see this class's docstring"

    def test_a_unit_name_alone_is_not_enough(self):
        """Auto needs the unit name AND a profiled range. A known-numeric
        column carrying the unit but no measured range stays mapping-only:
        without a range there is nothing to say the measure is bounded."""
        from engine.sug_suggest import _detection_intent
        assert _detection_intent({"name": "pressure_psi", "type": "numeric"},
                                 {"min": 59.4, "max": 66.9}, "") == ""
        assert _detection_intent({"name": "pressure_psi", "type": "numeric"},
                                 {}, "") == "mapping_only"

    def test_a_column_we_cannot_show_is_numeric_is_left_alone(self):
        """No type and no range is not evidence of anything. The classifier
        declines to call it a free measure rather than guessing — the guard
        added on 2026-08-21 believes a RANGE when the type is missing, not the
        absence of one."""
        from engine.sug_suggest import _detection_intent
        assert _detection_intent({"name": "pressure_psi", "type": ""}, {}, "") == ""
