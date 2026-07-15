"""
selftest.py — offline checks for the app's own logic (no PDC, no Ollama, no
network). The PDC API *shapes* live in v3_selftest.py; THIS file covers the
engine modules and the endpoints that run without a catalog:

    python selftest.py            (from glossary_generator/)

Run it after a pull on the VM: green means the build is sane before you
touch PDC. Everything runs against a throw-away dictionary/pack in a temp
dir — your installed scenario config is never read or written.
"""
from __future__ import annotations
import io, json, os, sys, tempfile, zipfile

# isolate ALL persisted state before any app import — the suite must never
# read or write the installed scenario config, settings or saved glossaries
_TD = tempfile.mkdtemp(prefix="glossary-selftest-")
for _var, _name in [("GLOSSARY_TAG_DICTIONARY", "tag_dictionary.json"),
                    ("GLOSSARY_DOMAIN_PACK", "domain_pack.json"),  # absent -> built-in defaults
                    ("GLOSSARY_SETTINGS", "settings.json"),
                    ("GLOSSARY_CONNECTIONS", "connections.json"),
                    ("GLOSSARY_GLOSSARIES", "glossaries.json"),
                    ("GLOSSARY_PEOPLE", "people.json"),
                    ("GLOSSARY_AUDIT_LOG", "audit_log.json")]:
    os.environ[_var] = os.path.join(_TD, _name)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tagdict, packgen, similarity, defqa, policy_draft, llm  # noqa: E402

PASS = FAIL = 0


def _c(name, ok, detail=""):
    global PASS, FAIL
    print(("  [ok  ] " if ok else "  [FAIL] ") + name + ((" -- %s" % (detail,)) if detail and not ok else ""))
    PASS += ok
    FAIL += not ok


def _row(term, col, **kw):
    r = {"Term": term, "Source_Column": col, "Keep": "Y", "Definition": "d.",
         "Category": "Customer", "Sensitivity": "LOW", "Suggested_Tags": ""}
    r.update(kw)
    return r


def main():
    print("glossary_generator selftest (offline)")

    # ---- version discipline: VERSION file matches the changelog head ---------
    print("version")
    with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
        ver = f.read().strip()
    chlog = os.path.join(HERE, "..", "docs", "CHANGELOG.md")
    if os.path.exists(chlog):
        import re
        with open(chlog, encoding="utf-8") as f:
            m = re.search(r"^## \[([^\]]+)\]", f.read(), re.M)
        _c("VERSION (%s) is the changelog's top entry" % ver, m and m.group(1) == ver,
           m and m.group(1))
    else:
        print("  [skip] docs/CHANGELOG.md not shipped in this build")

    # ---- tagdict: lowercase governance + steward lifecycle -------------------
    print("tagdict")
    _c("tags normalize lowercase", tagdict.norm_tag("PII") == "pii")
    tagdict.accrete([_row("Member Number", "cscu_core.members.mbr_no",
                          Suggested_Tags="PII;Identifier", Sensitivity="HIGH"),
                     _row("Column_3", "cscu_core.members.column_3")], persist=True)
    d = tagdict.load()
    _c("junk terms (column_N) blocked at accrete", "Column_3" not in d.get("terms", {}))
    _c("accreted term lands pending",
       (d["terms"].get("Member Number") or {}).get("status") == "pending")
    _c("accreted tags healed lowercase",
       set((d["terms"]["Member Number"].get("tags") or [])) >= {"pii", "identifier"},
       d["terms"]["Member Number"].get("tags"))
    _c("pending does not govern", "Member Number" not in tagdict.governed_terms())
    tagdict.review("term", ["Member Number"], "approve")
    _c("approve -> governs", "Member Number" in tagdict.governed_terms())
    tagdict.accrete([_row("Mbr No", "cscu_core.cards.mbr_no", Sensitivity="HIGH")], persist=True)
    tagdict.review("term", ["Mbr No"], "alias", target="Member Number")
    d = tagdict.load()
    _c("alias action folds pending into the canonical term",
       "Mbr No" in (d["terms"]["Member Number"].get("aliases") or [])
       and "Mbr No" not in d["terms"])
    _c("alias_index resolves the folded name",
       tagdict.alias_index().get("mbr no") == "Member Number", tagdict.alias_index().get("mbr no"))
    tagdict.accrete([_row("Scan Noise", "cscu_core.x.noise")], persist=True)
    tagdict.reset(preserve_approved=True)
    d = tagdict.load()
    _c("reset keeps approved, drops pending",
       (d["terms"].get("Member Number") or {}).get("status") == "approved"
       and "Scan Noise" not in d["terms"])
    _c("lift_sensitivity tightens via term dictionary, never loosens",
       tagdict.lift_sensitivity("LOW", [], term="Member Number") == "HIGH"
       and tagdict.lift_sensitivity("HIGH", [], term=None) == "HIGH")
    # pack-seeded vocabulary is company/approved and STAYS so across loads
    # (regression: _merge_seed relabeled every pack term generic on load,
    # which locked the whole curated vocabulary out of steward actions)
    with open(os.environ["GLOSSARY_DOMAIN_PACK"], "w", encoding="utf-8") as f:
        json.dump({"domain": "credit_union", "extra_tags": ["pci"],
                   "terms": {"Card Number": {"aliases": ["PAN"], "sensitivity": "HIGH",
                                             "tags": ["pci"]}}}, f)
    tagdict.reset(preserve_approved=True)
    m = (tagdict.load().get("terms") or {}).get("Card Number") or {}
    _c("pack term seeds company/approved and survives the load-merge",
       m.get("layer") == "company" and m.get("status") == "approved", m)
    _c("pack term is reachable by steward actions (not locked as generic)",
       tagdict.review("term", ["Card Number"], "approve") == 0  # already approved
       and tagdict.review("term", ["Card Number"], "reject") == 1)
    tagdict.reset(preserve_approved=True)  # reseed restores the curated term

    # ---- similarity: the duplicate advisor's evidence rubric -----------------
    print("similarity")
    a = _row("State", "geo.addresses.state_cd", Enum_Values="AZ;CA;NV;UT")
    b = _row("State", "hr.employees.state_cd", Enum_Values="AZ;CA;NV")
    c = _row("State", "wf.tickets.state_cd", Enum_Values="OPEN;CLOSED;PENDING")
    v, _ = similarity.compare_evidence(a, b)
    _c("overlapping profiled enums -> same", v == "same", v)
    v, _ = similarity.compare_evidence(a, c)
    _c("disjoint profiled enums -> different", v == "different", v)
    fk_child = _row("Member Number", "cscu_core.cards.mbr_no",
                    Source_Keys={"cscu_core.cards.mbr_no": {"pk": False, "fk": True,
                                                            "ref": "members.mbr_no"}})
    fk_parent = _row("Member Number", "cscu_core.members.mbr_no")
    v, why = similarity.compare_evidence(fk_child, fk_parent)
    _c("FK link -> same by construction", v == "same", why)
    v, _ = similarity.compare_evidence(_row("Id", "s.t1.c", Value_Pattern=r"^A\d{3}$"),
                                       _row("Id", "s.t2.c", Value_Pattern=r"^B\d{6}$"))
    _c("different induced formats -> different", v == "different", v)
    v, _ = similarity.compare_value_sets(["a", "b", "c"], ["A", "B", "c", "d", "e"])
    _c("live probe containment >= 0.6 -> same", v == "same", v)
    r = similarity.recommend_resolution([a, b])
    _c("advisor: evidence-same -> merge/high",
       r["action"] == "merge" and r["band"] == "high", r)
    r = similarity.recommend_resolution([a, c])  # same category, disjoint enums
    _c("advisor: different in one category -> split/high (import collides)",
       r["action"] == "split" and r["band"] == "high", r)
    c2 = dict(c, Category="Operations")
    r = similarity.recommend_resolution([a, c2])
    _c("advisor: different across categories -> separate/high",
       r["action"] == "separate" and r["band"] == "high", r)

    # ---- defqa: the deterministic definition linter ---------------------------
    print("defqa")
    rows = [_row("APR Rate", "s.loans.apr", Definition="Annual percentage rate as a decimal. Regulation Z disclosure value."),
            _row("Memo", "s.tx.memo", Definition="Memo."),
            _row("Member Number", "s.m.no", Definition="The member number of the member."),
            _row("Fee Code", "s.f.c", Definition="Data about fees and other information.")]
    issues = defqa.lint_rows(rows)
    _c("clean definition passes", 0 not in issues, issues.get(0))
    _c("too-short flagged", any("short" in x for x in issues.get(1, [])), issues.get(1))
    _c("circular flagged", any("circular" in x for x in issues.get(2, [])), issues.get(2))
    _c("vague opener flagged", any("vague" in x for x in issues.get(3, [])), issues.get(3))

    # ---- packgen: the pack flywheel's merge ------------------------------------
    print("packgen")
    _c("abbreviation alignment (mbr_no + Member Number)",
       similarity is not None and packgen._abbrev_pairs("mbr_no", "Member Number") == [("mbr", "Member")])
    _c("non-abbreviations rejected",
       packgen._abbrev_pairs("state", "State") == [] and packgen._abbrev_pairs("x", "Long Name") == [])
    scan = [_row("Member Number", "cscu_core.members.mbr_no", Category="Customer",
                 Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn"),
            _row("Member Name", "cscu_core.members.full_nm", Category="Customer")]
    base = {"table_category": {"members": "Membership"},
            "curated_seeds": {"Member Number": {"type": "pattern", "regex": r"^\d{6}$",
                                                "signature": None}},
            "terms": {"Member Number": {"aliases": ["Member ID"], "sensitivity": "LOW",
                                        "tags": ["member"]}}}
    pack, rep = packgen.build_pack(scan, base=dict(base))
    conf = {(x["key"], x["name"]): x for x in rep["conflicts"]}
    _c("scalar conflict default: pack (curation) wins",
       pack["table_category"]["members"] == "Membership"
       and conf[("table_category", "members")]["use"] == "pack")
    _c("curated_seeds default: fresher scan evidence wins",
       pack["curated_seeds"]["Member Number"]["regex"] == r"^CSCU-\d{6}$"
       and conf[("curated_seeds", "Member Number")]["use"] == "scan")
    t = pack["terms"]["Member Number"]
    _c("terms safe-union: aliases/tags union, sensitivity tightens",
       "Member ID" in t["aliases"] and "Mbr No" in t["aliases"]
       and "pii" in t["tags"] and t["sensitivity"] == "HIGH", t)
    pack2, _ = packgen.build_pack(scan, base=dict(base),
                                  resolutions={"table_category::members": "scan",
                                               "curated_seeds::Member Number": "pack"})
    _c("resolutions flip both defaults",
       pack2["table_category"]["members"] == "Customer"
       and pack2["curated_seeds"]["Member Number"]["regex"] == r"^\d{6}$")
    base3 = {"terms": {"X High": {"aliases": [], "sensitivity": "HIGH", "tags": []}}}
    tagdict.accrete([_row("X High", "s.t.x")], persist=True)  # accretes at LOW
    tagdict.review("term", ["X High"], "approve")
    pack3, rep3 = packgen.build_pack([], base=base3)
    _c("sensitivity loosening blocked by default AND reported as a conflict",
       pack3["terms"]["X High"]["sensitivity"] == "HIGH"
       and any(x["key"] == "terms.sensitivity" and x["name"] == "X High"
               for x in rep3["conflicts"]), rep3["conflicts"])

    # ---- policy_draft: seeds -> importable methods, guard-railed --------------
    print("policy_draft")
    rows = [_row("Member Number", "cscu_core.members.mbr_no",
                 Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn",
                 Suggested_Tags="pii;identifier"),
            _row("Risk Rating", "cscu_core.kyc.risk_cd", Enum_Values="LOW;MEDIUM;HIGH",
                 Suggested_Tags="compliance"),
            _row("SSN", "cscu_core.members.ssn", PII_Category="GOVERNMENT_ID"),
            _row("Memo Text", "cscu_core.tx.memo_txt")]
    art = policy_draft.draft_from_rows(rows, prefix="CSCU",
                                       hints={"Member Number": {"column_regex": "([bad",
                                                                "tags": ["pii", "rogue-tag"]}},
                                       governed_tags=["pii", "identifier", "compliance"])
    _c("profiled pattern + canonical SSN -> 2 patterns",
       len(art["patterns"]) == 2 and {p["seed"] for p in art["patterns"]} == {"profiled", "canonical"},
       [(p["term"], p["seed"]) for p in art["patterns"]])
    _c("enum row -> dictionary with csv values",
       len(art["dictionaries"]) == 1 and "LOW" in art["dictionaries"][0]["csv"])
    _c("seedless free-text row skipped with a reason",
       any(s["term"] == "Memo Text" for s in art["skipped"]), art["skipped"])
    mn = [p for p in art["patterns"] if p["term"] == "Member Number"][0]
    blob = json.dumps(mn["rule"])
    _c("AI hints guard-railed: invalid column regex rejected, off-gov tag filtered",
       "([bad" not in blob and "rogue-tag" not in blob and '"pii"' in blob)
    z = zipfile.ZipFile(io.BytesIO(policy_draft.to_zip_bytes(art)))
    _c("draft zips into an import bundle", len(z.namelist()) >= 3, z.namelist())

    # ---- llm guard-rails (no model needed) -------------------------------------
    print("llm")
    _c("_mostly_english accepts English",
       llm._mostly_english("The member's unique account identifier."))
    _c("_mostly_english rejects CJK drift",
       not llm._mostly_english("成员的唯一标识符。"))

    # ---- app endpoints that run offline ----------------------------------------
    print("app (offline endpoints)")
    from app import app, APP_VERSION
    tc = app.test_client()
    _c("/ renders", tc.get("/").status_code == 200)
    _c("/api/version == VERSION file",
       tc.get("/api/version").get_json().get("version") == ver == APP_VERSION)
    wn = tc.get("/api/whatsnew").get_json()
    if os.path.exists(chlog):
        _c("/api/whatsnew top release matches the running version",
           wn["releases"] and wn["releases"][0]["version"] == APP_VERSION,
           wn["releases"][0]["version"] if wn["releases"] else "none")
    ep = tc.post("/api/export-pack", json={"rows": scan}).get_json()
    _c("/api/export-pack returns pack + conflict-aware report",
       isinstance(ep.get("pack"), dict) and "conflicts" in ep.get("report", {}))
    ar = tc.post("/api/tagdict/ai-review", json={"names": ["no-such-term"]}).get_json()
    _c("/api/tagdict/ai-review names filter scopes the pass", ar.get("pending") == 0, ar)
    snap = zipfile.ZipFile(io.BytesIO(tc.get("/api/state-snapshot").data))
    mani = json.loads(snap.read("manifest.json"))
    _c("state snapshot carries the dictionary + a versioned manifest",
       "tag_dictionary.json" in snap.namelist() and mani.get("app_version") == APP_VERSION,
       snap.namelist())
    # round-trip: snapshot -> mutate state -> restore -> state reverted
    tagdict.accrete([_row("Snapshot Marker", "s.t.snapmark")], persist=True)
    snap2 = tc.get("/api/state-snapshot").data           # contains the marker
    tagdict.review("term", ["Snapshot Marker"], "reject")
    rr = tc.post("/api/state-restore", data=snap2).get_json()
    _c("state restore round-trips the dictionary (backup taken)",
       "Snapshot Marker" in tagdict.load().get("terms", {})
       and "tag_dictionary.json" in rr.get("restored", []) and rr.get("backed_up", 0) >= 1, rr)
    bad = tc.post("/api/state-restore", data=b"not a zip")
    _c("state restore rejects non-zip input", bad.status_code == 400)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
