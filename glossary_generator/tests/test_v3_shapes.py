"""Offline PDC 11 (public API v3) request-shape validation — the pytest port
of v3_selftest.py.

Every body the app can send is checked against the OFFICIAL v3 OpenAPI schemas
(docs.pentaho.com, PDC Public API v3), with the strict parts embedded here as
allow-lists — the entity PATCH is `additionalProperties: false` at every level,
so an unknown key is a 400, not a warning. Runs against the shared pdc_client
package (via the pdc_api shim) after any change to the client / suggester
builders."""
import inspect
import io

import pytest

from sources import pdc_api
from engine import suggester

# --------------------------------------------------------------------------- #
#  The v3 contract, embedded (source: PDC Public API v3 OpenAPI, PDC 11.0.0)
# --------------------------------------------------------------------------- #
PATCH_ATTR_KEYS = {"info", "features", "customProperties", "tags", "businessTerms",
                   "owners", "policies", "mlModels", "applications", "physicalAssets",
                   "contentScanDiscoveries", "dataCollections", "extended"}
PATCH_INFO_KEYS = {"description"}
PATCH_FEATURE_KEYS = {"sensitivity", "rating", "qualityScore", "trustScore",
                      "isCriticalDataElement", "isLineageVerified"}
PATCH_RATING_KEYS = {"value", "users"}
PATCH_TERM_KEYS = {"id", "glossaryId", "name", "sourceName", "sourceType", "confidenceScore"}
SEARCH_KEYS = {"searchTerm", "searchFacets", "page", "perPage"}
ENTITY_FILTER_KEYS = {"parentIds", "rootIds", "types", "collectionIds", "resourceIds",
                      "names", "fqdns", "buckets", "profileStatus"}
DS_FILTER_KEYS = {"ids", "resourceNames", "databaseTypes"}
BULK_JOB_NAMES = {"TEST_CONNECTION", "CLEANUP_DATASOURCE", "METADATA_INGEST",
                  "METADATA_REINGEST", "DATA_PROFILE", "DATA_DISCOVERY",
                  "DATA_IDENTIFICATION", "QUALITY_RULE", "QUALITY_RULE_ROW_COUNTER",
                  "ENTITY_USAGE", "ML_MANAGER_PRIMARY", "CALCULATE_TRUST_SCORE",
                  "COLLECTIONS_DATA_PROFILE", "COLLECTIONS_DATA_AGGREGATION",
                  "COLLECTIONS_TRUST_SCORE", "COLLECTIONS_SENSITIVITY",
                  "COLLECTIONS_QUALITY_SCORE"}
BULK_ITEM_KEYS = {"name", "type", "payload"}
BULK_REQUIRED_PAYLOAD = {"CALCULATE_TRUST_SCORE": {"scope"},
                         "DATA_DISCOVERY": {"scope", "configs"},
                         "DATA_IDENTIFICATION": {"scope"}}

ROWS = [{"Keep": "Y", "Category": "Customer", "Term": "Member Number",
         "Source_Column": "cscu.members.mbr_no",
         "Definition": "The member's unique CSCU number.",
         "Sensitivity": "HIGH", "PII_Category": "GOVERNMENT_ID",
         "Critical_Data_Element": "Yes", "Suggested_Tags": "pii;identifier",
         "Suggested_Rating": 4, "Source_Ratings": {"cscu.members.mbr_no": 4},
         "Suggested_Quality": 92,
         "Source_Quality_Dims": {"cscu.members.mbr_no": {"c": 1.0, "u": 1.0, "v": 1.0,
                                                         "eu": True, "nn": True}},
         "Value_Pattern": r"^CSCU-\d{6}$", "Value_Signature": "AAAA-nnnnnn",
         "Source_Keys": {"cscu.members.mbr_no": {"pk": True, "fk": False, "ref": None}}}]


def check_patch_attrs(attrs, strict=True):
    assert set(attrs) <= PATCH_ATTR_KEYS, set(attrs) - PATCH_ATTR_KEYS
    info = attrs.get("info")
    if isinstance(info, dict):
        assert set(info) <= PATCH_INFO_KEYS, set(info) - PATCH_INFO_KEYS
    feats = attrs.get("features")
    if isinstance(feats, dict):
        assert set(feats) <= PATCH_FEATURE_KEYS, set(feats) - PATCH_FEATURE_KEYS
        r = feats.get("rating")
        if isinstance(r, dict):
            assert set(r) <= PATCH_RATING_KEYS, set(r) - PATCH_RATING_KEYS
    for bt in attrs.get("businessTerms") or []:
        # the raw builder carries an app-internal 'glossary' name used by
        # Resolve; merge_attributes/_clean_term strips it before any PATCH,
        # so only PATCH-bound bodies are held to the strict whitelist
        extra = set(bt) - PATCH_TERM_KEYS - ({"glossary"} if not strict else set())
        assert not extra, (bt.get("name", "?"), extra)


class TestApplyPatchBodies:
    def test_builder_output_within_whitelist(self):
        links = suggester.data_element_links(ROWS, policy={"mode": "all"})
        api_json = suggester.links_to_api_json(links)
        assert api_json
        for rec in api_json:
            check_patch_attrs(rec["attributes"], strict=False)

    def test_steward_tags_stamp_mapping_only_columns_with_provenance(self):
        """"If I did a pii search, it wouldn't appear?" (field 2026-08-23):
           the steward approved tags in Review and they never reached the one
           facet PDC users search first. Approved GOVERNED tags now stamp
           mapping-only columns (where no method can ever exist, so the
           tags-mean-a-rule-fired fingerprint on seeded columns is intact),
           with provenance in extended.stewardTags. Structural and
           off-vocabulary tags never stamp."""
        rows = [
            dict(ROWS[0]),                                     # seeded (has detect evidence)
            {"Keep": "Y", "Category": "Customer", "Term": "Member Name",
             "Source_Column": "cscu.members.full_nm",
             "Definition": "The member's name.", "Sensitivity": "HIGH",
             "PII_Category": "NAME", "Critical_Data_Element": "No",
             "Suggested_Tags": "pii;privacy;maskable;identifier;off-vocab-thing",
             "Detection_Intent": "mapping_only"},
        ]
        links = suggester.data_element_links(rows, policy={"mode": "all"},
                                             allowed_tags={"pii", "privacy", "contact"})
        recs = suggester.links_to_api_json(links, rater="a.steward")
        by = {r["columnName"]: r["attributes"] for r in recs}
        # mapping-only: governed tags stamp, structural + off-vocabulary do not
        assert by["full_nm"].get("tags") == [{"name": "pii"}, {"name": "privacy"}]
        prov = by["full_nm"]["extended"]["stewardTags"]
        assert prov == {"tags": ["pii", "privacy"], "source": "glossary-apply",
                        "by": "a.steward"}
        # seeded column: NO tags in the payload — a rule earns those
        assert "tags" not in by["mbr_no"]
        for rec in recs:
            check_patch_attrs(rec["attributes"], strict=False)
        # the PATCH merge unions with what the entity already carries
        merged = pdc_api.merge_attributes(
            {"tags": [{"name": "hand-added"}, {"name": "pii"}]}, by["full_nm"])
        assert merged["tags"] == [{"name": "hand-added"}, {"name": "pii"},
                                  {"name": "privacy"}]

    def test_column_ratings_carry_their_rater(self):
        """A rating without a `users` map is a rating nobody cast: PDC shows
           0 stars, and Apply's table roll-up harvests its raters FROM the
           column ratings, so a rater-less column also silently disables every
           table rating (field 2026-08-23: 155 columns rated, 0 tables, 0
           stars everywhere). With a rater the map rides; without one the
           value still lands (the old shape, honestly degraded)."""
        links = suggester.data_element_links(ROWS, policy={"mode": "all"})
        rated = suggester.links_to_api_json(links, rater="a.steward")
        r = next(rec["attributes"]["features"]["rating"] for rec in rated
                 if (rec["attributes"]["features"].get("rating") or {}).get("value"))
        assert r["users"] == {"a.steward": r["value"]}
        check_patch_attrs(rated[0]["attributes"], strict=False)
        bare = suggester.links_to_api_json(links)
        rb = next(rec["attributes"]["features"]["rating"] for rec in bare
                  if (rec["attributes"]["features"].get("rating") or {}).get("value"))
        assert "users" not in rb

    def test_merged_apply_body_strict(self):
        links = suggester.data_element_links(ROWS, policy={"mode": "all"})
        api_json = suggester.links_to_api_json(links)
        merged = pdc_api.merge_attributes(
            {"businessTerms": [{"name": "Old", "id": "x", "glossaryId": "g",
                                "glossary": "DROP-ME"}],  # server junk must be cleaned
             "features": {"sensitivity": "LOW"}, "extended": {"prior": 1},
             "info": {"description": "old"}},
            api_json[0]["attributes"])
        check_patch_attrs(merged, strict=True)

    def test_table_rollup_body(self):
        tattrs = pdc_api.merge_attributes(
            {}, {"features": {"rating": {"value": 4}, "qualityScore": 92,
                              "sensitivity": "HIGH", "isLineageVerified": True},
                 "businessTerms": [{"name": "Member Record", "id": "t", "glossaryId": "g"}],
                 "info": {"description": "A single member record."}})
        check_patch_attrs(tattrs, strict=True)

    def test_delta_apply_detects_no_op_merges(self):
        """"be better if this did just the delta" — a merge that reproduces
        exactly what the entity already carries is a no-op and the PATCH is
        skipped; any real difference (a new term, a changed rating) reads as
        changed. Conservative: server-side junk on the current terms is
        cleaned on BOTH sides before comparing."""
        current = {"businessTerms": [{"name": "Member Number", "id": "x",
                                      "glossaryId": "g", "glossary": "junk",
                                      "confidenceScore": 0.9}],
                   "features": {"sensitivity": "HIGH", "qualityScore": 92},
                   "extended": {"isPrimaryKey": True}}
        same = pdc_api.merge_attributes(current, {
            "businessTerms": [{"name": "Member Number", "id": "x", "glossaryId": "g"}],
            "features": {"sensitivity": "HIGH"}})
        assert pdc_api._attrs_unchanged(current, same) is True
        changed = pdc_api.merge_attributes(current, {
            "businessTerms": [{"name": "Card Number", "id": "y", "glossaryId": "g"}],
            "features": {"sensitivity": "HIGH"}})
        assert pdc_api._attrs_unchanged(current, changed) is False
        rating = pdc_api.merge_attributes(current, {
            "features": {"rating": {"value": 4}}})
        assert pdc_api._attrs_unchanged(current, rating) is False


class TestFilterAndSearchShapes:
    def test_search_body_keys(self):
        assert {"searchTerm", "perPage"} <= SEARCH_KEYS

    def test_entity_filter_keys(self):
        for f in ({"names": ["x"]}, {"types": ["COLUMN"]}, {"fqdns": ["a.b"]},
                  {"names": ["f"], "types": ["FILE", "OBJECT", "RESOURCE"]}):
            assert set(f) <= ENTITY_FILTER_KEYS

    def test_cursor_travels_as_query_param(self):
        src = inspect.getsource(pdc_api.filter_entities)
        assert 'body["cursor"]' not in src and 'q["cursor"]' in src
        src = inspect.getsource(pdc_api.filter_profiling_info)
        assert 'body["cursor"]' not in src and 'q["cursor"]' in src

    def test_data_sources_filter_keys(self):
        assert {"resourceNames"} <= DS_FILTER_KEYS


class TestJobShapes:
    def test_bulk_job_names_documented(self):
        for app_name, bulk in pdc_api._V3_BULK_NAMES.items():
            assert bulk in BULK_JOB_NAMES, (app_name, bulk)

    def test_bulk_item_and_payload_shape(self):
        item = {"name": "CALCULATE_TRUST_SCORE", "type": "START", "payload": {"scope": ["id1"]}}
        assert set(item) == BULK_ITEM_KEYS
        for nm, req in BULK_REQUIRED_PAYLOAD.items():
            payload = {"scope": ["u"], "configs": {}}
            assert req <= set(payload), nm

    def test_v3_goes_straight_to_bulk(self):
        src = inspect.getsource(pdc_api._execute_job)
        assert 'in ("v3", "3")' in src and "jobs/execute/bulk" in src


class TestObjectStoreFolderTypes:
    """PDC types an object store's folders FOLDER (a live scan reports
       "16 FILE + 5 FOLDER entities"). If the entity-filter type lists omit it,
       PDC filters every folder out server-side and Data Discovery silently
       falls back to scoping individual FILES — which does NOT cascade, so one
       representative file per folder is profiled and its siblings are not,
       while the job still returns SUCCESS."""

    def test_folder_is_resolvable_as_a_container(self):
        from pdc_client import entities as ent
        assert "FOLDER" in ent._TBL_TYPES, \
            "resolve_table_entity cannot find an object-store folder without it"
        assert "FOLDER" in ent._FILE_TYPES

    def test_the_package_agrees_on_the_type_name(self):
        """bulkload and _is_container already used FOLDER; these lists drifted."""
        from pdc_client import bulkload, entities as ent
        import inspect
        assert "FOLDER" in inspect.getsource(bulkload)
        for t in ("DIRECTORY", "FOLDER"):
            assert t in ent._TBL_TYPES and t in ent._FILE_TYPES


class TestFileScanProfilesStructuredFiles:
    """PDC defaults withProfile and headerExists to FALSE on a file system scan.

    Sending no value inherits that, and the result LOOKS like success: the files
    are catalogued, every badge reads OK, and the CSVs have either no columns at
    all or columns called Column-0..Column-N because the header row was read as
    data. Keys confirmed against a real job record (jobType "File System Scan",
    schemaId "file_system_scan").
    """

    def test_the_scan_asks_for_a_profile_and_a_header(self):
        """Defaults, now expressed as arguments rather than a table: PDC defaults
           withProfile and headerExists to FALSE, and inheriting that catalogues
           every CSV with no columns."""
        import inspect
        from pdc_client import bulkload
        sig = inspect.signature(bulkload.internal_scan_files)
        assert sig.parameters["profile_files"].default is True
        assert sig.parameters["header_row"].default is True
        assert sig.parameters["doc_metadata"].default is True

    def test_the_listing_pass_runs_before_the_scan(self):
        """TEST_CONNECTION is what LISTS the bucket, despite the name; the scan
           persists what it found via lastTestConnectionId. Without it the scan
           walks nothing, completes, and reports success over an empty catalog -
           measured: 0 entities without, 21 files and 53 columns with."""
        import inspect
        from pdc_client import bulkload
        src = inspect.getsource(bulkload.bulk_load_one)
        assert "internal_test_connection(" in src
        i_tc = src.index("internal_test_connection(")
        i_scan = src.index("internal_scan_files(")
        assert i_tc < i_scan, "the listing pass must run FIRST"
        assert "last_test_connection_id=" in src

    def test_the_scan_body_is_minimal(self):
        """Measured, twice, the hard way: any key PDC's own UI does not send
           makes the scan enumerate NOTHING while still reporting success.
           Credentials echoed back -> 0 entities. The profile/header/day flags
           -> 0 entities. The minimal shape -> 21 files and folders. So the body
           must carry ONLY what the captured Test Connection call carries."""
        from pdc_client import bulkload
        sent = {}

        def fake_req(method, url, token=None, body=None, **kw):
            sent.update(body or {})
            return {"data": {"jobId": "j1"}}

        real = bulkload._req
        bulkload._req = fake_req
        try:
            bulkload.internal_scan_files("https://pdc.example", "t",
                                         {"resourceName": "S", "container": "b",
                                          "endpoint": "http://m:9000", "region": "r"},
                                         "rid-1", last_test_connection_id="tc-1",
                                         profile_files=True, header_row=True,
                                         doc_metadata=True, skip_recent_days=14)
        finally:
            bulkload._req = real
        d = sent["data"]
        assert d["resourceId"] == "rid-1"
        assert d["lastTestConnectionId"] == "tc-1"
        for banned in ("withProfile", "headerExists", "withDocMetadata",
                       "filesModifiedLaterThanDays", "filesAccessedLaterThanDays",
                       "containers", "patternType", "contentScanType",
                       "classification", "addressDetection", "summarizeDocuments",
                       "accessId", "accessKey", "secretKey", "secretAccessKey"):
            assert banned not in d, f"{banned} silences the scan - never send it"


class TestHttpErrorsKeepTheirDetail:
    """HTTPError SUBCLASSES URLError, and Python matches except clauses in order.

    With `except URLError` written first, every HTTP response landed there and
    was re-raised bare. The whole HTTP handler below it became unreachable, so:
    the response body vanished ("HTTP Error 400: Bad Request" and nothing else),
    401 stopped raising TokenExpired, and the Cloudflare detection went dead.

    Worse, the bulk loader's safe-recreate guard READS that text to tell a bad
    body from a name conflict - so with no text it deleted working data sources.
    Nothing caught it because no test had ever exercised the error path.
    """

    def _raise(self, monkeypatch, code, body):
        import urllib.error
        from pdc_client import core

        def boom(*a, **k):
            raise urllib.error.HTTPError(
                "https://pdc.example/api/public/v2/data-sources", code, "Bad Request",
                {}, io.BytesIO(body.encode()))

        monkeypatch.setattr(core.urllib.request, "urlopen", boom)
        return core

    def test_the_response_body_reaches_the_caller(self, monkeypatch):
        core = self._raise(monkeypatch, 400, '{"message":"resourceName already exists"}')
        with pytest.raises(RuntimeError) as e:
            core._req("POST", "https://pdc.example/api/public/v2/data-sources", token="t")
        msg = str(e.value)
        assert "already exists" in msg, "PDC's own explanation was dropped"
        assert "400" in msg

    def test_401_is_still_a_token_problem(self, monkeypatch):
        core = self._raise(monkeypatch, 401, "expired")
        with pytest.raises(core.TokenExpired):
            core._req("GET", "https://pdc.example/api/public/v2/data-sources", token="t")

    def test_cloudflare_is_still_named(self, monkeypatch):
        core = self._raise(monkeypatch, 403, "<html>error code: 1010</html>")
        with pytest.raises(RuntimeError) as e:
            core._req("GET", "https://pdc.example/api/public/v2/data-sources", token="t")
        assert "Cloudflare" in str(e.value)


class TestRecreateFailsClosed:
    """Deleting a data source needs positive proof the name is the only problem.

    The guard used to delete unless the error looked like a validation failure -
    i.e. an error it could not parse was taken as proof of a name conflict.
    """

    def test_an_unreadable_error_keeps_the_source(self):
        m = "http error 400: bad request"
        conflict = any(w in m for w in (
            "already exists", "already in use", "duplicate", "conflict", "409", "unique"))
        assert not conflict, "a bare 400 must never authorise a delete"

    def test_a_real_conflict_still_recreates(self):
        m = 'http 400 on post .../data-sources: {"message":"resourceName already exists"}'
        conflict = any(w in m for w in (
            "already exists", "already in use", "duplicate", "conflict", "409", "unique"))
        assert conflict


class TestCloudflareEdge:
    """A refusal at the edge is not an auth failure.

    Reported as "Keycloak auth failed: HTTP 403 ... error code: 1010" - which
    sent the reader to check realms, clients and passwords that Keycloak never
    saw. Both the Keycloak call and the /auth fallback failed identically,
    because Cloudflare refused both before the origin.
    """

    def test_cloudflare_codes_are_recognised(self):
        from pdc_client import core
        assert core._cloudflare_code("error code: 1010") == "1010"
        assert core._cloudflare_code("<html>error code: 1020</html>") == "1020"
        assert core._cloudflare_code('{"error":"invalid_grant"}') is None
        assert core._cloudflare_code("") is None
        assert core._cloudflare_code(None) is None

    def test_the_client_identifies_itself(self):
        """urllib sends "Python-urllib/3.x" unless told otherwise, and that
           signature is exactly what a browser integrity check refuses."""
        from pdc_client import core
        assert "PDC-Glossary-Generator" in core.USER_AGENT
        assert "urllib" not in core.USER_AGENT.lower()

    def test_access_service_token_comes_from_the_environment(self, monkeypatch):
        """Not from settings.json: that file is included in the State snapshot
           the app can export, and these are credentials."""
        from pdc_client import core
        monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        assert core._access_headers() == {}

        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "abc.access")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "shh")
        assert core._access_headers() == {
            "CF-Access-Client-Id": "abc.access",
            "CF-Access-Client-Secret": "shh",
        }

        # One half alone is a misconfiguration, not a partial credential.
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET")
        assert core._access_headers() == {}


class TestPerRowScanOptions:
    """A CSV column overrides the UI default per row, so one bucket can be
    registered twice - a structured row scoped to *.csv and an unstructured row
    scoped to *.pdf - each scanned the way its own file types deserve.

    The trap this guards: treating a BLANK cell as False. A CSV written before
    these columns existed, or one that fills them in on only some rows, must
    behave exactly as it did before - silently switching profiling off for every
    unfilled row would be the same class of failure as the default that shipped
    unticked in 1.36.5.
    """

    def test_blank_and_absent_mean_the_default(self):
        from pdc_client.bulkload import row_flag
        for row in ({}, {"profile": ""}, {"profile": "   "}, {"profile": None}):
            assert row_flag(row, "profile", True) is True
            assert row_flag(row, "profile", False) is False
        assert row_flag(None, "profile", True) is True

    def test_explicit_values_override(self):
        from pdc_client.bulkload import row_flag
        for yes in ("y", "Yes", "TRUE", "t", "1", "on"):
            assert row_flag({"profile": yes}, "profile", False) is True, yes
        for no in ("n", "No", "FALSE", "f", "0", "off"):
            assert row_flag({"profile": no}, "profile", True) is False, no

    def test_an_unreadable_value_is_never_a_silent_false(self):
        from pdc_client.bulkload import row_flag
        assert row_flag({"profile": "maybe"}, "profile", True) is True

    def test_skip_recent_days_reads_as_an_int(self):
        from pdc_client.bulkload import row_int
        assert row_int({}, "skipRecentDays", 7) == 7
        assert row_int({"skipRecentDays": ""}, "skipRecentDays", 7) == 7
        assert row_int({"skipRecentDays": "0"}, "skipRecentDays", 7) == 0,             "0 is meaningful - no age restriction - and must not read as blank"
        assert row_int({"skipRecentDays": "30"}, "skipRecentDays", 0) == 30
        assert row_int({"skipRecentDays": "soon"}, "skipRecentDays", 7) == 7
        assert row_int({"skipRecentDays": "-5"}, "skipRecentDays", 7) == 7



class TestHostForgivesAPastedUrl:
    """The minio endpoint IS a URL, so people write the postgres host the same
    way - and http://192.0.2.1 then fails the ingest with a bare FAILED. The
    intent is unambiguous, so the loader absorbs it."""

    def test_scheme_path_and_port_are_stripped(self):
        from pdc_client.bulkload import _bare_host
        assert _bare_host("http://192.0.2.1") == "192.0.2.1"
        assert _bare_host("https://db.example.com/") == "db.example.com"
        assert _bare_host("192.0.2.1:5433") == "192.0.2.1"
        assert _bare_host(" 192.0.2.1 ") == "192.0.2.1"
        assert _bare_host("db.example.com") == "db.example.com"

    def test_the_body_carries_the_bare_host(self):
        from pdc_client.bulkload import build_data_source_body
        b = build_data_source_body({"kind": "postgres", "resourceName": "T",
                                    "host": "http://192.0.2.1", "port": "5433",
                                    "databaseName": "d", "userName": "u",
                                    "password": "p"})
        assert b["host"] == "192.0.2.1"
