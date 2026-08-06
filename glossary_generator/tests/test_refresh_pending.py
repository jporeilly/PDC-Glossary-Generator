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
