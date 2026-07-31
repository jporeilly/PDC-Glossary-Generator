"""The scan's own fallback definition reads like prose but says nothing — it has
to be flagged, because that flag is what turns into the AI pass's REWRITE
REQUIRED instruction."""
import defqa


def _lint(term, definition):
    return defqa.lint_rows([{"Term": term, "Definition": definition, "Keep": "Y"}])


class TestTemplatedDefinitions:
    def test_associated_with_a_record_is_flagged(self):
        f = _lint("Severity", "Severity associated with an account alert record.")
        assert f and "generic scan template" in f[0][0]

    def test_reference_linking_is_flagged(self):
        f = _lint("Customer ID", "Reference linking this record to its related customer.")
        assert f and "generic scan template" in f[0][0]

    def test_unique_identifier_for_a_record_is_flagged(self):
        f = _lint("Alert ID", "Unique identifier for a account alert record.")
        assert f and "generic scan template" in f[0][0]

    def test_a_specific_definition_is_not_flagged(self):
        assert _lint("Meter ID",
                     "The formatted asset number stamped on a physical water meter.") == {}
        assert _lint("pH Level",
                     "Acidity of the water on the 0-14 pH scale, EPA target 6.5-8.5.") == {}

    def test_an_enumerated_definition_is_not_flagged(self):
        assert _lint("Alert Type",
                     "Type of alert. Values: High Usage, Payment Overdue, Low Pressure.") == {}
