"""The shared row -> detection-seed ladder (1.38.24).

The drafter and the Registry bridge used to decide "what counts as evidence"
separately, and drifted: a steward's Auto flip and a profiler-recognised kind
minted a drafted rule but never reached the Registry — the contract the Policy
Generator authors from. A walk that drafted 88 patterns handed over a Registry
worth 18, and the only way to notice was to count both by hand.

These tests pin the two halves together: same rows in, same seeds out.
"""
from conftest import make_row as _row


def _concepts(rows, name="Ladder G"):
    from registry.bridge import build_registry
    return {c["term_name"]: c for c in build_registry(rows, name)["concepts"]}


class TestNameAnchoredSeedsReachTheRegistry:
    """The steward's flip is a DECISION, and the Registry is where decisions
    travel. Before 1.38.24 it died in the drafter."""

    def test_flipped_measure_mints_a_name_anchored_pattern(self):
        r = _row("pH Level", "aw.samples.ph_level", Value_Range="6.5-8.5",
                 Suggested_Reason="Profiled: numeric")
        c = _concepts([r])["pH Level"]
        assert [d["source"] for d in c["detect"]] == ["name-anchored"]
        seed = c["detect"][0]
        assert seed["type"] == "pattern"
        assert seed["identity"] == "column_name", \
            "the authoring side needs to know the NAME carries identity here"
        assert seed["regex"] == r"^-?[0-9]+(\.[0-9]+)?$"
        assert c["detection_intent"] == "seeded"

    def test_flipped_date_mints_the_date_shape_despite_its_signature(self):
        # the sig-gate bug in reverse: a profiled date carries a signature, and
        # gating the mint behind "no signature" sent flipped dates to the skips
        r = _row("Service Start Date", "aw.customers.service_start_date",
                 Value_Kind="date", Value_Signature="dddd-dd-dd")
        seed = _concepts([r])["Service Start Date"]["detect"][0]
        assert seed["source"] == "name-anchored"
        assert seed["signature"] == "dddd-dd-dd", "informative, inert — never dropped"
        assert seed["regex"].startswith(r"^\d{4}-\d{2}-\d{2}")

    def test_mapping_only_is_never_flipped_for_the_steward(self):
        """A declared mapping-only row is the OPPOSITE of a flip: it must not
        pick up a name-anchored seed just because it has a range."""
        r = _row("Meter Reading", "aw.meters.reading", Value_Range="0-99999",
                 Detection_Intent="mapping_only")
        c = _concepts([r])["Meter Reading"]
        assert c["detect"] == []
        assert c["detection_intent"] == "mapping_only"

    def test_no_column_name_no_anchor(self):
        r = _row("Odd Measure", "aw", Value_Range="1-10")
        c = _concepts([r])["Odd Measure"]
        assert c["detect"] == [], "no physical column -> nothing to anchor to"


class TestRecognisedKindsReachTheRegistry:
    def test_recognised_kind_mints_the_profilers_own_shape(self):
        r = _row("Customer Email", "aw.customers.email", Value_Kind="email")
        seed = _concepts([r])["Customer Email"]["detect"][0]
        assert seed["source"] == "recognised"
        assert "@" in seed["regex"]


class TestDictionaryFloor:
    def test_single_value_reference_list_is_not_evidence(self):
        """The authoring side needs 2+ values, so a one-value list only
        pretended to be a seed — it produced a concept marked 'seeded' that
        could never yield a method."""
        c = _concepts([_row("Region", "aw.customers.region", Enum_Values="West")])["Region"]
        assert c["detect"] == []
        assert "detection_intent" not in c

    def test_two_values_still_seed_a_dictionary(self):
        c = _concepts([_row("Region", "aw.customers.region",
                            Enum_Values="West;East")])["Region"]
        assert [d["type"] for d in c["detect"]] == ["dictionary"]
        assert c["detect"][0]["values"] == ["West", "East"]


class TestDrafterAndRegistryAgree:
    """The anti-drift test: whatever the drafter mints, the Registry carries.
    This is the check that would have caught 88-vs-18 the day it appeared."""

    ROWS = [
        _row("Account Number", "aw.customers.account_number",
             Value_Pattern=r"^[A-Z]{3}-[0-9]{6}$", Value_Signature="AAA-nnnnnn"),
        _row("pH Level", "aw.samples.ph_level", Value_Range="6.5-8.5"),
        _row("Lead (ppb)", "aw.samples.lead_ppb", Value_Range="0-15"),
        _row("Service Start Date", "aw.customers.service_start_date", Value_Kind="date"),
        _row("Customer Email", "aw.customers.email", Value_Kind="email"),
        _row("Account Status", "aw.customers.account_status",
             Enum_Values="ACTIVE;SUSPENDED;CLOSED"),
        _row("Notes", "aw.customers.notes", Suggested_Reason="Profiled: free text",
             Suggested_Quality=0.4),
        _row("Meter Reading", "aw.meters.reading", Value_Range="0-99999",
             Detection_Intent="mapping_only"),
    ]

    def test_every_drafted_rule_has_a_registry_seed(self):
        from engine import policy_draft
        d = policy_draft.draft_from_rows(self.ROWS, glossary_name="Ladder G")
        concepts = _concepts(self.ROWS)
        drafted = {p["term"] for p in d["patterns"]} | {x["term"] for x in d["dictionaries"]}
        for term in drafted:
            assert concepts[term]["detect"], \
                f"{term} was drafted a rule the Registry cannot express"

    def test_counts_match_kind_for_kind(self):
        from engine import policy_draft
        d = policy_draft.draft_from_rows(self.ROWS, glossary_name="Ladder G")
        seeds = [s for c in _concepts(self.ROWS).values()
                 for s in c["detect"] if c.get("detection_intent") != "mapping_only"]
        assert len(d["patterns"]) == len([s for s in seeds if s["type"] == "pattern"])
        assert len(d["dictionaries"]) == len([s for s in seeds if s["type"] == "dictionary"])

    def test_seed_kinds_match(self):
        from engine import policy_draft
        d = policy_draft.draft_from_rows(self.ROWS, glossary_name="Ladder G")
        by_term = {c["term_name"]: c for c in
                   [v for v in _concepts(self.ROWS).values()]}
        for p in d["patterns"]:
            assert p["seed"] == by_term[p["term"]]["detect"][0]["source"]
