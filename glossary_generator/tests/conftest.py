"""Shared fixtures for the Glossary Generator test suite.

State isolation happens at IMPORT time, before any app module loads: every
persisted file (dictionary, pack, settings, connections, glossaries, roster,
audit log) is pointed into a throw-away temp dir, so the suite never reads or
writes the installed scenario config — the same guarantee the old selftest.py
gave.
"""
import os
import sys
import tempfile

_TD = tempfile.mkdtemp(prefix="glossary-pytest-")
for _var, _name in [("GLOSSARY_TAG_DICTIONARY", "tag_dictionary.json"),
                    ("GLOSSARY_DOMAIN_PACK", "domain_pack.json"),  # absent -> built-in defaults
                    ("GLOSSARY_SETTINGS", "settings.json"),
                    ("GLOSSARY_CONNECTIONS", "connections.json"),
                    ("GLOSSARY_GLOSSARIES", "glossaries.json"),
                    ("GLOSSARY_PEOPLE", "people.json"),
                    ("GLOSSARY_AUDIT_LOG", "audit_log.json"),
                    ("GLOSSARY_REGISTRY_DIR", "registries")]:
    os.environ[_var] = os.path.join(_TD, _name)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest  # noqa: E402


def make_row(term, col, **kw):
    """A minimal review row, as the scan would produce it."""
    r = {"Term": term, "Source_Column": col, "Keep": "Y", "Definition": "d.",
         "Category": "Customer", "Sensitivity": "LOW", "Suggested_Tags": ""}
    r.update(kw)
    return r


@pytest.fixture
def row():
    return make_row


@pytest.fixture
def fresh_dict():
    """A clean tag dictionary: wipe the persisted file + in-memory caches, and
    remove any pack a previous test wrote, so every test starts from the
    built-in defaults."""
    import tagdict
    for var in ("GLOSSARY_TAG_DICTIONARY", "GLOSSARY_DOMAIN_PACK"):
        try:
            os.unlink(os.environ[var])
        except OSError:
            pass
    with tagdict._LOCK:
        tagdict._DICT = None
        tagdict._COMPILED = tagdict._COMPILED_KEY = None
    yield tagdict
    with tagdict._LOCK:
        tagdict._DICT = None
        tagdict._COMPILED = tagdict._COMPILED_KEY = None


@pytest.fixture
def client(fresh_dict):
    """A TestClient over the FastAPI app, with a fresh dictionary."""
    from fastapi.testclient import TestClient
    import api as api_mod
    api_mod._JOBS.clear()
    c = TestClient(api_mod.app)
    yield c
    api_mod._JOBS.clear()
