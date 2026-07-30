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

    def test_formatted_natural_key_stays_kept(self):
        # a value SIGNATURE (formatted account number) marks a natural key
        rows = suggester.suggest({"customers": [
            self._col("account_id", pk=True,
                      profile={"uniq": 1.0, "signature": "AAA-AA-nnnnnn",
                               "pattern": r"^AWC-[A-Z]{2}-\d{6}$"})]},
            schema="awc_operations")
        r = self._row_for(rows, "account_id")
        assert r["Keep"] == "Y"
