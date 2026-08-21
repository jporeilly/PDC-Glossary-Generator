"""The one-way Review -> Dictionary flow: accepted grid improvements refresh
the dictionary's PENDING entries on glossary save; governed entries never
auto-change."""
from conftest import make_row


def _pending_meta(tagdict, name):
    return tagdict.load()["terms"].get(name)


class TestRefreshPending:
    def test_definition_and_category_flow_forward(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Alert Type", "public.account_alerts.alert_type",
                                  Definition="Alert Type associated with a account alert record.")])
        n = tagdict.refresh_pending([make_row(
            "Alert Type", "public.account_alerts.alert_type",
            Definition="Classifies an account alert (leak, overdue, quality).",
            Category="Governance")])
        assert n == 1
        m = _pending_meta(tagdict, "Alert Type")
        assert m["definition"].startswith("Classifies an account alert")
        assert m["category"] == "Governance"
        assert m["status"] == "pending"          # still the steward's call

    def test_rename_keeps_scan_name_as_alias(self, fresh_dict):
        tagdict = fresh_dict
        # the scan misread ph_level as "Phone Level"
        tagdict.accrete([make_row("Phone Level", "public.water_quality_reports.ph_level",
                                  Definition="Phone Level associated with a water quality report record.")])
        n = tagdict.refresh_pending([make_row(
            "pH Level", "public.water_quality_reports.ph_level",
            Definition="Acidity/alkalinity of the water on the 0-14 pH scale.")])
        assert n == 1
        assert _pending_meta(tagdict, "Phone Level") is None
        m = _pending_meta(tagdict, "pH Level")
        assert m is not None and m["status"] == "pending"
        assert "Phone Level" in m["aliases"]     # rescans fold, not re-propose
        assert m["definition"].startswith("Acidity/alkalinity")

    def test_governed_entries_never_auto_change(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Meter Size", "public.meters.meter_size",
                                  Definition="original governed definition")])
        tagdict.review("term", ["Meter Size"], "approve")
        n = tagdict.refresh_pending([make_row(
            "Meter Size", "public.meters.meter_size",
            Definition="an enriched definition that must NOT land")])
        assert n == 0
        m = _pending_meta(tagdict, "Meter Size")
        assert m["definition"] == "original governed definition"
        assert m["status"] == "approved"

    def test_stale_pending_twin_folds_into_existing_term(self, fresh_dict):
        tagdict = fresh_dict
        # governed canonical term + a stale pending misread from a later scan
        tagdict.accrete([make_row("pH Level", "public.water_quality_reports.ph_level")])
        tagdict.review("term", ["pH Level"], "approve")
        tagdict.accrete([make_row("Phone Level", "public.system_status.ph_level")])
        n = tagdict.refresh_pending([make_row(
            "pH Level", "public.system_status.ph_level")])
        assert n == 1
        assert _pending_meta(tagdict, "Phone Level") is None
        m = _pending_meta(tagdict, "pH Level")
        assert "Phone Level" in m["aliases"]
        assert m["status"] == "approved"

    def test_glossary_save_triggers_refresh(self, client):
        from engine import tagdict
        tagdict.accrete([make_row("Alert Type", "public.account_alerts.alert_type",
                                  Definition="raw scan definition.")])
        r = client.post("/api/glossaries", json={
            "name": "awc-test",
            "rows": [make_row("Alert Type", "public.account_alerts.alert_type",
                              Definition="Steward-accepted enriched definition.")]})
        assert r.status_code == 200
        assert r.json()["pending_refreshed"] == 1
        assert _pending_meta(tagdict, "Alert Type")["definition"].startswith("Steward-accepted")


class TestCaseOnlyRename:
    def test_case_correction_adopts_stewards_casing(self, fresh_dict):
        """"Ph Level" -> "pH Level" never reached the rename path: the
           case-folded index matched, the definition refreshed, and the stored
           name kept the scan's casing forever (field-caught - the steward
           fixed the term and the pending queue kept showing "Ph Level")."""
        tagdict = fresh_dict
        tagdict.accrete([make_row("Ph Level", "awc_operations.water_quality_reports.ph_level",
                                  Definition="Ph Level associated with a water quality report record.")])
        n = tagdict.refresh_pending([make_row(
            "pH Level", "awc_operations.water_quality_reports.ph_level",
            Definition="The acidity or alkalinity level of water samples.")])
        assert n >= 1
        assert _pending_meta(tagdict, "Ph Level") is None
        m = _pending_meta(tagdict, "pH Level")
        assert m is not None and m["status"] == "pending"
        assert "Ph Level" in m["aliases"], "raw casing folds - rescans don't re-propose"
        assert m["definition"].startswith("The acidity")


class TestAutoPrunedKeysStayOut:
    def test_pruned_keys_never_enter_pending(self, fresh_dict):
        """The scan already answered a surrogate key - the pending queue must
           not ask the steward again (field-caught: System ID, Alert ID and
           friends piled into a 135-item review)."""
        tagdict = fresh_dict
        tagdict.accrete([make_row("System ID", "public.water_systems.system_id",
                                  Keep="No", Prune_Reason="surrogate PK/FK reference id",
                                  Suggested_Tags="identifier")])
        assert _pending_meta(tagdict, "System ID") is None
        assert "identifier" not in tagdict.load()["tags"] or \
            tagdict.load()["tags"]["identifier"].get("layer") == "generic", \
            "a pruned key's tags must not seed the allow-list"

    def test_legacy_pending_keys_retro_retire_on_save(self, fresh_dict):
        """Entries absorbed before the accrete guard existed retire on the
           next glossary save - popped and tombstoned like a steward click -
           while a row merely UNTICKED by the steward (no Prune_Reason) is
           left alone: dropped from one glossary is not retired company-wide."""
        tagdict = fresh_dict
        tagdict.accrete([make_row("System ID", "public.water_systems.system_id"),
                         make_row("Correspondence", "awc-documents/correspondence")])
        n = tagdict.refresh_pending([
            make_row("System ID", "public.water_systems.system_id",
                     Keep="No", Prune_Reason="surrogate PK/FK reference id"),
            make_row("Correspondence", "awc-documents/correspondence", Keep="No"),
        ])
        assert n >= 1
        assert _pending_meta(tagdict, "System ID") is None
        assert "System ID" in tagdict.load()["retired"]["terms"], "tombstoned - durable"
        assert _pending_meta(tagdict, "Correspondence") is not None, \
            "steward-dropped without Prune_Reason stays pending"


class TestStalePendingDetection:
    """The Dictionary is a stage-gate in the workflow now (Review -> Dictionary
       -> Govern), so its pending queue must hold only questions the current
       estate actually raises. Entries whose sources, name and aliases appear
       in NO saved glossary are fossils from scans whose rows are gone -
       refresh_pending can only carry improvements from rows that exist, so
       nothing can ever fix them (field-caught: "Flow", category Uncategorized,
       from a May snapshot file, matching zero rows in the review)."""

    def test_fossils_are_reported_and_live_entries_are_not(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([
            make_row("Flow", "public.pinal_valley_pressure_2026-05-14.json.export_metadata.units.flow",
                     Suggested_Tags="uncategorized"),
            make_row("Base Charge", "awc_operations.monthly_usage.base_charge",
                     Suggested_Tags="financial"),
        ])
        health = tagdict.stale_pending(
            sources={"awc_operations.monthly_usage.base_charge"},
            terms={"base charge"}, tags={"financial"})
        assert "Flow" in health["terms"]
        assert "Base Charge" not in health["terms"]
        assert "uncategorized" in health["tags"]
        assert "financial" not in health["tags"]

    def test_name_match_keeps_an_entry_alive_when_sources_moved(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Ph Level", "old_scan.water.ph_level")])
        health = tagdict.stale_pending(sources=set(), terms={"ph level"}, tags=set())
        assert "Ph Level" not in health["terms"], \
            "a name still carried by any glossary is evidence enough"

    def test_governed_entries_are_never_reported(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Meter Size", "public.meters.meter_size")])
        tagdict.review("term", ["Meter Size"], "approve")
        health = tagdict.stale_pending(sources=set(), terms=set(), tags=set())
        assert "Meter Size" not in health["terms"], \
            "approved vocabulary is the steward's decision, not debris"


class TestValuePatternTravelsWithTheEntry:
    """For *_id candidates the induced value pattern is THE discriminator
       between a quoted business identifier (Meter ID - coded format) and a
       surrogate key (bare integer). The steward and the advisor both need it
       at the decision point - field-caught twice (Meter ID, Report ID)."""

    def test_accrete_captures_and_refresh_updates(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Meter ID", "public.meters.meter_id",
                                  Value_Pattern=r"^MTR-\d{6}$")])
        m = _pending_meta(tagdict, "Meter ID")
        assert m["pattern"] == r"^MTR-\d{6}$"
        tagdict.refresh_pending([make_row("Meter ID", "public.meters.meter_id",
                                          Value_Pattern=r"^MTR-\d{7}$")])
        assert _pending_meta(tagdict, "Meter ID")["pattern"] == r"^MTR-\d{7}$"

    def test_bare_id_stays_patternless(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Report ID", "public.water_quality_reports.report_id")])
        assert _pending_meta(tagdict, "Report ID")["pattern"] == "", \
            "absence of a pattern IS the surrogate-key signal - never invent one"


class TestFoldTargetsResolveHonestly:
    """A fold is durable, so its target resolution must be honest: typed
       targets resolve case-insensitively, and a miss is a full no-op - the
       old exact-key lookup silently did nothing while the UI toasted
       success (field-caught: 'you don't know what you're folding into')."""

    def test_alias_target_resolves_case_insensitively(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("pH Level", "a.w.ph_level"),
                         make_row("Ph Reading", "a.s.ph_reading")])
        tagdict.review("term", ["pH Level"], "approve")
        tagdict.review("term", ["Ph Reading"], "alias", target="ph level")
        d = tagdict.load()["terms"]
        assert "Ph Reading" not in d, "folded away"
        assert "Ph Reading" in d["pH Level"]["aliases"]

    def test_unknown_target_is_a_full_noop(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Ph Reading", "a.s.ph_reading")])
        tagdict.review("term", ["Ph Reading"], "alias", target="No Such Term")
        d = tagdict.load()["terms"]
        assert "Ph Reading" in d, "a target miss must change nothing"
        assert "Ph Reading" not in tagdict.load().get("retired", {}).get("terms", [])


class TestRetiredTagsDisappearEverywhere:
    """Retiring a tag removed it from the allow-list while every term that
       ever carried it kept displaying it - "uncategorized on everything",
       field-caught. A retire must strip the tag from all term entries, and
       the tombstone must beat a stale Suggested_Tags string on rescan."""

    def test_reject_strips_the_tag_from_every_term(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Contaminant Level", "a.w.contaminant_level",
                                  Suggested_Tags="uncategorized;operational")])
        assert "uncategorized" in tagdict.load()["terms"]["Contaminant Level"]["tags"]
        tagdict.review("tag", ["uncategorized"], "reject")
        d = tagdict.load()
        assert "uncategorized" not in d.get("tags", {})
        assert d["terms"]["Contaminant Level"]["tags"] == ["operational"]

    def test_tombstoned_tag_never_rides_back_in(self, fresh_dict):
        tagdict = fresh_dict
        tagdict.accrete([make_row("Seed", "a.t.seed", Suggested_Tags="uncategorized")])
        tagdict.review("tag", ["uncategorized"], "reject")
        tagdict.accrete([make_row("Copper Ppm", "a.w.copper_ppm",
                                  Suggested_Tags="uncategorized;operational")])
        d = tagdict.load()
        assert "uncategorized" not in d.get("tags", {}), "the tombstone holds"
        assert "uncategorized" not in (d["terms"]["Copper Ppm"].get("tags") or [])

    def test_a_pattern_the_data_no_longer_has_is_cleared(self, fresh_dict):
        """Field-caught on the AWC clean run (2026-08-21).

        The seeder had filled twelve columns with one code shape. Once the
        estate was repaired those columns held words, the rescan induced an
        enum and NO pattern, and the row arrived with Value_Pattern blank.
        Guarded on `pattern and`, the blank could not overwrite: eight pending
        terms kept ^[A-Z]{2}[0-9]{4}$, one Approve away from entering the
        governed vocabulary and seeding a Data Pattern that matches zero rows
        and can never fire.

        A pattern is evidence, and the pending entry is a projection of the
        row: no shape on the row means no shape on the term.
        """
        tagdict = fresh_dict
        tagdict.accrete([make_row("County", "public.water_systems.county",
                                  Value_Pattern="^[A-Z]{2}[0-9]{4}$")])
        assert _pending_meta(tagdict, "County")["pattern"] == "^[A-Z]{2}[0-9]{4}$"

        n = tagdict.refresh_pending([make_row(
            "County", "public.water_systems.county",
            Value_Pattern="", Enum_Values="Cochise;Coconino;Navajo;Pinal")])
        assert n == 1, "clearing a dead pattern is a change"
        m = _pending_meta(tagdict, "County")
        assert not m.get("pattern"), \
            f"the term still asserts {m.get('pattern')!r}, a shape the data no longer has"
        assert m["status"] == "pending", "still the steward's call"

    def test_prose_stays_fill_only(self, fresh_dict):
        """Definition and category are steward prose, not evidence: a blank
        means 'nothing new to say', never 'it is gone'."""
        tagdict = fresh_dict
        tagdict.accrete([make_row("Alert Type", "public.account_alerts.alert_type",
                                  Definition="Classifies an account alert.")])
        tagdict.refresh_pending([make_row("Alert Type", "public.account_alerts.alert_type",
                                          Definition="", Category="")])
        m = _pending_meta(tagdict, "Alert Type")
        assert m["definition"] == "Classifies an account alert.", "a blank erased steward prose"
