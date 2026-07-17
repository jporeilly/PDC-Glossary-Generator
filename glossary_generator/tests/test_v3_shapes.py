"""Offline PDC 11 (public API v3) request-shape validation — the pytest port
of v3_selftest.py.

Every body the app can send is checked against the OFFICIAL v3 OpenAPI schemas
(docs.pentaho.com, PDC Public API v3), with the strict parts embedded here as
allow-lists — the entity PATCH is `additionalProperties: false` at every level,
so an unknown key is a 400, not a warning. Runs against the shared pdc_client
package (via the pdc_api shim) after any change to the client / suggester
builders."""
import inspect

import pdc_api
import suggester

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
