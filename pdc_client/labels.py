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

Assigning a label to a specific entity is a separate mutation not yet
captured — create/read/delete of label DEFINITIONS is what ships here.
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


def create_label(base_url, token, name, values, item_type="Columns",
                 descriptions=None, verify_tls=True):
    """Create one data-label definition with its governed value set.
    Returns the new _id."""
    descriptions = descriptions or {}
    avail = [{"value": str(v),
              "description": str(descriptions.get(v, ""))}
             for v in values if str(v).strip()]
    d = gql(base_url, token,
            "mutation($r: CreateOneCustomPropertyInput!) {"
            " CustomPropertyCreateUnique(record: $r) { record { _id name } } }",
            {"r": {"scope": [item_type], "name": str(name),
                   "isDataLabel": True, "availableValues": avail}},
            verify_tls=verify_tls)
    rec = ((d.get("CustomPropertyCreateUnique") or {}).get("record")) or {}
    return rec.get("_id") or ""


def remove_label(base_url, token, label_id, verify_tls=True):
    """Delete a data-label definition by id (used by tests/cleanup)."""
    gql(base_url, token,
        "mutation($i: MongoID!) { CustomPropertyRemoveById(_id: $i) { record { _id } } }",
        {"i": str(label_id)}, verify_tls=verify_tls)
