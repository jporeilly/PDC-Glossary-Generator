"""The sample seeder's value rules (1.38.35).

The defect these guard against: every text column without a name rule fell
through to one generic fallback — two uppercase letters plus the row index —
so twelve unrelated columns on the AWC estate (county, severity, notes,
description, recommended_action, contaminant_level, system_type, source_type,
primary_source, conservation_focus, service_county and a second notes) all
came back as 'WQ2602'. A profiler then induces ONE pattern that fits all
twelve, the drafter backs every one of those concepts with it, and free-text
`notes` arrives bound to all of them. The app-side fix was to name-anchor the
seeds; this is the fix underneath it.

The rule the suite enforces: no two unrelated text columns may share a shape.
"""
import random
import re

from sources import seed_sample as S


def gen(col, dtype="character varying", row_i=1042, row=None):
    return S._gen(col, dtype, row_i, {}, row or {})


def shape(v):
    """The pattern a naive profiler would induce from one value."""
    return re.sub(r"[0-9]", "n", re.sub(r"[A-Za-z]", "a", str(v)))


class TestNoSharedShape:
    # the twelve that collided, plus the free-text ones they dragged in
    COLLIDED = ["county", "service_county", "severity", "contaminant_level",
                "system_type", "source_type", "primary_source",
                "conservation_focus", "notes", "description",
                "recommended_action"]

    def test_none_of_them_fall_to_the_generic_fallback(self):
        random.seed(3)
        for col in self.COLLIDED:
            v = gen(col)
            assert not re.match(r"^[A-Z]{2}[0-9]+$", str(v)), \
                f"{col} still answers with the shape-collision fallback: {v!r}"

    def test_unrelated_columns_do_not_share_one_shape(self):
        random.seed(3)
        shapes = {}
        for col in self.COLLIDED:
            shapes.setdefault(shape(gen(col)), []).append(col)
        worst = max(shapes.values(), key=len)
        assert len(worst) < 4, \
            f"{len(worst)} unrelated columns share one induced shape: {worst}"

    def test_fallback_is_anchored_to_the_column_name(self):
        # a column nothing recognises must STILL not collide with the next one
        a, b = gen("some_unmapped_column"), gen("another_unmapped_column")
        assert shape(a) != shape(b), \
            "the fallback shape must differ per column, not per row"
        assert "SOME-UNMAPPED-COLUMN" in a, "filler should name the column it fills"


class TestEstateVocabularies:
    def test_county_follows_the_city_on_its_own_row(self):
        assert gen("service_county", row={"service_city": "Sierra Vista"}) == "Cochise"
        assert gen("service_county", row={"service_city": "Casa Grande"}) == "Pinal"

    def test_county_without_a_city_still_reads_as_a_county(self):
        random.seed(1)
        assert gen("county") in S.COUNTIES

    def test_severity_and_contaminant_level_use_the_estates_words(self):
        random.seed(1)
        assert gen("severity") in S.SEVERITY
        assert gen("contaminant_level") in S.CONTAM_LEVEL

    def test_meter_id_takes_the_estate_format(self):
        random.seed(1)
        assert re.match(r"^[A-Z]{2}[0-9]{6}$", gen("meter_id")), \
            "2 letters + 6 digits — a 4-digit fallback split the induced pattern in two"

    def test_notes_is_prose_not_a_code(self):
        random.seed(1)
        assert len(gen("notes")) > 30


class TestTypeDecidesNotJustTheName:
    def test_rating_takes_labels_in_text_and_a_scale_in_numbers(self):
        random.seed(1)
        assert gen("quality_rating", "character varying") in S.RATING_LABEL
        assert gen("quality_rating", "integer") in range(1, 6)

    def test_money_rules_stay_off_non_money_columns(self):
        # 'rate' matched rate_id (an integer PK) and rate_period (a varchar
        # year), and both were handed a dollar amount
        assert gen("rate_period", "character varying") in ("2024", "2025", "2026")
        assert isinstance(gen("rate_id", "integer"), int)


class TestRateCardAndBill:
    def test_tier_edges_never_cross(self):
        for i in (1, 2, 3, 4):
            lo = gen(f"tier{i}_from_gallons", "integer")
            hi = gen(f"tier{i}_to_gallons", "integer")
            assert lo < hi, f"tier {i} starts at {lo} and ends at {hi}"

    def test_tier_from_continues_the_previous_tier(self):
        assert gen("tier2_from_gallons", "integer") == gen("tier1_to_gallons", "integer")

    def test_tier_gallons_split_the_rows_usage(self):
        row = {"usage_gallons": 22000}
        got = [gen(f"usage_tier_{i}_gallons", "integer", row=row) for i in (1, 2, 3, 4)]
        assert sum(got) == 22000, f"tiers {got} do not add up to the usage"

    def test_the_bill_adds_up(self):
        row = {"base_charge": 20.0, "wastewater_charge": 30.0,
               "tier_1_charge": 12.0, "tier_2_charge": 8.0,
               "tier_3_charge": 0.0, "tier_4_charge": 0.0}
        row["total_before_tax"] = gen("total_before_tax", "numeric", row=row)
        assert row["total_before_tax"] == 70.0
        row["tax_amount"] = gen("tax_amount", "numeric", row=row)
        row["total_due"] = gen("total_due", "numeric", row=row)
        assert row["total_due"] == round(70.0 + row["tax_amount"], 2)

    def test_an_unpaid_bill_has_not_been_paid(self):
        row = {"total_due": 82.5, "payment_status": "Unpaid"}
        assert gen("amount_paid", "numeric", row=row) == 0
        row["payment_status"] = "Paid"
        assert gen("amount_paid", "numeric", row=row) == 82.5


class TestChemistryStaysInRange:
    def test_readings_are_drinking_water_readings(self):
        random.seed(5)
        for _ in range(20):
            assert 0.2 <= gen("chlorine_residual", "numeric") <= 4.0
            assert 0 <= gen("copper_ppm", "numeric") <= 1.3
            assert 150 <= gen("total_dissolved_solids_ppm", "integer") <= 900


class TestOneRowNamesOnePlace:
    """The estate's geography comes from ONE table — AWC_SYSTEMS, read off the
    original water_systems rows. Before that, city, county, system name and
    account code were four independent draws, so the seeder produced rows like
    "Phoenix System 2009 | Navajo | Tempe", and put 1000 of 1010 customers in
    seven metros this utility does not serve (Maricopa alone took 852).
    """
    def test_every_city_belongs_to_exactly_one_system_and_county(self):
        assert S.CITY_FACTS, "the geography table is empty"
        for city, (county, system, code) in S.CITY_FACTS.items():
            assert county and system and code, f"{city} is incompletely described"
        assert len(S.CODE_CITY) == len(S.CITY_FACTS), "two cities share an account code"

    def test_the_invented_metros_are_gone(self):
        for gone in ("Phoenix", "Tucson", "Mesa", "Tempe", "Chandler",
                     "Scottsdale", "Glendale"):
            assert gone not in S.CITY_FACTS, \
                f"{gone} is a municipal utility, not one of this estate's service areas"

    def test_a_customer_row_names_one_place(self):
        """account code -> city -> county -> service area, all agreeing."""
        for i in range(40):
            row = {}
            row["account_number"] = S._gen("account_number", "character varying", 3000 + i, {}, row)
            row["service_city"] = S._gen("service_city", "character varying", 3000 + i, {}, row)
            row["service_county"] = S._gen("service_county", "character varying", 3000 + i, {}, row)
            row["service_area_system"] = S._gen("service_area_system", "character varying",
                                                3000 + i, {}, row)
            code = row["account_number"].split("-")[1]
            city = S.CODE_CITY[code]
            county, system, _ = S.CITY_FACTS[city]
            assert row["service_city"] == city, row
            assert row["service_county"] == county, row
            assert row["service_area_system"] == system, row

    def test_a_water_system_row_names_one_place(self):
        by_system = {s: (c, cs) for s, c, cs in S.AWC_SYSTEMS}
        for i in range(40):
            row = {}
            row["system_name"] = S._gen("system_name", "character varying", 4000 + i, {}, row)
            row["service_cities"] = S._gen("service_cities", "character varying", 4000 + i, {}, row)
            row["county"] = S._gen("county", "character varying", 4000 + i, {}, row)
            stem = S._system_stem(row["system_name"])
            assert stem, f"system_name is not built from a real system: {row['system_name']}"
            county, cities = by_system[stem]
            assert row["county"] == county, row
            assert row["service_cities"] == ", ".join(c for c, _ in cities), row

    def test_system_names_stay_unique_across_a_run(self):
        names = {S._gen("system_name", "character varying", i, {}, {}) for i in range(200)}
        assert len(names) == 200, "system_name carries a UNIQUE constraint"
