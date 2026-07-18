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
        import llm
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
        import suggester
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
        import suggester
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
        import pdc_api
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
        import pdc_api
        monkeypatch.setattr(api, "_pdc_token_and_reauth", lambda *a, **k: ("tok", None))
        monkeypatch.setattr(pdc_api, "profiled_snapshot",
                            lambda *a, **k: {"id1": "t1", "id2": "t2"})
        r = client.post("/api/discovery-progress",
                        json={"base_url": "https://pdc", "ids": ["id1", "id2"],
                              "baseline": {}})
        d = r.json()
        assert d["done"] is True and d["profiled"] == 2
        assert d["job"] is None and d["worker_done"] is False
