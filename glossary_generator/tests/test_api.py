"""The FastAPI layer via TestClient — ports the old selftest.py endpoint
checks and covers the port's contract guarantees: {'error': ...} payloads,
streaming shells, and the additive /api/jobs/* start/poll pattern."""
import io
import json
import os
import time
import zipfile

import pytest

from conftest import make_row as _row

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_ROWS = [_row("Member Number", "cscu_core.members.mbr_no", Category="Customer",
                  Value_Pattern=r"^CSCU-\d{6}$", Value_Signature="AAAA-nnnnnn"),
             _row("Member Name", "cscu_core.members.full_nm", Category="Customer")]


class TestCore:
    def test_index_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]

    def test_version_matches_version_file(self, client):
        import api
        with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as f:
            ver = f.read().strip()
        body = client.get("/api/version").json()
        assert body["version"] == ver == api.APP_VERSION

    def test_whatsnew_top_release_matches_running_version(self, client):
        import api
        chlog = os.path.join(APP_DIR, "..", "docs", "CHANGELOG.md")
        wn = client.get("/api/whatsnew").json()
        if os.path.exists(chlog):
            assert wn["releases"] and wn["releases"][0]["version"] == api.APP_VERSION
        else:
            assert wn["releases"] == []

    def test_health_and_docs(self, client):
        h = client.get("/health").json()
        assert h["status"] == "ok" and h["service"] == "glossary-suggester"
        assert client.get("/docs").status_code == 200, "Swagger UI serves"
        assert client.get("/openapi.json").status_code == 200

    def test_error_contract_shape(self, client):
        """Errors must be {'error': msg} — the UI checks data.error, never
        FastAPI's default {'detail': ...}."""
        r = client.get("/api/glossaries/no-such-id")
        assert r.status_code == 404 and r.json() == {"error": "not found"}
        r = client.post("/api/tagdict/review", json={"kind": "bogus", "names": ["x"]})
        assert r.status_code == 400 and "error" in r.json()

    def test_detect_report_shape(self, client):
        d = client.get("/api/detect").json()
        assert {"platform", "ollama", "recommendation"} <= set(d)
        assert d["recommendation"]["model"]


class TestScanPipeline:
    DDL = ("CREATE TABLE members (\n"
           "  mbr_no INT PRIMARY KEY,\n"
           "  full_nm VARCHAR(80),\n"
           "  ssn VARCHAR(11)\n"
           ");\n"
           "CREATE TABLE cards (\n"
           "  card_id INT PRIMARY KEY,\n"
           "  mbr_no INT REFERENCES members(mbr_no)\n"
           ");")

    def test_scan_ddl_text_to_rows(self, client):
        body = client.post("/api/scan", json={"ddl_text": self.DDL}).json()
        assert body["scanned"]["tables"] == 2 and body["rows"]
        assert body["stats"]["terms"] == len(body["rows"])

    def test_schema_graph(self, client):
        g = client.post("/api/schema", json={"ddl_text": self.DDL}).json()
        assert g["schema_name"] == "ddl" and g.get("tables")

    def test_generate_jsonl_and_registry(self, client):
        scan = client.post("/api/scan", json={"ddl_text": self.DDL}).json()
        out = client.post("/api/generate",
                          json={"rows": scan["rows"], "glossary_name": "T Glossary"}).json()
        assert out["jsonl"].strip() and out["stats"]["terms"] >= 1
        lines = [json.loads(x) for x in out["jsonl"].splitlines() if x.strip()]
        assert {x["type"] for x in lines} >= {"category", "term"}

    def test_data_elements_links(self, client):
        scan = client.post("/api/scan", json={"ddl_text": self.DDL}).json()
        out = client.post("/api/data-elements",
                          json={"rows": scan["rows"], "glossary_name": "T Glossary"}).json()
        assert out["count"] == len(out["links"]) and "csv" in out
        assert out["policy"]["mode"]


class TestStateAndGovernance:
    def test_export_pack_conflict_aware(self, client):
        ep = client.post("/api/export-pack", json={"rows": SCAN_ROWS}).json()
        assert isinstance(ep.get("pack"), dict) and "conflicts" in ep.get("report", {})

    def test_ai_review_names_filter(self, client):
        ar = client.post("/api/tagdict/ai-review", json={"names": ["no-such-term"]}).json()
        assert ar.get("pending") == 0

    def test_state_snapshot_restore_roundtrip(self, client, fresh_dict):
        import api
        tagdict = fresh_dict
        # the snapshot only zips files that exist — persist a dictionary first
        tagdict.accrete([_row("Seed Term", "s.t.seed")], persist=True)
        snap = zipfile.ZipFile(io.BytesIO(client.get("/api/state-snapshot").content))
        mani = json.loads(snap.read("manifest.json"))
        assert "tag_dictionary.json" in snap.namelist()
        assert mani.get("app_version") == api.APP_VERSION
        # round-trip: snapshot -> mutate state -> restore -> state reverted
        tagdict.accrete([_row("Snapshot Marker", "s.t.snapmark")], persist=True)
        snap2 = client.get("/api/state-snapshot").content        # contains the marker
        tagdict.review("term", ["Snapshot Marker"], "reject")
        rr = client.post("/api/state-restore", content=snap2).json()
        assert "Snapshot Marker" in tagdict.load().get("terms", {})
        assert "tag_dictionary.json" in rr.get("restored", [])
        assert rr.get("backed_up", 0) >= 1

    def test_state_restore_rejects_non_zip(self, client):
        bad = client.post("/api/state-restore", content=b"not a zip")
        assert bad.status_code == 400 and "error" in bad.json()

    def test_fold_advisor_expansion_twins(self, client, fresh_dict):
        tagdict = fresh_dict
        with open(os.environ["GLOSSARY_DOMAIN_PACK"], "w", encoding="utf-8") as f:
            json.dump({"domain": "credit_union", "abbreviations": {"mbr": "Member"}}, f)
        tagdict.accrete([_row("Mbr Rating", "s.m.mbr_rating"),
                         _row("Member Rating", "s.m.member_rating")], persist=True)
        tagdict.review("term", ["Mbr Rating", "Member Rating"], "approve")
        fa = client.post("/api/tagdict/fold-advisor", json={}).json()
        assert any(p["fold"] == "Mbr Rating" and p["keep"] == "Member Rating"
                   and p["confidence"] == "high" for p in fa.get("pairs", []))

    def test_governance_summary_cors(self, client):
        r = client.get("/api/governance-summary")
        assert r.headers.get("access-control-allow-origin") == "*"
        assert r.json()["schema"] == "governance-summary/1"

    def test_source_viewer_reaches_pdc_client(self, client):
        listing = client.get("/api/source").json()
        assert any(f["file"] == "pdc_api/core.py" for f in listing["files"])
        src = client.get("/api/source", params={"file": "pdc_api/core.py"}).json()
        assert "def" in src["content"] and src["lines"] > 50
        assert client.get("/api/source", params={"file": "settings.json"}).status_code == 404


class TestStreamingContracts:
    def test_resolve_terms_stream_error_event(self, client):
        """No base_url -> the SSE stream still opens and reports event: error
        (the old UI parses exactly this shape)."""
        r = client.post("/api/resolve-terms-stream", json={"json": []})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        assert "event: error" in r.text and "PDC base URL is required" in r.text

    def test_bulk_load_ndjson_dry_run(self, client):
        rows = [{"kind": "postgres", "resourceName": "T_DB", "host": "h", "port": "5432",
                 "databaseName": "d", "userName": "u", "password": "p", "schemaNames": "public"}]
        r = client.post("/api/pdc/bulk-load",
                        json={"base_url": "https://pdc.example", "rows": rows, "dry_run": True})
        events = [json.loads(x) for x in r.text.splitlines() if x.strip()]
        assert "application/x-ndjson" in r.headers["content-type"]
        assert events[0]["event"] == "start" and events[0]["dry_run"] is True
        assert events[-1]["event"] == "done"
        row_ev = [e for e in events if e["event"] == "row"][0]
        assert row_ev["result"]["create"] == "DRY"
        assert row_ev["body"].get("password") not in ("p",), "secrets redacted in dry-run echo"

    def test_cross_glossary_check_needs_a_host_but_not_a_round_trip(self, client):
        """The Review-time "already in PDC?" check. An empty name list must not
           reach the network: a steward with nothing kept yet should get an empty
           answer, not an auth error about a server they never meant to call."""
        r = client.post("/api/pdc/terms/existing", json={"names": ["Member Number"]})
        assert r.status_code == 400 and "base URL" in r.json()["error"]

        r = client.post("/api/pdc/terms/existing",
                        json={"base_url": "https://pdc.example", "names": []})
        assert r.status_code == 200
        assert r.json() == {"found": {}, "checked": 0, "hits": 0}

    def test_apply_stream_preflight_400(self, client):
        r = client.post("/api/apply-to-pdc-stream", json={"json": []})
        assert r.status_code == 400 and "error" in r.json()


class TestJobs:
    def _wait(self, client, job_id, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = client.get(f"/api/jobs/{job_id}").json()
            if st["status"] != "running":
                return st
            time.sleep(0.05)
        raise AssertionError("job did not finish in time")

    def test_unknown_job_404(self, client):
        r = client.get("/api/jobs/nope")
        assert r.status_code == 404 and "error" in r.json()

    def test_resolve_terms_job_error_path(self, client):
        job = client.post("/api/jobs/resolve-terms", json={"json": []}).json()
        st = self._wait(client, job["job"])
        assert st["status"] == "error" and "PDC base URL is required" in st["detail"]

    def test_bulk_load_job_dry_run(self, client):
        rows = [{"kind": "minio", "resourceName": "Docs", "endpoint": "http://m:9000",
                 "accessKey": "a", "secretKey": "s", "container": "docs", "path": "/"}]
        job = client.post("/api/jobs/bulk-load",
                          json={"base_url": "https://pdc.example", "rows": rows,
                                "dry_run": True}).json()
        st = self._wait(client, job["job"])
        assert st["status"] == "done"
        assert st["result"]["event"] == "done" and st["result"]["dry_run"] is True
        assert any(e.get("event") == "row" for e in st["events"])

    def test_pull_model_job_with_stubbed_stream(self, client, monkeypatch):
        from ai import llm
        def fake_pull(model=None):
            yield {"phase": "downloading", "status": "pulling", "completed": 50,
                   "total": 100, "percent": 50.0}
            yield {"phase": "success", "status": "success", "completed": 100,
                   "total": 100, "percent": 100.0}
        monkeypatch.setattr(llm, "pull_stream", fake_pull)
        job = client.post("/api/jobs/pull-model", json={"model": "stub"}).json()
        st = self._wait(client, job["job"])
        assert st["status"] == "done" and st["result"]["phase"] == "success"
        assert st["done"] == 100 and st["total"] == 100


class TestLabExport:
    """POST /api/lab-export — push a generated artifact to the lab MinIO over a
    saved connection (bucket pdc-exports, created on first use)."""

    def _clear_conns(self):
        import api
        api._save_connections([])

    def test_no_minio_connection_400(self, client):
        self._clear_conns()
        r = client.post("/api/lab-export", json={"filename": "x.jsonl", "text": "{}"})
        assert r.status_code == 400 and "MinIO" in r.json()["error"]

    def test_missing_filename_or_payload_400(self, client):
        assert client.post("/api/lab-export", json={"text": "{}"}).status_code == 400
        assert client.post("/api/lab-export",
                           json={"filename": "x.jsonl"}).status_code == 400

    def test_uploads_via_saved_connection(self, client, monkeypatch):
        from engine import suggester
        self._clear_conns()
        client.post("/api/connections",
                    json={"name": "LabMinio", "type": "minio",
                          "config": {"endpoint": "http://minio:9000", "bucket": "docs"}})
        calls = {}

        class FakeS3:
            def head_bucket(self, Bucket):
                raise RuntimeError("NoSuchBucket")   # forces the create path

            def create_bucket(self, Bucket):
                calls["created"] = Bucket

            def put_object(self, Bucket, Key, Body, ContentType):
                calls["put"] = (Bucket, Key, Body, ContentType)

        monkeypatch.setattr(suggester, "_s3_client", lambda cfg: FakeS3())
        r = client.post("/api/lab-export",
                        json={"filename": "glossary-import.jsonl",
                              "text": '{"a":1}\n',
                              "content_type": "application/x-ndjson"})
        d = r.json()
        assert r.status_code == 200 and d["ok"] is True
        assert d["bucket"] == "pdc-exports" and calls["created"] == "pdc-exports"
        bkt, key, body, ctype = calls["put"]
        assert bkt == "pdc-exports" and key.endswith("-glossary-import.jsonl")
        assert body == b'{"a":1}\n' and ctype == "application/x-ndjson"
        assert d["connection"] == "LabMinio" and ":9001" in d["hint"]

    def test_several_connections_need_an_explicit_pick(self, client, monkeypatch):
        from engine import suggester
        self._clear_conns()
        for n in ("LabMinio", "OtherStore"):
            client.post("/api/connections",
                        json={"name": n, "type": "minio",
                              "config": {"endpoint": "http://m:9000", "bucket": "b"}})

        class FakeS3:
            def head_bucket(self, Bucket): pass
            def put_object(self, **kw): pass

        monkeypatch.setattr(suggester, "_s3_client", lambda cfg: FakeS3())
        r = client.post("/api/lab-export", json={"filename": "a.zip", "b64": "UEs="})
        assert r.status_code == 400 and "connection" in r.json()["error"]
        r = client.post("/api/lab-export", json={"filename": "a.zip", "b64": "UEs=",
                                                 "connection": "OtherStore"})
        assert r.status_code == 200 and r.json()["connection"] == "OtherStore"


class TestDiscoveryProgress:
    """POST /api/discovery-progress — terminal-aware: reports the worker's own
    state so the UI can stop when the job finishes even if some files never
    flip profiledAt (PDC computes no DQ for e.g. pdf/docx)."""

    def test_worker_done_reported_even_when_not_all_profiled(self, client, monkeypatch):
        import api
        from sources import pdc_api
        monkeypatch.setattr(api, "_pdc_token_and_reauth", lambda *a, **k: ("tok", None))
        monkeypatch.setattr(pdc_api, "profiled_snapshot",
                            lambda *a, **k: {"id1": "2026-07-18T10:00:00", "id2": None})
        monkeypatch.setattr(pdc_api, "job_status",
                            lambda *a, **k: {"status": "COMPLETED", "activity": "done",
                                             "error": "", "raw": {}})
        r = client.post("/api/discovery-progress",
                        json={"base_url": "https://pdc", "ids": ["id1", "id2"],
                              "baseline": {"id1": None, "id2": None}, "job_id": "j1"})
        d = r.json()
        assert r.status_code == 200
        assert d["profiled"] == 1 and d["total"] == 2 and d["done"] is False
        assert d["per"] == {"id1": True, "id2": False}
        assert d["worker_done"] is True and d["job"]["status"] == "COMPLETED"

    def test_without_job_id_the_old_contract_holds(self, client, monkeypatch):
        import api
        from sources import pdc_api
        monkeypatch.setattr(api, "_pdc_token_and_reauth", lambda *a, **k: ("tok", None))
        monkeypatch.setattr(pdc_api, "profiled_snapshot",
                            lambda *a, **k: {"id1": "t1", "id2": "t2"})
        r = client.post("/api/discovery-progress",
                        json={"base_url": "https://pdc", "ids": ["id1", "id2"],
                              "baseline": {}})
        d = r.json()
        assert d["done"] is True and d["profiled"] == 2
        assert d["job"] is None and d["worker_done"] is False


class TestSpaCachePolicy:
    """index.html points at the hashed bundle, so it must revalidate — otherwise
       the browser's heuristic caching keeps loading the previous release's JS
       and the app appears not to have upgraded."""

    def test_index_revalidates_and_assets_are_immutable(self, client):
        r = client.get("/")
        if r.status_code == 404:
            import pytest
            pytest.skip("frontend/dist not built in this checkout")
        assert r.headers.get("cache-control") == "no-cache", \
            "index.html must revalidate or an upgrade is invisible until a hard reload"

        import os, re
        dist = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist", "assets")
        js = [f for f in os.listdir(dist) if f.endswith(".js")]
        assert js, "no built bundle to check"
        a = client.get(f"/assets/{js[0]}")
        assert a.status_code == 200
        assert "immutable" in a.headers.get("cache-control", ""), \
            "content-hashed assets should be cached hard — the name changes when they do"
        assert re.search(r"-[A-Za-z0-9_-]{6,}\.js$", js[0]), "bundle should be content-hashed"


class TestAdviseHonesty:
    """`used_llm: false` means the model wasn't NEEDED as often as it means the
       model wasn't AVAILABLE. The response has to distinguish them or the UI
       blames a healthy Ollama for a run the evidence already settled."""

    def test_reports_zero_ambiguous_when_evidence_settles_everything(self, client, monkeypatch):
        from ai import llm
        called = {"n": 0}

        def _never(*a, **k):
            called["n"] += 1
            return {}, True
        monkeypatch.setattr(llm, "adjudicate_groups", _never)
        # two same-named terms whose profiled value sets are disjoint -> decided
        rows = [_row("Status", "db.accounts.status", Enum_Values="OPEN;CLOSED",
                     Category="Account", Keep="Yes"),
                _row("Status", "db.loans.status", Enum_Values="CURRENT;DEFAULT",
                     Category="Lending", Keep="Yes")]
        r = client.post("/api/recommend-resolutions", json={"rows": rows, "ai": True})
        assert r.status_code == 200
        body = r.json()
        assert "ambiguous" in body, "the caller cannot tell the two cases apart without this"
        assert body["ambiguous"] == 0
        assert body["used_llm"] is False
        assert called["n"] == 0, "nothing ambiguous -> the adjudicator must not run"


class TestPdcDerivedQuality:
    """PDC profiles server-side, so where it has measurements they beat the
       app's own partial sampling — and for pdf/docx, which the app cannot read
       at all, they are the only measurements that will ever exist."""

    def test_profiling_response_carries_a_derived_score(self, client, monkeypatch):
        from sources import pdc_api
        monkeypatch.setattr(
            pdc_api, "pdc_profile_for_columns",
            lambda *a, **k: {
                "s.t.full_col":  {"id": "1", "stats": {"density": 100, "uniqueness": 100}},
                "s.t.sparse_col": {"id": "2", "stats": {"density": 40}},
                "s.t.unprofiled": {"id": "3", "stats": {}},
            })
        r = client.post("/api/pdc-profiling", json={
            "base_url": "https://pdc.example.com", "token": "t",
            "columns": [{"schema": "s", "table": "t", "column": "full_col"}]})
        assert r.status_code == 200
        p = r.json()["profiles"]
        assert p["s.t.full_col"]["derived_quality"] == 100
        assert p["s.t.sparse_col"]["derived_quality"] == 40
        assert p["s.t.unprofiled"]["derived_quality"] is None, "no measurement, no score"
        assert r.json()["derived_quality"] == 2, "counts only the scored ones"


class TestSourceViewer:
    """The "Under the hood" viewer serves files by RELATIVE PATH.

    Nothing else checks those strings, so a module move breaks them silently -
    the page 404s and the learner concludes the app is broken rather than that a
    path went stale. This is the check that grouping the modules into packages
    needed and did not have.
    """

    def test_every_whitelisted_source_exists(self):
        import api
        missing = [k for k in api._SOURCE_WHITELIST if not os.path.isfile(api._source_path(k))]
        assert not missing, "whitelisted sources that do not exist: {}".format(missing)

    def test_developer_tools_are_not_offered(self):
        """cli/* does not ship with the installer, so serving it would 404 on a
           real install even though it resolves in a checkout."""
        import api
        assert not [k for k in api._SOURCE_WHITELIST if k.startswith("cli/")]


class TestSeedIsGated:
    """/api/seed is the only endpoint that writes to a connected database.

    "Only empty tables" is not the safeguard it sounds like: a production estate
    has empty tables - a new feature's, an audit table not yet written to, a
    staging table between loads - and a seed would fill them with fabricated
    rows. The UI asks twice, but a UI is not a control: the gate is enforced here
    so a frontend change can never be the only thing in the way.
    """

    def test_a_connection_must_opt_in_before_anything_is_written(self, client):
        r = client.post("/api/seed", json={"conn": {"engine": "postgresql",
                                                    "host": "db", "database": "prod"}})
        assert r.status_code == 400
        msg = r.json()["error"]
        assert "not marked as safe" in msg
        assert "production" in msg.lower(), "the refusal must say WHY, not just no"

    def test_the_opt_in_is_read_strictly(self):
        from api import _truthy
        assert _truthy(True) and _truthy("true") and _truthy("yes") and _truthy("1")
        for absent in (None, "", "no", "false", "0", "maybe", {}, []):
            assert not _truthy(absent), absent

    def test_a_dry_run_needs_no_opt_in_and_writes_nothing(self, client, monkeypatch):
        """The preview must work on a connection that is NOT allowed to be seeded -
           seeing what would happen is how someone decides whether to allow it."""
        import api
        calls = {"plan": 0, "seed": 0}

        def fake_plan(cfg, only_empty=True, schema=None):
            calls["plan"] += 1
            return {"schema": "public", "database": "demo",
                    "targets": [{"table": "customers", "existing_rows": 0}], "skipped": []}

        def fake_seed(*a, **k):
            calls["seed"] += 1
            raise AssertionError("a dry run must never reach the writer")

        monkeypatch.setattr(api.seed_sample, "plan", fake_plan)
        monkeypatch.setattr(api.seed_sample, "seed", fake_seed)
        r = client.post("/api/seed", json={"conn": {"database": "demo"}, "dry_run": True})
        assert r.status_code == 200
        assert r.json()["targets"][0]["table"] == "customers"
        assert calls == {"plan": 1, "seed": 0}


class TestReadinessReportsWhatIsMissing:
    """Both inputs are optional and both degrade SILENTLY, which is the whole
    reason this endpoint exists.

    No domain pack -> the engine returns {} and falls back to generic vocabulary:
    `mbr_no` stays "Mbr No" instead of becoming "Member Number". No roster ->
    stewardship exports empty and PDC accepts it. In each case the run succeeds
    and looks identical to a healthy one, so the UI has to be told.
    """

    def test_reports_an_absent_pack_and_an_empty_roster(self, client, monkeypatch):
        import api
        monkeypatch.setattr(api, "_load_people", lambda: [])
        from engine import suggester
        monkeypatch.setattr(suggester, "_load_domain_pack", lambda: {})
        d = client.get("/api/readiness").json()
        assert d["domain_pack"]["present"] is False
        assert d["domain_pack"]["entries"] == 0
        assert d["roster"]["people"] == 0

    def test_a_pack_with_no_vocabulary_counts_as_absent(self, client, monkeypatch):
        """A pack carrying only a domain name gives the same bland glossary as no
           pack at all, so it must not read as configured."""
        from engine import suggester
        monkeypatch.setattr(suggester, "_load_domain_pack",
                            lambda: {"domain": "water_utility", "note": "scaffold"})
        d = client.get("/api/readiness").json()
        assert d["domain_pack"]["present"] is False, "empty must not look configured"
        assert d["domain_pack"]["domain"] == "water_utility"

    def test_vocabulary_makes_it_present(self, client, monkeypatch):
        from engine import suggester
        monkeypatch.setattr(suggester, "_load_domain_pack",
                            lambda: {"domain": "d", "abbreviations": {"mbr": "Member"},
                                     "cat_keywords": {"Customer": ["member"]}})
        d = client.get("/api/readiness").json()
        assert d["domain_pack"]["present"] is True
        assert d["domain_pack"]["entries"] == 2
        assert set(d["domain_pack"]["sections"]) == {"abbreviations", "cat_keywords"}

    def test_readiness_never_raises_on_a_broken_pack(self, client, monkeypatch):
        """It warns; it must never be the thing that stops the app loading."""
        from engine import suggester

        def boom():
            raise RuntimeError("unreadable pack")

        monkeypatch.setattr(suggester, "_load_domain_pack", boom)
        r = client.get("/api/readiness")
        assert r.status_code == 200 and r.json()["domain_pack"]["present"] is False


class TestAiCategoriesProposesFromSchema:
    """The steward must not guess a taxonomy, and the model must not invent one:
    it is shown tables, columns and FK links the scan proved, proposes an
    abstract grouping, and the steward gates it. Tables the model leaves out
    are reported and keep their physical group - never silently guessed."""

    def test_endpoint_returns_proposal_and_aligned_assignments(self, client, monkeypatch):
        from ai import llm as _llm

        def fake(rows, model=None, compute=None):
            return ([{"name": "Customer", "definition": "d", "tables": ["customers"]}],
                    ["Customer", None], True)

        monkeypatch.setattr(_llm, "propose_categories", fake)
        r = client.post("/api/ai-categories", json={"rows": [
            {"Keep": "Y", "Term": "A", "Source_Column": "s.customers.a"},
            {"Keep": "Y", "Term": "B", "Source_Column": "s.rates.b"}]})
        assert r.status_code == 200
        d = r.json()
        assert d["used_llm"] is True
        assert d["assignments"] == ["Customer", None]
        assert d["categories"][0]["tables"] == ["customers"]

    def test_evidence_carries_the_fk_graph(self):
        from ai import llm
        rows = [{"Keep": "Y", "Term": "T", "Source_Column": "s.monthly_usage.gallons",
                 "Source_Keys": {"s.monthly_usage.customer_id":
                                 {"fk": True, "ref": "customers.customer_id"}}}]
        ev = llm.schema_evidence(rows)
        assert ev["monthly_usage"]["refs"] == {"customers"}, \
            "the FK graph is the strongest grouping signal and must reach the prompt"

    def test_offline_proposes_nothing_rather_than_guessing(self):
        from ai import llm
        rows = [{"Keep": "Y", "Term": "A", "Source_Column": "s.t1.a"},
                {"Keep": "Y", "Term": "B", "Source_Column": "s.t2.b"}]
        prop, assign, used = llm.propose_categories(rows, model="definitely-not-a-model")
        # used_llm may be True (server up, bogus model answered nothing) or
        # False (server down) - the guarantee under test is the same either
        # way: NOTHING is guessed. No proposal, every assignment None.
        assert prop == [] and assign == [None, None]


class TestDictionarySyncOnEntry:
    def test_sync_adjudicates_live_rows_without_a_save(self, client, fresh_dict):
        """The save-path sync only fires when an edit triggers a save, so the
           Dictionary page adjudicated a pre-edit queue (field-caught: "pH
           Level" fixed on Review, still pending as "Ph Level"). The page now
           POSTS the live rows on entry - same one-way rules, and the response
           is the refreshed summary the page renders directly."""
        tagdict = fresh_dict
        tagdict.accrete([_row("Ph Level", "awc.water_quality_reports.ph_level")],
                        persist=True)
        d = client.post("/api/tagdict/sync", json={"rows": [
            _row("pH Level", "awc.water_quality_reports.ph_level",
                 Definition="The acidity or alkalinity of water samples."),
        ]}).json()
        assert d.get("pending_refreshed", 0) >= 1
        names = {t["term"] for t in d.get("terms", []) if t.get("status") == "pending"}
        assert "pH Level" in names and "Ph Level" not in names, \
            "the gate must show the steward's casing without waiting for a save"

    def test_sync_without_rows_is_a_plain_read(self, client):
        d = client.post("/api/tagdict/sync", json={}).json()
        assert d.get("pending_refreshed") == 0
        assert "terms" in d and "tags" in d


class TestDraftPoliciesJob:
    def test_job_narrates_and_serves_the_bundle(self, client, fresh_dict):
        """The AI polish ran for minutes behind a silent "Drafting…" (field:
           "could do with some feedback"). The job twin narrates phases and
           keeps the finished zip on the job — and the poll must NEVER leak
           the raw bytes (underscore keys stay server-side)."""
        import time
        rows = [_row("Meter Size", "awc.meters.meter_size",
                     Value_Pattern="^[0-9]{2}$")]
        job = client.post("/api/jobs/draft-policies",
                          json={"rows": rows, "glossary_name": "G"}).json()["job"]
        for _ in range(100):
            j = client.get(f"/api/jobs/{job}").json()
            if j["status"] != "running":
                break
            time.sleep(0.05)
        assert j["status"] == "done", j.get("detail")
        assert "_zip" not in j, "underscore keys must not travel in the poll"
        r = j["result"]
        assert {"patterns", "dictionaries", "quality", "skipped"} <= set(r)
        z = client.get(f"/api/jobs/{job}/zip")
        assert z.status_code == 200
        assert z.content[:2] == b"PK", "the stored bundle must be a real zip"

    def test_zip_404s_for_jobs_without_a_bundle(self, client):
        r = client.get("/api/jobs/nonexistent/zip")
        assert r.status_code == 404


class TestEstateReport:
    def test_contract_verifies_from_disk_not_ticks(self, client, fresh_dict):
        """The closeout is a CONTRACT CHECK: registry parsed and id-matched,
           receipts consulted, freshness compared — "checks that all the
           required estate docs are in place ready for Policy Generator"."""
        rows = [_row("Meter Size", "awc.meters.meter_size",
                     Critical_Data_Element="No", PII_Category="")]
        r = client.post("/api/estate-report",
                        json={"rows": rows, "glossary_name": "Estate X"}).json()
        assert r["ready"] is False
        keys = {c["key"]: c for c in r["contract"]}
        assert not keys["registry"]["ok"], "no registry yet"
        assert not keys["jsonl"]["ok"], "no generate receipt yet"
        assert r["stats"]["terms_kept"] == 1

        client.post("/api/generate",
                    json={"rows": rows, "glossary_name": "Estate X"})
        r2 = client.post("/api/estate-report",
                         json={"rows": rows, "glossary_name": "Estate X"}).json()
        k2 = {c["key"]: c for c in r2["contract"]}
        assert k2["registry"]["ok"], k2["registry"]
        assert k2["jsonl"]["ok"], k2["jsonl"]
        assert "concept" in k2["registry"]["detail"]

    def test_registry_id_mismatch_is_named(self, client, fresh_dict):
        """A registry from a DIFFERENT glossary must fail the contract with
           the reason, not pass on file-exists."""
        rows = [_row("Meter Size", "awc.meters.meter_size",
                     Critical_Data_Element="No", PII_Category="")]
        client.post("/api/generate",
                    json={"rows": rows, "glossary_name": "Estate A"})
        import os as _os
        from api import _registry_path
        _os.replace(_registry_path("Estate A"), _registry_path("Estate B"))
        r = client.post("/api/estate-report",
                        json={"rows": rows, "glossary_name": "Estate B"}).json()
        keys = {c["key"]: c for c in r["contract"]}
        assert not keys["registry"]["ok"]
        assert "DIFFERENT glossary" in keys["registry"]["detail"]


class TestAdviseJob:
    def test_job_returns_the_same_payload_as_the_sync_route(self, client):
        """AI advise ran behind a silent "Advising…" — the job twin narrates
           evidence → probe → adjudicate and returns the sync payload."""
        import time
        rows = [_row("Capacity", "awc.gis.capacity"),
                _row("Capacity", "awc.ops.capacity")]
        job = client.post("/api/jobs/recommend-resolutions",
                          json={"rows": rows}).json()["job"]
        for _ in range(100):
            j = client.get(f"/api/jobs/{job}").json()
            if j["status"] != "running":
                break
            time.sleep(0.05)
        assert j["status"] == "done", j.get("detail")
        r = j["result"]
        assert {"groups", "probed", "used_llm", "ambiguous"} <= set(r)
        assert any(g["name"] == "Capacity" for g in r["groups"])


class TestBaseUrlSurvivesPasteDamage:
    def test_doubled_scheme_is_normalized(self):
        """"Could not reach https:/https://pentaho.io/...: no host given" —
           a doubled scheme in the base field parsed as no-host and read as
           a NETWORK failure (the user went to check the NIC). clean_base
           exists to absorb paste mistakes; a doubled scheme is the same
           family: the LAST scheme owns the real host."""
        from pdc_client.core import clean_base
        assert clean_base("https:/https://pentaho.io") == "https://pentaho.io"
        assert clean_base("https://https://pentaho.io") == "https://pentaho.io"
        assert clean_base("http://https://pentaho.io") == "https://pentaho.io"
        assert clean_base("https://pentaho.io") == "https://pentaho.io", \
            "a healthy base must pass through untouched"
        assert clean_base("https://pentaho.io/keycloak/realms/pdc") == \
            "https://pentaho.io", "existing path-stripping still works"


class TestGlossaryTreeCheckWiring:
    def test_route_reaches_the_network_not_an_attribute_error(self, client):
        """glossary_categories lives in pdc_client.entities but was never
           added to the package's __init__ exports, so the shim re-exported
           everything EXCEPT it - the first live click died with "module
           'sources.pdc_api' has no attribute 'glossary_categories'"
           (field-caught the moment the never-live-verified branch met
           reality). The route must fail on the NETWORK (bogus host), never
           on the attribute."""
        from sources import pdc_api
        assert hasattr(pdc_api, "glossary_categories"), \
            "the shim must re-export glossary_categories"
        r = client.post("/api/pdc/glossary-tree-check", json={
            "base_url": "https://pdc.invalid.example", "glossary": "G",
            "categories": ["A"], "token": "x"})
        assert r.status_code == 502
        assert "glossary_categories" not in (r.json().get("error") or ""), \
            "the failure must be the unreachable host, not the wiring"


class TestClientLogIsTheBlackBox:
    def test_client_errors_reach_app_log(self, client):
        """A field crash left NOTHING to read - no Windows event, no WebView
           dump, no log. The frontend beacons uncaught errors here and they
           must land in app.log in the state dir, so the NEXT vanishing
           window leaves a record."""
        r = client.post("/api/client-log", json={
            "kind": "error", "message": "boom at ReviewPage",
            "stack": "Error: boom\n  at aiCategories", "url": "#review"})
        assert r.status_code == 200 and r.json().get("ok") is True
        import logging
        for h in logging.getLogger("client").handlers:
            try:
                h.flush()
            except Exception:
                pass
        log = os.path.join(os.environ["GLOSSARY_STATE_DIR"], "app.log")
        assert os.path.exists(log), "app.log must exist in the state dir"
        with open(log, encoding="utf-8") as f:
            text = f.read()
        assert "boom at ReviewPage" in text and "#review" in text


class TestPendingHealthSeesTheLiveGrid:
    def test_first_run_unsaved_rows_are_not_fossils(self, client, fresh_dict):
        """The stale universe was SAVED glossaries only, and the autosave only
           writes once the glossary is NAMED — so a first run reaching the
           Dictionary before naming saw its entire fresh queue flagged stale
           and "Retire stale" offered to tombstone the whole vocabulary
           (field-caught). The page now POSTS the live rows with the health
           check; entries they back are evidence-carrying, not fossils."""
        tagdict = fresh_dict
        rows = [_row("Fossil Candidate", "zz.fossil_table.fossil_col",
                     Suggested_Tags="fossil-tag")]
        tagdict.accrete(rows, persist=True)
        stale = client.get("/api/tagdict/pending-health").json()
        assert "Fossil Candidate" in stale["terms"], \
            "with an empty store and no live rows the entry IS a fossil"
        stale = client.post("/api/tagdict/pending-health",
                            json={"rows": rows}).json()
        assert "Fossil Candidate" not in stale["terms"], \
            "rows the caller posts are evidence — a first run has no fossils"
        assert "fossil-tag" not in stale["tags"], \
            "live rows back tags the same way they back terms"


class TestWritesSurviveAVanishedStateDir:
    def test_write_recreates_the_directory(self, client, fresh_dict):
        """Delete the state dir under a RUNNING server (the fresh-install wipe
           done after launch) and every write endpoint 500'd with
           FileNotFoundError while reads kept working - import connections and
           Harvest both died on virgin soil (field-caught). Writers now
           recreate the directory: state loss is acceptable on a deliberate
           wipe, a dead server is not."""
        import os, shutil
        from core import paths
        csv = ("resourceName,kind,host,port,databaseName,userName,password,schemaNames\n"
               "AWO,postgres,h,5433,db,u,p,s\n")
        r = client.post("/api/connections/import-csv", json={"csv": csv, "only": ["AWO"]})
        assert r.status_code == 200
        shutil.rmtree(paths.state_dir())                      # the mid-life wipe
        assert not os.path.isdir(paths.state_dir())
        r2 = client.post("/api/connections/import-csv", json={"csv": csv, "only": ["AWO"]})
        assert r2.status_code == 200, "writes must self-heal, not 500"
        assert os.path.isdir(paths.state_dir())


class TestFactoryReset:
    def test_wipes_state_and_requires_confirm(self, client, fresh_dict):
        """The installer's delete-app-data failed to wipe on an upgrade and
           two estates conflated — the app owns its own zero. Guarded by an
           explicit confirm; app.log is kept (the black box outlives the
           wipe)."""
        import os as _os
        tagdict = fresh_dict
        tagdict.accrete([_row("Meter Size", "awc.meters.meter_size")],
                        persist=True)
        assert _os.path.exists(_os.environ["GLOSSARY_TAG_DICTIONARY"])
        r = client.post("/api/factory-reset", json={})
        assert r.status_code == 400, "no confirm, no wipe"
        r2 = client.post("/api/factory-reset", json={"confirm": "RESET"}).json()
        assert "tag_dictionary.json" in r2["deleted"]
        assert not _os.path.exists(_os.environ["GLOSSARY_TAG_DICTIONARY"])
        d = client.get("/api/tagdict").json()
        assert all(t.get("status") != "pending" for t in d.get("terms", [])), \
            "the running process forgets too — reseeded defaults, no pending"
