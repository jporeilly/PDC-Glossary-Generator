"""The one rule for folding a scan's value evidence into a stored row.

Three defects in a single day came from each store deciding capture-vs-refresh
for itself (rowmerge.js, tagdict.accrete, tagdict.refresh_pending). The rule
lives in engine/evidence.py now, and these are its terms.
"""
import pytest

from engine import evidence as ev


def row(**kw):
    return kw


class TestCapture:
    """First sight, or a routine rescan: fill gaps, never erase."""

    def test_fills_what_is_missing(self):
        t = {"Value_Pattern": ""}
        assert ev.merge(t, row(Value_Pattern="^AWC-[0-9]{6}$"), ev.CAPTURE)
        assert t["Value_Pattern"] == "^AWC-[0-9]{6}$"

    def test_a_blank_never_erases(self):
        # the incoming enum is new information and lands; the pattern it did
        # NOT carry must survive it
        t = {"Value_Pattern": "^AWC-[0-9]{6}$"}
        assert ev.merge(t, row(Enum_Values="a;b"), ev.CAPTURE)
        assert t["Enum_Values"] == "a;b"
        assert t["Value_Pattern"] == "^AWC-[0-9]{6}$", "capture erased evidence"

    def test_a_better_reading_still_wins(self):
        t = {"Value_Pattern": "^A$"}
        assert ev.merge(t, row(Value_Pattern="^B$"), ev.CAPTURE)
        assert t["Value_Pattern"] == "^B$"


class TestRefresh:
    """The DATA changed and the steward asked for the fresh reading to win."""

    def test_the_observation_replaces_the_set_whole(self):
        # the AWC case: a repaired column induces an enum and no shape
        t = {"Value_Pattern": "^[A-Z]{2}[0-9]{4}$", "Value_Kind": "code",
             "Enum_Values": ""}
        assert ev.merge(t, row(Enum_Values="Cochise;Pinal"), ev.REFRESH)
        assert t["Enum_Values"] == "Cochise;Pinal"
        assert t["Value_Pattern"] == "", "a dead shape survived the refresh"
        assert t["Value_Kind"] == "", "a dead kind survived the refresh"

    def test_a_scan_that_saw_nothing_erases_nothing(self):
        """Absence of observation is not observation of absence - an
        unprofilable pdf/docx row must not strip a profiled column."""
        t = {"Value_Pattern": "^AWC-[0-9]{6}$", "Value_Kind": "code"}
        assert not ev.merge(t, row(Term="Some Doc"), ev.REFRESH)
        assert t["Value_Pattern"] == "^AWC-[0-9]{6}$"

    def test_observed_reads_the_whole_row_not_one_field(self):
        assert ev.observed(row(Enum_Values="a;b"))
        assert ev.observed(row(Value_Pattern="^x$"))
        assert not ev.observed(row(Term="x", Definition="y"))
        assert not ev.observed(row(Value_Pattern="   "))


class TestProjection:
    """A store keeping one field uses the same rule - and is judged on
    whether the SCAN saw anything, not on whether its own field arrived."""

    DICT = {"pattern": "Value_Pattern"}

    def test_an_enum_only_rescan_clears_the_projected_pattern(self):
        meta = {"pattern": "^[A-Z]{2}[0-9]{4}$"}
        assert ev.merge(meta, row(Enum_Values="High;Low"), ev.REFRESH, self.DICT)
        assert not meta["pattern"], \
            "the dictionary kept a shape the row no longer induces"

    def test_an_empty_row_leaves_the_projection_alone(self):
        meta = {"pattern": "^[A-Z]{2}[0-9]{4}$"}
        assert not ev.merge(meta, row(), ev.REFRESH, self.DICT)
        assert meta["pattern"] == "^[A-Z]{2}[0-9]{4}$"

    def test_no_key_is_invented_where_none_existed(self):
        meta = {"definition": "d"}
        ev.merge(meta, row(Enum_Values="a;b"), ev.REFRESH, self.DICT)
        assert "pattern" not in meta, "a projection grew a field it never carried"


def test_an_unknown_mode_is_an_error_not_a_default():
    """The bug was a call site deciding for itself. A typo must not silently
    pick one of the two behaviours."""
    with pytest.raises(ValueError):
        ev.merge({}, row(Value_Pattern="^x$"), "fill-only")
