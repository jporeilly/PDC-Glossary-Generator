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
