"""Structural-key pruning vs profiling evidence: tiny demo tables must not
turn surrogate ids into kept 'enum' business terms."""
import suggester


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
    """PDC's Data Discovery flattens a nested file into dotted paths, so every
       JSON in a document store emits a batch of candidates like
       'export_metadata.units.flow' — file structure, not business concepts.
       Same handling as a surrogate key: pruned by default, reason on the row,
       restorable with one tick of Keep."""

    def test_envelope_paths_are_pruned_with_a_specific_reason(self):
        import suggester
        r = suggester.document_path_prune("export_metadata.units.flow")
        assert r and "envelope" in r
        assert suggester.document_path_prune("metadata.source")

    def test_control_fields_are_pruned(self):
        import suggester
        for name in ("_id", "$schema", "@timestamp"):
            assert suggester.document_path_prune(name), name

    def test_nested_paths_are_pruned_and_say_the_leaf_is_the_concept(self):
        import suggester
        r = suggester.document_path_prune("readings.pump_status")
        assert r and "leaf" in r

    def test_a_plain_business_column_is_kept(self):
        """The rules must not fire on ordinary columns — a database column name
           has no path separator, so they cannot reach one."""
        import suggester
        for name in ("asset_id", "street_name", "condition_rating",
                     "capacity_units", "latitude", "install_year"):
            assert suggester.document_path_prune(name) is None, name
