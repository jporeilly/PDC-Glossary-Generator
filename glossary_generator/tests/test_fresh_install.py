"""What a customer sees on a clean machine.

Every leak found on 2026-08-06 was visible from a fresh install and invisible
from this checkout: a MinIO endpoint pre-filled with a lab IP, the water-utility
pack shipped as the only example, and one industry's vocabulary in the category
keywords, the tag dictionary and the CDE patterns. All of it was found by a
person installing the app on a laptop, which is a slow and expensive way to find
things a test can assert in a second.

These tests run against an EMPTY state directory - the state a first launch
actually has - rather than the developer's, which by then has a company, a pack
and a dictionary grown from real scans.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(REPO, "glossary_generator")

# Words that must not reach a customer machine: real hosts, real accounts, and
# any single industry's vocabulary driving classification.
BANNED = [
    r"192\.168\.\d+\.\d+",
    r"pentaho\.io",
    r"\bpdc_user\b",
    r"/mnt/user-data",
    r"\bcatalog123\b",
    r"minio_secret",
]


def _fresh(tmp_path, monkeypatch):
    """Point every store at an empty directory and reload the path resolver."""
    state = tmp_path / "state"
    state.mkdir()
    for var in ("GLOSSARY_STATE_DIR",):
        monkeypatch.setenv(var, str(state))
    for var in ("GLOSSARY_DOMAIN_PACK", "GLOSSARY_GLOSSARIES", "GLOSSARY_SETTINGS",
                "GLOSSARY_CONNECTIONS", "GLOSSARY_PEOPLE", "GLOSSARY_AUDIT_LOG",
                "GLOSSARY_TAG_DICTIONARY", "GLOSSARY_REGISTRY_DIR", "GLOSSARY_COMPANY"):
        monkeypatch.delenv(var, raising=False)
    from core import paths
    paths.reset_cache()
    return state


class TestFreshState:
    def test_no_domain_pack_is_installed(self, tmp_path, monkeypatch):
        """The installer ships no pack, so a fresh app must not find one.

        It shipped water_utility.example.json until 1.35.0 - one customer's
        industry as the default vocabulary on every machine.
        """
        _fresh(tmp_path, monkeypatch)
        from core import paths
        assert not os.path.isfile(paths.domain_pack_path()), \
            "a domain pack is present on a fresh install: " + paths.domain_pack_path()

    def test_the_engine_classifies_nothing_without_a_pack(self, tmp_path, monkeypatch):
        """Uncategorised is the honest answer. Anything else means the engine is
           asserting a taxonomy the customer never chose."""
        _fresh(tmp_path, monkeypatch)
        from engine import suggester
        assert suggester.CAT_KEYWORDS == []
        for column in ("invoice_total", "meter_reading", "customer_email"):
            assert suggester.categorize_column(column) is None, \
                "{} was categorised with no pack installed".format(column)

    def test_writes_land_in_the_state_directory(self, tmp_path, monkeypatch):
        """Not beside the code: a packaged install cannot write there."""
        state = _fresh(tmp_path, monkeypatch)
        from core import paths
        for name, var in (("glossaries.json", "GLOSSARY_GLOSSARIES"),
                          ("settings.json", "GLOSSARY_SETTINGS"),
                          ("domain_pack.json", None)):
            got = paths.domain_pack_write_path() if var is None else paths.state_path(name, var)
            assert got.startswith(str(state)), "{} would be written to {}".format(name, got)


class TestShippedSource:
    """The files an installer carries. Read as text - a leak is a string, and
    the point is to catch it before it is compiled into a bundle."""

    def _staging_excludes(self):
        """Read the exclude lists FROM the staging script.

        Keeping a second copy here would drift, and a drifted copy is worse than
        none: this test would start failing on the developer's own
        connections.json (which never ships) or, far worse, stop checking a file
        that does. One list, one place.
        """
        stage = os.path.join(REPO, "desktop", "scripts", "stage-app.ps1")
        if not os.path.isfile(stage):
            return set(), set()
        text = open(stage, encoding="utf-8").read()
        files, dirs = set(), set()
        for m in re.finditer(r"\$excludeFiles\s*(?:=|\+=)\s*@\(([^)]*)\)", text):
            files |= set(re.findall(r'"([^"]+)"', m.group(1)))
        for m in re.finditer(r"\$excludeDirs\s*(?:=|\+=)\s*@\(([^)]*)\)", text):
            dirs |= set(re.findall(r'"([^"]+)"', m.group(1)))
        return files, dirs

    def _shipped_files(self):
        skip_files, skip_dirs = self._staging_excludes()
        skip_dirs |= {"__pycache__", ".venv", ".pytest_cache"}
        for base, dirs, files in os.walk(APP):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for name in files:
                if name in skip_files or name.startswith(".env"):
                    continue
                if name.endswith((".py", ".csv", ".json")):
                    yield os.path.join(base, name)

    @pytest.mark.parametrize("pattern", BANNED)
    def test_no_real_hosts_or_accounts_in_shipped_code(self, pattern):
        rx = re.compile(pattern, re.I)
        hits = []
        for path in self._shipped_files():
            with open(path, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if line.lstrip().startswith("#"):
                        continue          # comments explain history; they ship nothing
                    if rx.search(line):
                        hits.append("{}:{}".format(os.path.relpath(path, REPO), n))
        assert not hits, "{!r} appears in shipped code at {}".format(pattern, hits)

    def test_the_sample_csv_carries_no_real_credentials(self):
        sample = os.path.join(APP, "datasources.sample.csv")
        if not os.path.isfile(sample):
            pytest.skip("no sample csv")
        text = open(sample, encoding="utf-8").read()
        assert "CHANGE_ME" in text, "the sample should show placeholders, not values"
        for pattern in BANNED:
            assert not re.search(pattern, text, re.I), \
                "{!r} in the shipped sample CSV".format(pattern)


class TestFrontendBundle:
    """The built SPA, if it has been built. Skipped otherwise so a plain
       checkout still runs the suite."""

    def _bundle(self):
        d = os.path.join(REPO, "frontend", "dist", "assets")
        if not os.path.isdir(d):
            return None
        js = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".js")]
        return js or None

    @pytest.mark.parametrize("pattern", BANNED)
    def test_no_real_hosts_in_the_built_ui(self, pattern):
        files = self._bundle()
        if not files:
            pytest.skip("frontend not built")
        rx = re.compile(pattern, re.I)
        for path in files:
            text = open(path, encoding="utf-8", errors="replace").read()
            assert not rx.search(text), \
                "{!r} is compiled into {}".format(pattern, os.path.basename(path))
