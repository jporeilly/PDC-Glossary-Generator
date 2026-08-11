"""Structural-key pruning vs profiling evidence: tiny demo tables must not
turn surrogate ids into kept 'enum' business terms."""
from engine import suggester


class TestEnumNeedsRepetition:
    def test_unique_ids_are_not_an_enum(self):
        # 10 rows, 10 distinct ids — the old rule called this an enum
        prof = suggester._profile_values("customer_id", [str(v) for v in range(1001, 1011)], 10)
        assert prof.get("kind") != "enum"
        assert not prof.get("enum")
        assert prof.get("kind") == "identifier"      # near-unique numeric ids

    def test_repeated_codes_still_profile_as_enum(self):
        vals = ["Active", "Suspended", "Closed"] * 4   # 12 rows, 3 distinct
        prof = suggester._profile_values("account_status", vals, 12)
        assert prof.get("kind") == "enum"
        assert prof.get("enum") == ["Active", "Closed", "Suspended"]


class TestColumnNoisePrune:
    """Field: "some of these Terms should have been retired: Length Feet,
       Total Revenue May 2026, Description". The two CRISP signatures prune
       deterministically with the reason on the row; judgment calls (Length
       Feet) stay with the AI advisor."""

    def _col(self, name):
        return {"table": "reports", "column": name, "type": "text",
                "ordinal": 1, "notnull": False, "unique": False,
                "pk": False, "fk": False, "comment": "", "profile": {}}

    def test_period_stamped_and_structural_columns_start_unkept(self):
        rows = suggester.suggest({"reports": [
            self._col("total_revenue_may_2026"),
            self._col("revenue_2026q1"),
            self._col("description"),
            self._col("notes"),
            self._col("county")]}, schema="awc_operations")
        by = {r["Source_Column"].split(".")[-1]: r for r in rows
              if r["Source_Column"]}
        assert by["total_revenue_may_2026"]["Keep"] == "N"
        assert "period-stamped" in by["total_revenue_may_2026"]["Prune_Reason"]
        assert by["revenue_2026q1"]["Keep"] == "N"
        assert by["description"]["Keep"] == "N"
        assert "structural column name" in by["description"]["Prune_Reason"]
        assert by["notes"]["Keep"] == "N"
        assert by["county"]["Keep"] == "Y", "real vocabulary is untouched"

    def test_qualified_and_yearless_names_are_not_noise(self):
        rows = suggester.suggest({"reports": [
            self._col("asset_description"),     # qualified — a real concept
            self._col("install_year"),          # names a concept, no stamp
            self._col("tier1_gallons")]}, schema="awc_operations")
        assert all(r["Keep"] == "Y" for r in rows if r["Source_Column"]), \
            [r["Prune_Reason"] for r in rows if r["Source_Column"]]


class TestKeyPrune:
    def _col(self, name, pk=False, fk=False, profile=None):
        return {"table": "customers", "column": name, "type": "integer",
                "ordinal": 1, "notnull": True, "unique": False,
                "pk": pk, "fk": fk, "comment": "", "profile": profile or {}}

    def _row_for(self, rows, col):
        return next(r for r in rows if r["Source_Column"].endswith("." + col))

    def test_declared_pk_is_pruned_even_with_enum_evidence(self):
        # a low-cardinality profile must not stop the structural prune
        rows = suggester.suggest({"customers": [
            self._col("customer_id", pk=True,
                      profile={"uniq": 1.0, "enum": [str(v) for v in range(1001, 1011)]})]},
            schema="awc_operations")
        r = self._row_for(rows, "customer_id")
        assert r["Keep"] == "N"
        assert "structural key" in r["Prune_Reason"]
        assert r["Source_Column"] == "awc_operations.customers.customer_id"

    def test_view_column_inherits_base_table_key(self):
        # a summary VIEW re-exposing customers.customer_id can't declare an FK;
        # the name-match against the base table's PK marks it structural anyway
        tables = {
            "customers": [self._col("customer_id", pk=True)],
            "customer_billing_summary": [
                dict(self._col("customer_id"), table="customer_billing_summary"),
                dict(self._col("total_outstanding"), table="customer_billing_summary")],
        }
        suggester._inherit_view_keys(tables, {"customer_billing_summary"},
                                     pks={("customers", "customer_id")}, fks=set(), fkref={})
        vcols = {c["column"]: c for c in tables["customer_billing_summary"]}
        assert vcols["customer_id"]["fk"] is True
        assert vcols["customer_id"]["ref_table"] == "customers"
        assert vcols["total_outstanding"]["fk"] is False   # non-key names untouched
        rows = suggester.suggest(tables, schema="awc_operations")
        r = self._row_for(rows, "total_outstanding")       # non-key stays a kept term
        assert r["Keep"] == "Y"

    def test_formatted_natural_key_stays_kept(self):
        # a value SIGNATURE (formatted account number) marks a natural key
        rows = suggester.suggest({"customers": [
            self._col("account_id", pk=True,
                      profile={"uniq": 1.0, "signature": "AAA-AA-nnnnnn",
                               "pattern": r"^AWC-[A-Z]{2}-\d{6}$"})]},
            schema="awc_operations")
        r = self._row_for(rows, "account_id")
        assert r["Keep"] == "Y"


class TestDocumentPathPrune:
    """PDC's Data Discovery flattens a nested file into dotted paths. The line to
       draw is ENVELOPE (describes the file) vs PAYLOAD (the data in it) — not
       "is it nested", which caught regulated water-quality measures in the first
       version of this rule."""

    def test_envelope_paths_are_pruned(self):
        from engine import suggester
        assert "envelope" in suggester.document_path_prune("export_metadata.units.flow")
        assert suggester.document_path_prune("metadata.source")

    def test_control_fields_are_pruned(self):
        from engine import suggester
        for name in ("_id", "$schema", "@timestamp"):
            assert suggester.document_path_prune(name), name

    def test_bookkeeping_fields_are_pruned(self):
        """Fields about the extract rather than the data, wherever they sit."""
        from engine import suggester
        for name in ("readings.timestamp", "readings.sensor_id", "rows.record_id",
                     "readings.source", "batch.checksum"):
            assert suggester.document_path_prune(name), name

    def test_payload_measures_are_KEPT(self):
        """The regression that mattered: chlorine residual and turbidity are
           regulated drinking-water measures — precisely what a utility governs.
           Nesting is a fact about the file format, not a reason to drop them."""
        from engine import suggester
        for name in ("systems.chlorine_residual_ppm", "systems.turbidity_ntu",
                     "readings.flow_gpm", "readings.pressure_psi",
                     "readings.reservoir_level_percent", "systems.population_served",
                     "readings.pump_status", "readings.alarm"):
            assert suggester.document_path_prune(name) is None, name

    def test_a_plain_business_column_is_kept(self):
        from engine import suggester
        for name in ("asset_id", "street_name", "condition_rating", "latitude"):
            assert suggester.document_path_prune(name) is None, name


class TestDocumentLeafName:
    """The JSON container ('systems', 'readings') names the file's shape, not the
       concept, so the term should be the leaf — which also lets the same concept
       arriving from a database column merge with it."""

    def test_leaf_is_taken_from_a_path(self):
        from engine import suggester
        assert suggester.document_leaf_name("systems.chlorine_residual_ppm") == "chlorine_residual_ppm"
        assert suggester.document_leaf_name("a.b.c") == "c"

    def test_plain_names_pass_through(self):
        from engine import suggester
        assert suggester.document_leaf_name("asset_id") == "asset_id"
        assert suggester.document_leaf_name("") == ""


class TestDocumentTableTermNames:
    """A document store's 'table' is a FILE, so its name carries two things a
       term must not: the extension, and — on an exported snapshot — the period
       it was cut for. Leaving the period in mints a NEW term per export, so the
       glossary accretes one term per file per day and nothing ever merges."""

    def test_extension_is_dropped(self):
        from engine import suggester
        assert suggester.table_term_name("asset_inventory.csv") == "Asset Inventory Record"

    def test_a_dated_snapshot_collapses_to_one_stable_term(self):
        """Today's and tomorrow's export must be the SAME term."""
        from engine import suggester
        a = suggester.table_term_name("pinal_valley_pressure_2026-05-14.json")
        b = suggester.table_term_name("pinal_valley_pressure_2026-05-15.json")
        assert a == b == "Pinal Valley Pressure Record"

    def test_every_period_shape_an_export_uses(self):
        from engine import suggester
        for name, want in (("epa_compliance_bisbee_2026Q1.pdf", "Epa Compliance Bisbee Record"),
                           ("usage_202605.csv", "Usage Record"),
                           ("report_2026_H2.xlsx", "Report Record")):
            assert suggester.table_term_name(name) == want, name

    def test_database_tables_are_untouched(self):
        from engine import suggester
        assert suggester.table_term_name("customers") == "Customer Record"
        assert suggester.table_term_name("water_systems") == "Water System Record"

    def test_the_pack_still_wins_over_the_derived_name(self, monkeypatch):
        """A curated table_terms entry must not be bypassed by the cleanup —
           looked up both on the raw name and on the cleaned stem, so a pack can
           key on either 'usage_2026.csv' or 'usage'."""
        from engine import suggester
        monkeypatch.setitem(suggester.TABLE_TERMS, "tiered_rates", "Rate Plan Record")
        monkeypatch.setitem(suggester.TABLE_TERMS, "usage", "Consumption Record")
        assert suggester.table_term_name("tiered_rates") == "Rate Plan Record"
        assert suggester.table_term_name("usage_202605.csv") == "Consumption Record"


class TestDocumentColumnCategory:
    """A file name is a poor proxy for what its columns are about: one SCADA
       snapshot holds turbidity and chlorine (water quality) beside pump status
       and reservoir level (water system). Whatever single keyword the FILE
       matched would file the lot under it — which is how a harvested
       'Turbidity Ntu' landed in Water System while the database's own sat in
       Water Quality, leaving two rows that can never merge (Category + Term)."""

    def _cats(self, monkeypatch, pairs):
        from engine import suggester
        monkeypatch.setattr(suggester, "CAT_KEYWORDS",
                            [("turbidity", "Water Quality"), ("chlorine", "Water Quality"),
                             ("system", "Water System")])
        return {c: suggester.categorize_column(c) for c in pairs}

    def test_a_measure_names_its_own_category(self, monkeypatch):
        got = self._cats(monkeypatch, ["turbidity_ntu", "chlorine_residual_ppm"])
        assert got["turbidity_ntu"] == "Water Quality"
        assert got["chlorine_residual_ppm"] == "Water Quality"

    def test_an_unmatched_column_defers_to_the_file(self, monkeypatch):
        """None means 'no opinion' — the caller keeps the file-level category."""
        got = self._cats(monkeypatch, ["pump_status", "flow_gpm"])
        assert got["pump_status"] is None and got["flow_gpm"] is None

    def test_it_never_consults_table_category(self, monkeypatch):
        """TABLE_CATEGORY is keyed on table names; matching a column against it
           would categorise by accident."""
        from engine import suggester
        monkeypatch.setattr(suggester, "CAT_KEYWORDS", [])
        monkeypatch.setitem(suggester.TABLE_CATEGORY, "customers", "Customer")
        assert suggester.categorize_column("customers") is None

    def test_empty_input_is_safe(self):
        from engine import suggester
        assert suggester.categorize_column("") is None
        assert suggester.categorize_column(None) is None
