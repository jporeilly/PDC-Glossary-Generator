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
        "Under the hood — bulk-loading data sources (PDC Public API)",
        "Under the hood — reading PDC's catalog",
    ],
    # moved with the connection cards when Connect went PDC-only — the
    # explainers live where the buttons they explain now live
    "../components/SourceConnections.jsx": [
        "Connection types &amp; what each button does",
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
    # 1.38.26 evidence refresh: overwrite is opt-in, and the steward's
    # Detection_Intent flips are NEVER refresh targets — the field stays
    # fill-only in every mode (the 70 flips must survive a rescaled estate)
    assert "refreshEvidence" in rm
    assert "stays fill-only in EVERY mode" in rm
    # 1.38.17: the landing moved into state.js (landScanRows) so the empty-
    # grid guard wraps EVERY scan/harvest landing — Connect and the source
    # connections delegate to it, and the source-identity merge lives behind it
    st = _read(os.path.join(base, "state.js"))
    assert "mergeBySource" in st and "landScanRows" in st, \
        "state.js must own the guarded landing over the source-identity merge"
    cp = _read(os.path.join(base, "pages", "ConnectPage.jsx"))
    assert "landScanRows" in cp, "Connect's harvest must land through the guarded merge"
    assert "rowKey" not in cp, "the Category|Term row key must not survive"
    sc = _read(os.path.join(base, "components", "SourceConnections.jsx"))
    assert "landScanRows" in sc, "direct scans must land through the guarded merge"
    rv = _read(os.path.join(base, "pages", "ReviewPage.jsx"))
    assert "selfFold" in rv and "SILENT auto-heal" in rv, \
        "Review must heal old-key damage behind the scenes"
    assert "Fold same-source rows" not in rv, \
        "the heal is never exposed to the steward as a decision"


def test_proposed_categories_are_chips_on_the_banner():
    """The categorize banner says "settle the set, rename any group" - but
       the proposed subjects were only visible by scrolling the grid reading
       pills, and a rename meant editing pills row by row (field: "it would
       be great to see the list of proposed Categories without having to
       scroll. this list could be editable."). Pin the affordance: the banner
       groups the pending Category pills into editable chips, a chip renames
       its whole group (merging onto an existing name), a group can be
       dismissed alone, and both rewrites go through commitProposals so
       pendingCats and the Approve button recount live."""
    path = os.path.join(REPO, "frontend", "src", "pages", "ReviewPage.jsx")
    if not os.path.isfile(path):
        return                     # backend-only checkout
    src = _read(path)
    assert "renameProposedCat" in src and "dismissProposedCat" in src
    assert "rv-catchip" in src, "the chip strip must render on the proposal banner"
    for fn in ("renameProposedCat", "dismissProposedCat"):
        body = src.split("function %s" % fn)[1].split("\n  }")[0]
        assert "commitProposals" in body, \
            "%s must rewrite pills via commitProposals so the edit persists" % fn
    css = _read(os.path.join(REPO, "frontend", "src", "pages", "review.css"))
    assert ".rv-catchip" in css


def test_wholesale_accept_is_categorize_only():
    """Accept all rubber-stamps a whole AI-pass run, but that run is the
       steward's to review pill by pill (field: "dont need accept dimiss all
       as the data steward has to go through every pill."). Pin the split:
       the wholesale pair renders ONLY behind the categorize gate (accepting
       a settled taxonomy is one deliberate act — the chips exist to settle
       it first); every other agent's banner offers a discard-only Dismiss
       rest, which clears leftovers and can never apply a change."""
    path = os.path.join(REPO, "frontend", "src", "pages", "ReviewPage.jsx")
    if not os.path.isfile(path):
        return                     # backend-only checkout
    src = _read(path)
    assert "const wholesale = proposals.label === 'AI categories (schema)'" in src
    assert src.count("onClick={acceptAllProps}") == 1, \
        "Accept all must render exactly once, inside the wholesale branch"
    assert "Dismiss rest" in src
    assert "never applies anything" in src, \
        "Dismiss rest must say outright that it cannot apply changes"


def test_the_keystone_is_wired_through_the_workspace():
    """"Confirm categories" is the steward's explicit "the taxonomy is
       settled" - the keystone everything downstream keys off (Dictionary
       syncs at confirm, Govern reads it instead of guessing, drift makes the
       button actionable again). Pin the wiring: the state carries it through
       save/load, Review offers it, Govern consults it."""
    base = os.path.join(REPO, "frontend", "src")
    if not os.path.isdir(base):
        return                  # backend-only checkout
    st = _read(os.path.join(base, "state.js"))
    assert "setCategoriesConfirmed" in st
    assert st.count("categories_confirmed") >= 3, \
        "the keystone must survive save, sendBeacon-save and load"
    rv = _read(os.path.join(base, "pages", "ReviewPage.jsx"))
    assert "Approve categories" in rv and "setCategoriesConfirmed" in rv
    assert "/api/tagdict/sync" in rv, "approving must sync the Dictionary immediately"
    assert "Review complete" in rv and "setReviewCompleted" in rv,         "the Review stage must close with one deliberate, syncing act"
    assert st.count("review_completed") >= 3,         "review completion must survive save, sendBeacon-save and load"
    gv = _read(os.path.join(base, "pages", "GovernPage.jsx"))
    assert "categoriesConfirmed" in gv, \
        "Govern must consult the keystone instead of guessing"


def test_refresh_evidence_replaces_the_observation_whole():
    """A refresh must clear evidence the fresh scan no longer sees.

    Field-caught on the AWC clean run (2026-08-21). The seeder had filled
    twelve columns with one code shape; after the estate was repaired those
    columns held words, so the rescan induced an ENUM and no pattern at all.
    The merge was field-wise and guarded on `nr[f] &&`, so the incoming BLANK
    could not overwrite - and ^[A-Z]{2}[0-9]{4}$ survived on County, Severity,
    System Type, Source Type, Primary Source, Conservation Focus, Service
    County and Contaminant Level, next to a fresh, correct enum.

    Those patterns matched zero rows. Deployed as Data Patterns they would
    have reported success and never fired - the same silent shape as the
    numeric threshold and the stale profile before them. In refresh mode the
    fresh observation now replaces the whole evidence set, blanks included; a
    scan that saw nothing at all still never erases.
    """
    path = os.path.join(REPO, "frontend", "src", "rowmerge.js")
    if not os.path.isfile(path):
        return                     # frontend is optional for a backend-only checkout
    src = _read(path)
    assert "if (nr[f] && (refreshEvidence || !next[f])) next[f] = nr[f]" not in src, \
        "field-wise refresh is back: an incoming blank cannot clear a stale pattern"
    assert "mergeEvidence(next, nr, refreshEvidence ? REFRESH : CAPTURE)" in src, \
        "the row merge must go through the shared rule, not re-decide it inline"


def test_the_two_evidence_mirrors_agree():
    """evidence.py and evidence.js are the same rule written twice - rows are
    merged in the browser, the dictionary in Python - so they are pinned to
    the same field list and the same two modes. Three defects in one day came
    from each site deciding capture-vs-refresh for itself; the point of the
    shared module is that a fourth store cannot get it wrong, and the point of
    this test is that the two copies cannot drift apart.
    """
    import re
    py = _read(APP_DIR, "engine", "evidence.py")
    js_path = os.path.join(REPO, "frontend", "src", "evidence.js")
    if not os.path.isfile(js_path):
        return                     # frontend is optional for a backend-only checkout
    js = _read(js_path)

    def fields(text, marker):
        m = re.search(marker + r"\s*=\s*[\(\[](.*?)[\)\]]", text, re.S)
        assert m, f"{marker} not found"
        return [x.strip("'\" \n") for x in m.group(1).split(",") if x.strip()]

    assert fields(py, "EVIDENCE_FIELDS") == fields(js, "EVIDENCE_FIELDS"), \
        "the two evidence mirrors disagree about which fields travel together"
    for mode in ("capture", "refresh"):
        assert f'"{mode}"' in py and f"'{mode}'" in js, \
            f"mode {mode} missing from one of the mirrors"


def test_shipped_packs_carry_no_mangled_singulars():
    """A pack's table_terms are TERM NAMES: they reach PDC and a customer sees
    them. The singulariser used to strip the final "s" from any word not ending
    "ss", so `system_water_quality_status` became "System Water Quality Statu
    Record" — and because the pack STORES the name, the lookup then returned
    the mangled form faithfully, long after the generator was fixed. Shipped
    2026-08-21 into a customer-facing glossary.
    """
    import glob
    import json
    import re
    bad_word = re.compile(r"\b(?:Statu|Analysi|Basi|Axi|Diagnosi|Serie|Specie|"
                          r"Censu|Bonu|Radiu|Alia|Len|New)\b")
    packs = glob.glob(os.path.join(APP_DIR, "domain_packs", "*.json"))
    assert packs, "no domain packs found - has the path moved?"
    for path in packs:
        with open(path, encoding="utf-8") as f:
            try:
                pack = json.load(f)
            except ValueError:
                continue
        for key in ("table_terms", "terms", "table_category"):
            for k, v in (pack.get(key) or {}).items():
                for text in (k, v) if isinstance(v, str) else (k,):
                    m = bad_word.search(str(text))
                    assert not m, (f"{os.path.basename(path)} {key}[{k!r}] carries "
                                   f"a mangled singular: {text!r}")
