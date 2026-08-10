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


# The "Under the hood" explainers, per page. These are teaching material and the
# main reason the app is usable in a workshop: the learner reads what it will do
# to their systems before it does it.
#
# They need a test because of HOW they were lost. Removing the legacy Jinja UI at
# 1.35.0 deleted 12 of them in one commit - nothing referenced them, no test
# covered them, and the loss surfaced only when someone went looking weeks later.
# A page can lose its explainer without a single error being raised, so the list
# is pinned here and grows as the remaining panels are ported back.
EXPLAINERS = {
    "ConnectPage.jsx": [
        "Connection types &amp; what each button does",
        "Under the hood — bulk-loading data sources (PDC Public API)",
        "Under the hood — reading PDC's catalog",
        "Under the hood — what a database scan runs",
    ],
    "FilesPage.jsx": [
        "Under the hood — browsing the object store (S3 API)",
    ],
    "ReviewPage.jsx": [
        "How terms are defined &amp; built",
        "Under the hood — this page's calls",
    ],
    "GovernPage.jsx": [
        "Under the hood — fetching the roster from Keycloak",
    ],
    "ApplyPage.jsx": [
        "Under the hood — generating the JSONL",
        "Under the hood — the PDC API calls this makes",
    ],
    "DictionaryPage.jsx": [
        "Under the hood — the governed vocabulary API",
        "Under the hood — the pack flywheel: whose scan feeds the pack?",
    ],
}

# The transparency viewer lives in a component rather than a page. It is listed
# separately because it is the one panel that serves the code itself, and it was
# orphaned for a full release - live, tested server-side, and called by nothing.
VIEWER = ("SourceViewer.jsx", "Under the hood — read the source that runs")


def test_explainer_panels_are_present():
    import re
    for page, wanted in EXPLAINERS.items():
        path = os.path.join(REPO, "frontend", "src", "pages", page)
        if not os.path.isfile(path):
            continue           # frontend is optional for a backend-only checkout
        src = _read(path)
        summaries = " || ".join(re.findall(r"<summary[^>]*>(.*?)</summary>", src, re.S))
        for title in wanted:
            assert title in summaries, f"{page} lost its explainer: {title!r}"


def test_the_source_viewer_is_wired_to_a_page():
    """/api/source is served and server-side tested. It spent a release orphaned
       because nothing in the UI called it, so the wiring is pinned too."""
    import glob
    comp = os.path.join(REPO, "frontend", "src", "components", VIEWER[0])
    if not os.path.isfile(comp):
        return
    assert VIEWER[1] in _read(comp)
    assert "/api/source" in _read(comp), "the viewer must actually call the endpoint"
    pages = glob.glob(os.path.join(REPO, "frontend", "src", "pages", "*.jsx"))
    assert any("SourceViewer" in _read(p) for p in pages),         "SourceViewer is not rendered by any page - the viewer is orphaned again"


def test_readme_reflects_fastapi_port():
    """The README must not describe the removed Flask entry point."""
    text = _read(REPO, "README.md")
    assert "app.py" not in text, "README still references the removed Flask app.py"


def test_llm_chip_provenance_stays_per_field():
    """Accepting ONE field must not light the other field's LLM chip.
       Through 1.36.32 every accept carried row-level LLM_Enriched, and the
       chips' legacy fallback then lit Purpose the moment a Definition was
       accepted (field-caught). The carry list stays per-field, and the chips
       go through llmChip, whose fallback is reserved for rows with NO
       per-field flag at all - true legacy saves."""
    import re
    path = os.path.join(REPO, "frontend", "src", "pages", "ReviewPage.jsx")
    if not os.path.isfile(path):
        return                     # frontend is optional for a backend-only checkout
    src = _read(path)
    m = re.search(r"const CARRY_FOR = \{(.*?)\n\}", src, re.S)
    assert m, "CARRY_FOR must exist - it is how accepts carry provenance"
    assert "LLM_Enriched" not in m.group(1), \
        "row-level LLM_Enriched in CARRY_FOR lights chips on unaccepted fields"
    assert "llmChip(r, 'LLM_Definition')" in src and "llmChip(r, 'LLM_Purpose')" in src, \
        "field chips must go through llmChip so the legacy fallback stays scoped"
    assert "delete patch.LLM_Enriched" in src, \
        "the whole-row accept must strip the legacy flag too"


def test_row_identity_is_evidence_not_labels():
    """133 kept became 248: rows merged on the Category|Term key, the steward
       renamed exactly those fields, and a re-ingestion appended the whole
       estate again (field-caught on the fresh-install exam). Identity must
       come from source columns - the one thing steward edits never change.
       Pin the shape: the shared merge module exists, Connect delegates to it,
       Review carries the repair, and no Category|Term row key survives."""
    base = os.path.join(REPO, "frontend", "src")
    if not os.path.isfile(os.path.join(base, "rowmerge.js")):
        if not os.path.isdir(base):
            return              # backend-only checkout
        raise AssertionError("rowmerge.js must exist - row identity lives there")
    rm = _read(os.path.join(base, "rowmerge.js"))
    assert "IDENTITY IS EVIDENCE, NOT LABELS" in rm
    assert "mergeBySource" in rm and "selfFold" in rm and "sameSourceCount" in rm
    cp = _read(os.path.join(base, "pages", "ConnectPage.jsx"))
    assert "mergeBySource" in cp, "Connect's workspace merge must use source identity"
    assert "rowKey" not in cp, "the Category|Term row key must not survive"
    rv = _read(os.path.join(base, "pages", "ReviewPage.jsx"))
    assert "selfFold" in rv and "SILENT auto-heal" in rv, \
        "Review must heal old-key damage behind the scenes"
    assert "Fold same-source rows" not in rv, \
        "the heal is never exposed to the steward as a decision"
