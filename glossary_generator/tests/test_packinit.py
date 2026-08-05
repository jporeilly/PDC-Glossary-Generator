"""packinit — the thin-pack scaffolder.

A pack is read by three engines from one file, so writing one from scratch means
getting a shape you cannot guess. Without it a new scenario starts with NO pack,
which is how an estate ends up letting the model carry classification that rules
should be doing. This scaffolds the skeleton; the export step grows it.
"""
import json

import packinit


class TestScaffold:
    def test_seeds_one_keyword_per_category(self):
        pack, _ = packinit.scaffold("credit_union", "Copper State",
                                    ["Member", "Lending", "Payments"])
        assert pack["cat_keywords"] == [["member", "Member"], ["lending", "Lending"],
                                        ["payments", "Payments"]]

    def test_prefers_the_distinctive_last_word(self):
        """'Billing & Rates' is about rates; 'Water Quality' about quality."""
        pack, _ = packinit.scaffold("d", None, ["Water Quality"])
        assert pack["cat_keywords"] == [["quality", "Water Quality"]]

    def test_never_emits_a_rule_that_cannot_fire(self):
        """suggester matches builtins FIRST, so a pack rule repeating one is dead
           weight that reads as configured behaviour."""
        pack, skipped = packinit.scaffold("d", None, ["Customer", "Usage"])
        assert pack["cat_keywords"] == []
        assert len(skipped) == 2
        assert all("builtin" in why for _, _, why in skipped)

    def test_duplicate_keywords_are_dropped_not_shadowed(self):
        """cat_keywords is first-match; a second rule on the same word is dead."""
        pack, skipped = packinit.scaffold("d", None, ["Field Service", "Customer Service"])
        assert [k for k, _ in pack["cat_keywords"]] == ["service"]
        assert any("already claims" in why for _, _, why in skipped)

    def test_a_category_with_no_usable_word_is_reported(self):
        """Silently leaving a category unmatched is the failure this prevents."""
        pack, skipped = packinit.scaffold("d", None, ["Records & Documents"])
        assert pack["cat_keywords"] == []
        assert skipped and "too generic" in skipped[0][2]

    def test_evidence_driven_keys_are_left_empty(self):
        """Inventing table names for an estate nobody has scanned produces rules
           that never match and look curated. The export step fills these."""
        pack, _ = packinit.scaffold("d", None, ["Member"])
        for k in ("table_category", "table_terms", "tag_rules", "terms", "abbreviations"):
            assert pack[k] == ({} if isinstance(pack[k], dict) else [])

    def test_tags_are_slugified_and_pre_approved(self):
        pack, _ = packinit.scaffold("d", None, ["Accounts & Cards"])
        assert pack["category_tags"]["Accounts & Cards"] == ["accounts-cards"]
        assert "accounts-cards" in pack["extra_tags"]

    def test_output_is_valid_json_and_names_the_lifecycle(self):
        pack, _ = packinit.scaffold("water_utility", "Arizona Water Company", ["Usage2"])
        json.dumps(pack)
        assert "Export domain pack" in pack["note"]
        assert pack["domain"] == "water_utility"


class TestCli:
    def test_refuses_to_clobber_an_existing_pack(self, tmp_path, capsys):
        p = tmp_path / "pack.json"
        p.write_text("{}", encoding="utf-8")
        rc = packinit.main(["--domain", "d", "-o", str(p)])
        assert rc == 2, "a hand-curated pack must never be overwritten silently"
        assert p.read_text(encoding="utf-8") == "{}"

    def test_force_overwrites(self, tmp_path):
        p = tmp_path / "pack.json"
        p.write_text("{}", encoding="utf-8")
        assert packinit.main(["--domain", "d", "-o", str(p), "--force"]) == 0
        assert json.loads(p.read_text(encoding="utf-8"))["domain"] == "d"
