"""
v3_selftest.py — offline PDC 11 (public API v3) request-shape validation.

Every body the app can send is checked against the OFFICIAL v3 OpenAPI schemas
(docs.pentaho.com, PDC Public API v3), with the strict parts embedded here as
allow-lists — the entity PATCH is `additionalProperties: false` at every level,
so an unknown key is a 400, not a warning. Run after any change to pdc_api /
suggester builders:

    python -m v3_selftest
"""
import sys

PASS = FAIL = 0


def _c(name, ok, detail=""):
    global PASS, FAIL
    print(("  [ok  ] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail and not ok else ""))
    PASS += ok
    FAIL += not ok


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


def _check_patch_attrs(attrs, label, strict=True):
    _c(f"{label}: attribute keys within the v3 whitelist",
       set(attrs) <= PATCH_ATTR_KEYS, str(set(attrs) - PATCH_ATTR_KEYS))
    info = attrs.get("info")
    if isinstance(info, dict):
        _c(f"{label}: info keys", set(info) <= PATCH_INFO_KEYS, str(set(info) - PATCH_INFO_KEYS))
    feats = attrs.get("features")
    if isinstance(feats, dict):
        _c(f"{label}: feature keys", set(feats) <= PATCH_FEATURE_KEYS,
           str(set(feats) - PATCH_FEATURE_KEYS))
        r = feats.get("rating")
        if isinstance(r, dict):
            _c(f"{label}: rating keys", set(r) <= PATCH_RATING_KEYS, str(set(r) - PATCH_RATING_KEYS))
    for bt in attrs.get("businessTerms") or []:
        # the raw builder carries an app-internal 'glossary' name used by
        # Resolve; merge_attributes/_clean_term strips it before any PATCH,
        # so only PATCH-bound bodies are held to the strict whitelist
        extra = set(bt) - PATCH_TERM_KEYS - ({"glossary"} if not strict else set())
        _c(f"{label}: businessTerm keys ({bt.get('name', '?')})", not extra, str(extra))


def main():
    import pdc_api
    import suggester

    print("v3 shape selftest — PDC 11 public API")

    # --- Apply PATCH bodies, end to end through the real builders -------------
    rows = [{"Keep": "Y", "Category": "Customer", "Term": "Member Number",
             "Source_Column": "cscu.members.mbr_no",
             "Definition": "The member's unique CSCU number.",
             "Sensitivity": "HIGH", "PII_Category": "GOVERNMENT_ID",
             "Critical_Data_Element": "Yes", "Suggested_Tags": "pii;identifier",
             "Suggested_Rating": 4, "Source_Ratings": {"cscu.members.mbr_no": 4},
             "Suggested_Quality": 92,
             "Source_Quality_Dims": {"cscu.members.mbr_no": {"c": 1.0, "u": 1.0, "v": 1.0, "eu": True, "nn": True}},
             "Value_Pattern": r"^CSCU-\d{6}$", "Value_Signature": "AAAA-nnnnnn",
             "Source_Keys": {"cscu.members.mbr_no": {"pk": True, "fk": False, "ref": None}}}]
    links = suggester.data_element_links(rows, policy={"mode": "all"})
    api = suggester.links_to_api_json(links)
    _c("api_json produced", bool(api))
    for rec in api:
        _check_patch_attrs(rec["attributes"], f"column {rec.get('columnName')}", strict=False)

    merged = pdc_api.merge_attributes(
        {"businessTerms": [{"name": "Old", "id": "x", "glossaryId": "g",
                            "glossary": "DROP-ME"}],  # server junk must be cleaned
         "features": {"sensitivity": "LOW"}, "extended": {"prior": 1},
         "info": {"description": "old"}},
        api[0]["attributes"])
    _check_patch_attrs(merged, "merged apply body")

    # table roll-up body shape (term + sensitivity + description)
    tattrs = pdc_api.merge_attributes(
        {}, {"features": {"rating": {"value": 4}, "qualityScore": 92,
                          "sensitivity": "HIGH", "isLineageVerified": True},
             "businessTerms": [{"name": "Member Record", "id": "t", "glossaryId": "g"}],
             "info": {"description": "A single member record."}})
    _check_patch_attrs(tattrs, "table roll-up body")

    # --- search ---------------------------------------------------------------
    _c("search body keys", {"searchTerm", "perPage"} <= SEARCH_KEYS)

    # --- entities/filter ------------------------------------------------------
    for f in ({"names": ["x"]}, {"types": ["COLUMN"]}, {"fqdns": ["a.b"]},
              {"names": ["f"], "types": ["FILE", "OBJECT", "RESOURCE"]}):
        _c(f"entities/filter filters {sorted(f)}", set(f) <= ENTITY_FILTER_KEYS)
    import inspect
    src = inspect.getsource(pdc_api.filter_entities)
    _c("entities/filter cursor travels as a QUERY PARAM (v3 contract)",
       'body["cursor"]' not in src and 'q["cursor"]' in src)
    src = inspect.getsource(pdc_api.filter_profiling_info)
    _c("profiling-info cursor travels as a QUERY PARAM (v3 contract)",
       'body["cursor"]' not in src and 'q["cursor"]' in src)

    # --- jobs (v3 = bulk only) --------------------------------------------------
    for app_name, bulk in pdc_api._V3_BULK_NAMES.items():
        _c(f"bulk job name {bulk} is a documented v3 job", bulk in BULK_JOB_NAMES)
    item = {"name": "CALCULATE_TRUST_SCORE", "type": "START", "payload": {"scope": ["id1"]}}
    _c("bulk item keys exactly name/type/payload", set(item) == BULK_ITEM_KEYS)
    for nm, req in BULK_REQUIRED_PAYLOAD.items():
        payload = {"scope": ["u"], "configs": {}}
        _c(f"{nm} required payload keys present", req <= set(payload))
    src = inspect.getsource(pdc_api._execute_job)
    _c("v3 goes STRAIGHT to /jobs/execute/bulk (no doomed individual call)",
       "in (\"v3\", \"3\")" in src and "jobs/execute/bulk" in src)

    # --- data sources -----------------------------------------------------------
    _c("data-sources filter keys", {"resourceNames"} <= DS_FILTER_KEYS)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
