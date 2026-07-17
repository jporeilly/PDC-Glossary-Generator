"""Docs/version consistency — the drift guard that caught Policy shipping
VERSION 1.6.0 while its README said 1.5.4. The single source of truth is
glossary_generator/VERSION (what /api/version serves); every human-facing
stamp must agree with it."""
import os
import re

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(APP_DIR)


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def test_required_docs_exist():
    for p in ("README.md", os.path.join("docs", "CHANGELOG.md"),
              os.path.join("docs", "GUIDE.md"),
              os.path.join("glossary_generator", "VERSION"),
              os.path.join("glossary_generator", "README.md")):
        assert os.path.exists(os.path.join(REPO, p)), f"missing {p}"


def test_version_markers_agree():
    version = _read(APP_DIR, "VERSION").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version

    # the running app serves exactly this version
    import api
    assert api.APP_VERSION == version

    # newest changelog entry (docs/CHANGELOG.md is what /api/whatsnew reads)
    m = re.search(r"^## \[([^\]]+)\]", _read(REPO, "docs", "CHANGELOG.md"), re.M)
    assert m and m.group(1) == version, \
        f"docs/CHANGELOG.md top entry {m and m.group(1)} != VERSION {version}"

    # the repo README's version stamp
    m = re.search(r"\*\*Version:\*\*\s*([0-9][^\s·]*)", _read(REPO, "README.md"))
    assert m and m.group(1) == version, \
        f"README.md **Version:** {m and m.group(1)} != VERSION {version}"


def test_readme_reflects_fastapi_port():
    """The README must not describe the removed Flask entry point."""
    text = _read(REPO, "README.md")
    assert "app.py" not in text, "README still references the removed Flask app.py"
