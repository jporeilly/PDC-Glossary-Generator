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


class TestBooleanSourcesAreNeverSeeded:
    """A value-shape rule on a bit column is inert (1.38.34).

    PDC matches a pattern's regex and a dictionary's vocabulary against a
    column's VALUES. A bit column has none to match: proven on the live estate
    2026-08-20, where opted_out_marketing and bacteria_present (both BIT, both
    holding 0/1) tagged nothing under a name-anchored regex AND under a
    hand-built {0,1} dictionary, while every NUMERIC sibling tagged correctly.
    Minting a rule for them produces a method that imports, passes drift, and
    never fires — so the ladder refuses, and says why.
    """

    def _seed(self, **kw):
        from engine.policy_seed import seeds_for_row
        row = _row("Opted Out Marketing", "aw.customers.opted_out_marketing", **kw)
        return seeds_for_row(row, {})

    def test_a_bit_column_is_refused_with_a_reason(self):
        seeds, skip, _ = self._seed(Value_Range="0-1",
                                    Source_Types={"aw.customers.opted_out_marketing": "BIT"})
        assert seeds == []
        assert "boolean column" in skip and "term" in skip

    def test_a_numeric_sibling_still_mints(self):
        seeds, skip, _ = self._seed(Value_Range="6.5-8.5",
                                    Source_Types={"aw.customers.opted_out_marketing": "NUMERIC"})
        assert skip is None and seeds and seeds[0]["source"] == "name-anchored"

    def test_no_type_information_changes_nothing(self):
        """Registries written before 1.38.34 carry no source_types; they must
        behave exactly as they did."""
        seeds, skip, _ = self._seed(Value_Range="0-1")
        assert skip is None and seeds and seeds[0]["source"] == "name-anchored"


class TestBooleanNatureIsMappingOnlyBeforeAnyoneCanFlipIt:
    """The default, not just the guard (1.38.34).

    The ladder refuses to seed a bit column, but a steward could still flip the
    row to Auto and watch nothing happen. The nature classifier now recognises
    the type PDC actually reports for a flag — BIT — so such a row arrives
    mapping-only and the grid refuses the flip.
    """

    def _intent(self, typ):
        from engine.sug_suggest import _detection_intent
        return _detection_intent({"type": typ}, {}, "")

    def test_bit_is_mapping_only(self):
        assert self._intent("BIT") == "mapping_only"

    def test_the_other_spellings_too(self):
        for t in ("bool", "BOOLEAN", "tinyint(1)", "TINYINT( 1 )"):
            assert self._intent(t) == "mapping_only", t

    def test_a_shaped_column_is_still_auto(self):
        """Only the boolean rule is new: a column with a profiled shape keeps
        its Auto nature. (A bare NUMERIC with no shape is mapping-only by an
        older, deliberate rule — a free measure has nothing to identify it.)"""
        from engine.sug_suggest import _detection_intent
        assert _detection_intent({"type": "VARCHAR"},
                                 {"pattern": r"^[A-Z]{3}-\d{6}$"}, "") != "mapping_only"


class TestTableRatingCarriesItsRater:
    """A rating PDC can read (1.38.34).

    Apply rolled a table rating up as {"value": 4} with no `users` map. PDC
    computes the displayed rating from that map, so the entity page showed 0
    stars and raised "There was an error getting the rating information" on
    every table Apply rated — 18 of them, while the receipt reported success.
    """

    def test_value_and_raters_travel_together(self):
        from pdc_client.apply import rating_payload
        assert rating_payload(4, {"steward-1": 4}) == {"value": 4, "users": {"steward-1": 4}}

    def test_every_rater_carries_the_rolled_up_value(self):
        from pdc_client.apply import rating_payload
        out = rating_payload(3, {"a": 5, "b": 1})
        assert out["users"] == {"a": 3, "b": 3}, "the table's value, not each column's"

    def test_no_rater_means_no_rating(self):
        """Better no rating than one attributed to nobody — that is the state
        that produced the error."""
        from pdc_client.apply import rating_payload
        assert rating_payload(4, None) is None
        assert rating_payload(4, {}) is None


class TestApplyCountsWhatItActuallyWrote:
    """`tables_rated` used to count PATCHes that returned 200 (1.38.34).

    All 18 of them "succeeded" while writing a rating PDC could not read. The
    report now separates the two facts: how many tables were patched, and how
    many carried a rating with its raters — the only kind that survives a read.
    """

    def test_a_rating_without_raters_is_not_counted_as_rated(self):
        from pdc_client.apply import rating_payload
        rows = [
            {"status": "applied", "body": {"attributes": {"features": {
                "rating": rating_payload(4, {"steward-1": 4})}}}},
            {"status": "applied", "body": {"attributes": {"features": {}}}},
        ]
        patched = sum(1 for t in rows if t["status"] in ("applied", "planned"))
        rated = sum(1 for t in rows
                    if t["status"] in ("applied", "planned")
                    and ((t.get("body") or {}).get("attributes", {})
                         .get("features", {}).get("rating") or {}).get("users"))
        assert patched == 2 and rated == 1


class TestAmbiguousShapesBecomeNameAnchored:
    """A regex shared by several concepts identifies none of them (1.38.34).

    On the live estate one induced shape — ^[A-Z]{2}[0-9]{4}$ — was the profiled
    evidence for EIGHT concepts. Authored with the profiled blend the shape alone
    clears the gate, and a free-text `notes` column came back bound to all eight,
    tagged pii/privacy/location. Marking the seed name-anchored makes the column
    name carry identity, so name AND shape must agree.
    """

    ROWS = [
        _row("Source Type", "aw.systems.source_type", Value_Pattern=r"^[A-Z]{2}[0-9]{4}$"),
        _row("Water System Type", "aw.systems.system_type", Value_Pattern=r"^[A-Z]{2}[0-9]{4}$"),
        _row("Account Number", "aw.customers.account_number", Value_Pattern=r"^ACC-[0-9]{6}$"),
    ]

    def test_a_shared_shape_is_marked_name_anchored(self):
        cs = _concepts(self.ROWS)
        for t in ("Source Type", "Water System Type"):
            seed = cs[t]["detect"][0]
            assert seed["identity"] == "column_name", t
            assert seed["shared_with"], "say which other concepts claim this shape"

    def test_a_unique_shape_is_left_alone(self):
        seed = _concepts(self.ROWS)["Account Number"]["detect"][0]
        assert "identity" not in seed and seed["source"] == "profiled"
