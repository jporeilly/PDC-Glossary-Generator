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


def test_desktop_installer_version_matches():
    """tauri.conf.json's version NAMES the built installer. Drift there ships a
       file whose filename misstates what is inside it, which is the one kind of
       version mistake a user cannot check."""
    import json
    conf = os.path.join(REPO, "desktop", "src-tauri", "tauri.conf.json")
    if not os.path.isfile(conf):
        return  # desktop shell is optional; nothing to check
    with open(conf, encoding="utf-8") as f:
        version = _read(APP_DIR, "VERSION").strip()
        assert json.load(f)["version"] == version, \
            f"desktop/src-tauri/tauri.conf.json version != VERSION {version}"


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
    readme = _read(REPO, "README.md")
    m = re.search(r"\*\*Version:\*\*\s*([0-9][^\s·]*)", readme)
    assert m and m.group(1) == version, \
        f"README.md **Version:** {m and m.group(1)} != VERSION {version}"

    # …and its shields.io version badge (a second stamp = a second way to drift)
    m = re.search(r"img\.shields\.io/badge/version-([0-9][^-]*)-", readme)
    assert m and m.group(1) == version, \
        f"README.md version badge {m and m.group(1)} != VERSION {version}"


def test_build_manifest_versions_agree():
    """The build manifests must state the version the build actually is.

    These three drifted unnoticed - frontend/package.json stuck at 1.24.0 and
    both desktop manifests at 0.1.0 while the app shipped 1.36.3 - because
    nothing reads them at runtime, so nothing contradicted them. That is
    exactly why they need a test rather than vigilance: a tree that gives four
    different answers about its own version cannot be read with confidence,
    and the reader has no way to tell which answer is the true one.
    """
    import json
    version = _read(APP_DIR, "VERSION").strip()

    for rel in (("frontend", "package.json"), ("desktop", "package.json")):
        path = os.path.join(REPO, *rel)
        if not os.path.isfile(path):
            continue  # neither is required for the Python app to run
        with open(path, encoding="utf-8") as f:
            got = json.load(f).get("version")
        assert got == version, \
            f"{'/'.join(rel)} version {got} != VERSION {version}"

    # Cargo's own [package] version. Dependency versions are inline tables
    # ({ version = "2.0" }), so anchoring to line start picks out only ours.
    cargo = os.path.join(REPO, "desktop", "src-tauri", "Cargo.toml")
    if os.path.isfile(cargo):
        m = re.search(r'^version\s*=\s*"([^"]+)"', _read(cargo), re.M)
        assert m and m.group(1) == version, \
            f"Cargo.toml version {m and m.group(1)} != VERSION {version}"


def test_readme_reflects_fastapi_port():
    """The README must not describe the removed Flask entry point."""
    text = _read(REPO, "README.md")
    assert "app.py" not in text, "README still references the removed Flask app.py"
