"""pdc_api.labels — PDC data labels over the catalog's GraphQL endpoint.

Field-mapped 2026-08-14 on a live PDC 11: labels are CUSTOM PROPERTIES with
isDataLabel=true, served by POST /graphql (bearer token works — no session
cookie needed). Discovered via a DevTools capture of the UI's own
getDataLabels query plus error-shape probing (introspection is disabled;
Apollo's "did you mean" suggestions name the real mutations):

  read    CustomPropertiesMany(filter: {isDataLabel, itemType})
  create  CustomPropertyCreateUnique(record: {scope: [String]!, name,
          isDataLabel, availableValues: [{value, description}]})
  update  CustomPropertyUpdateById
  delete  CustomPropertyRemoveById(_id)

Assignment (mapped live 2026-08-17, error-shape probing after the UI's
graphql filter never showed a write): it is NOT GraphQL at all — a label
value lands on an entity via the public REST API,

  PATCH /api/public/v3/entities/{entity_id}
        {"attributes": {"customProperties": [{"id": <definition _id>,
                                              "value": "<tier>"}]}}

and the array REPLACES wholesale (proven by clear-and-restore on a live
column), so assign_labels below is read-merge-write. The entity GET
carries the same array back under attributes.customProperties.
"""
from .core import _req, clean_base


def gql(base_url, token, query, variables=None, verify_tls=True, timeout=30):
    """POST one GraphQL operation; returns the `data` dict or raises on
    GraphQL errors (the transport 200s even for failures)."""
    out = _req("POST", clean_base(base_url) + "/graphql", token=token,
               body={"query": query, **({"variables": variables} if variables else {})},
               verify_tls=verify_tls, timeout=timeout)
    if isinstance(out, dict) and out.get("errors"):
        msgs = "; ".join(str(e.get("message", ""))[:160] for e in out["errors"][:3])
        raise RuntimeError(f"GraphQL: {msgs}")
    return (out or {}).get("data") or {}


def list_labels(base_url, token, item_type="Columns", verify_tls=True):
    """Existing data-label definitions for an item type: [{_id, name, values}]."""
    d = gql(base_url, token,
            "query($f: FilterFindManyCustomPropertyInput) {"
            " CustomPropertiesMany(filter: $f) {"
            "  _id name isDataLabel availableValues { value description } } }",
            {"f": {"isDataLabel": True, "itemType": item_type}},
            verify_tls=verify_tls)
    out = []
    for p in d.get("CustomPropertiesMany") or []:
        out.append({"_id": p.get("_id"), "name": p.get("name") or "",
                    "values": [v.get("value") for v in (p.get("availableValues") or [])
                               if v and v.get("value")]})
    return out


def create_label(base_url, token, name, values, item_types=None,
                 descriptions=None, scope=None, field_type="select",
                 blank_allowed=True, verify_tls=True):
    """Create one data-label definition with its governed value set.

    Field names proven against the live schema (error-shape probing +
    the UI's own Create Custom Property form): `itemTypes` is the
    Columns/Tables/Folders/Schema/Files checkboxes, `scope` is the
    hierarchy ("Data Canvas"), `fieldType` is lowercase "select" and the hierarchy maps to
    scope ["Entities"] (read off a UI-created record). Returns the new _id."""
    descriptions = descriptions or {}
    avail = [{"value": str(v),
              "description": str(descriptions.get(v, ""))}
             for v in values if str(v).strip()]
    d = gql(base_url, token,
            "mutation($r: CreateOneCustomPropertyInput!) {"
            " CustomPropertyCreateUnique(record: $r) { record { _id name } } }",
            {"r": {"scope": list(scope or ["Entities"]),
                   # the UI's own createProperty capture (user-provided,
                   # 2026-08-17) checks Columns+Folders+Files for PII Type —
                   # a label that can't land on files is half a label in a
                   # document-bearing estate
                   "itemTypes": list(item_types or ["Columns", "Folders", "Files"]),
                   "fieldType": str(field_type),
                   "defaultValue": "",
                   "isBlankAllowed": bool(blank_allowed),
                   "name": str(name),
                   "isDataLabel": True, "availableValues": avail}},
            verify_tls=verify_tls)
    rec = ((d.get("CustomPropertyCreateUnique") or {}).get("record")) or {}
    return rec.get("_id") or ""


def entity_labels(base_url, token, entity_id, verify_tls=True, timeout=30):
    """Current label assignments on one entity: [{"id", "value"}], where id
    is the label DEFINITION's _id. Empty list = nothing assigned."""
    url = clean_base(base_url) + f"/api/public/v3/entities/{entity_id}"
    out = _req("GET", url, token=token, verify_tls=verify_tls, timeout=timeout)
    d = (out or {}).get("data") or out or {}
    return [a for a in ((d.get("attributes") or {}).get("customProperties") or [])
            if isinstance(a, dict) and a.get("id")]


def assign_labels(base_url, token, entity_id, assignments, verify_tls=True,
                  timeout=30, valid_ids=None):
    """Assign label values to one entity, preserving whatever other labels
    are already on it — the PATCH replaces the customProperties array
    wholesale, so this reads, merges by definition id (new value wins), and
    writes back. `assignments`: [{"id": <definition _id>, "value": "..."}];
    a blank value REMOVES that label. `valid_ids` (an iterable of live
    definition ids) makes the merge an orphan sweep too: any existing
    assignment whose definition no longer resolves is dropped instead of
    being carried forward (W19 — a deleted family left ~160 columns wearing
    assignments no UI renders). Returns the array as written."""
    merged = {str(a["id"]): str(a.get("value") or "")
              for a in entity_labels(base_url, token, entity_id,
                                     verify_tls=verify_tls, timeout=timeout)}
    if valid_ids is not None:
        live = {str(i) for i in valid_ids}
        merged = {k: v for k, v in merged.items() if k in live}
    for a in assignments or []:
        if a and a.get("id"):
            merged[str(a["id"])] = str(a.get("value") or "")
    arr = [{"id": k, "value": v} for k, v in merged.items() if v]
    url = clean_base(base_url) + f"/api/public/v3/entities/{entity_id}"
    _req("PATCH", url, token=token,
         body={"attributes": {"customProperties": arr}},
         verify_tls=verify_tls, timeout=timeout)
    return arr


def remove_label(base_url, token, label_id, verify_tls=True):
    """Delete a data-label definition by id (used by tests/cleanup)."""
    gql(base_url, token,
        "mutation($i: MongoID!) { CustomPropertyRemoveById(_id: $i) { record { _id } } }",
        {"i": str(label_id)}, verify_tls=verify_tls)
