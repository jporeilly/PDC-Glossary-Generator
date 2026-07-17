"""
pdc_api.py - PDC Public API client.

Two jobs:
  1. RESOLVE  - look up each business term by name -> {id, glossaryId} and stamp
                the ids into the Data Elements JSON (so it is POST-able to
                /data-collections).
  2. APPLY    - for each kept term<->column association, resolve the column's
                entity id, MERGE the new businessTerms + features into whatever
                the column already carries, and PATCH it back into PDC. Supports
                a dry-run that returns every planned PATCH (id + body) without
                sending, then an apply mode that reports per-column pass/fail.
                Optionally kicks off Calculate Trust Score on the touched ids.
  3. PROFILE  - pull PDC's own profiling stats for a set of columns so the app's
                discovery panel can show app-vs-PDC side by side.

Grounded in the PDC Public API (confirmed from the instance Swagger):
  - Auth:    POST /api/public/<v>/auth   (form) -> {data:{accessToken}}
  - Search:  POST /api/public/<v>/search ({searchTerm, searchFacets:{type:["term"]}})
             a term hit carries its own _id (term id) and rootId (its glossary).
  - Filter:  POST /api/public/<v>/entities/filter?extended=true&size=500
             body {"filters": {...}} - at least one of:
               fqdns | names | types | parentIds | rootIds | resourceIds |
               collectionIds | buckets | profileStatus | profiledAt
             response {status, data:[ {_id, name, type, fqdn, fqdnDisplay,
               parentId, rootId, resourceId, resourceName, attributes, ...} ]}
  - Patch:   PATCH /api/public/<v>/entities/{_id}   body {"attributes": {...}}
             server semantics: arrays full-replace, scalars overwrite, object
             keys merge -> so we send the already-merged businessTerms superset.
  - Profile: POST /api/public/<v>/entities/filter/profiling-info?sampleLimit=N
             same filters body; each item adds nested profilingInfo.stats.
  - Trust:   POST /api/public/<v>/jobs/execute/calculate-trust-score {"scope":[ids]}
             poll GET /api/public/<v>/jobs/{id}/status
"""

# The single-module pdc_api.py became this package (same file layout
# rules as the original: transport/auth in core, then terms, entities,
# apply, jobs, bulkload — each may only lean on earlier modules).
# Everything is re-exported here so `import pdc_api` keeps working
# unchanged for app.py and v3_selftest.py.
from .core import (
    TokenExpired,
    _REALM_RE,
    _bt_match,
    _ctx,
    _cursor,
    _eid,
    _glossary_id,
    _post,
    _req,
    _results,
    auth,
    clean_base,
    decode_jwt,
    keycloak_auth,
    pdc_api_auth,
    split_base,
)
from .terms import (
    diagnose_terms,
    fuzzy_term_candidates,
    resolve_terms,
    stamp_ids,
)
from .entities import (
    _COL_TYPES,
    _FILE_TYPES,
    _ROOT_TYPES,
    _TBL_TYPES,
    _aget,
    _attrs_of,
    _col_meta,
    _file_record,
    _norm_data_source,
    _path_text,
    _resolve_object_entity,
    _source_match,
    _split_entity_path,
    _under_root,
    filter_entities,
    get_entity,
    glossary_exists,
    harvest_from_catalog,
    list_catalog_roots,
    resolve_column_entity,
    resolve_table_entity,
)
from .apply import (
    _BT_KEYS,
    _SENS_DN,
    _SENS_UP,
    _clean_term,
    _retry_auth,
    _term_key,
    apply_to_pdc,
    merge_attributes,
)
from .jobs import (
    _DISCOVERY_DEFAULTS,
    _JOB_BAD,
    _JOB_OK,
    _SECRET_KEYS,
    _V3_BULK_NAMES,
    _execute_job,
    calculate_trust_score,
    filter_profiling_info,
    job_status,
    pdc_profile_for_columns,
    profiled_snapshot,
    resolve_document_scope,
    trigger_data_discovery,
)
from .bulkload import (
    CSV_COLUMNS,
    _SECRET_CSV_COLS,
    _TYPE_TO_KIND,
    _ingest_body,
    _nonempty,
    _split_list,
    build_data_source_body,
    bulk_load_one,
    connections_to_csv,
    create_data_source,
    delete_data_source,
    find_existing_data_source,
    get_data_source,
    internal_scan_files,
    list_data_sources,
    parse_csv_rows,
    redact_secrets,
    run_job,
    wait_job,
)
