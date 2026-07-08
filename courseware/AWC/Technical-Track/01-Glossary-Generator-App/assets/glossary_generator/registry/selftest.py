"""Offline checks for the app-side Registry writer. Run: python -m registry.selftest"""
from .bridge import build_registry, _slug
from .model import Sensitivity

_P, _F = [], []
def _c(name, ok): (_P if ok else _F).append(name); print(("  [ok  ] " if ok else "  [FAIL] ")+name)

def main():
    rows = [
        {"type":"term","Keep":"Y","Term":"Customer Account Number","Category":"Billing",
         "Sensitivity":"HIGH","PII_Category":"FINANCIAL","Suggested_Tags":["PII","Financial"]},
        {"type":"term","Keep":"Y","Term":"Meter Reading","Category":"Operations",
         "Sensitivity":"low","Suggested_Tags":"Usage; Operations"},
        {"type":"category","Keep":"Y","Term":"Billing"},
        {"type":"term","Keep":"N","Term":"Dropped","Category":"X","Sensitivity":"LOW"},
    ]
    reg = build_registry(rows, "Test")
    by = {c["concept"]: c for c in reg["concepts"]}
    _c("schema tag is classification-registry/1", reg["schema"] == "classification-registry/1")
    _c("only kept term rows become concepts (2)", len(reg["concepts"]) == 2)
    _c("category rows are skipped", "billing" not in by)
    _c("un-kept rows are skipped", "dropped" not in by)
    _c("slug normalises to snake_case", _slug("Customer Account Number") == "customer_account_number")
    _c("sensitivity preserved (HIGH)", by["customer_account_number"]["sensitivity"] == "HIGH")
    _c("lowercase sensitivity parsed (low -> LOW)", by["meter_reading"]["sensitivity"] == "LOW")
    _c("string tags split on ; and ,", by["meter_reading"]["tags"] == ["Usage", "Operations"])
    _c("PII_Category forces a PII tag", "PII" in by["customer_account_number"]["tags"])
    _c("term_id is null until reconcile", by["customer_account_number"]["term_id"] is None)
    _c("Sensitivity ordinal (HIGH>LOW)", Sensitivity.HIGH > Sensitivity.LOW)
    # glossary_id embed + resolve-time backfill
    import tempfile, os, json
    from .bridge import backfill_term_ids
    reg2 = build_registry([{"type":"term","Keep":"Y","Term":"Phone","Category":"Contact",
                            "Sensitivity":"HIGH","Suggested_Tags":["PII"]}], "G", glossary_id="gid-1")
    _c("glossary_id embedded at build time", reg2["glossary_id"] == "gid-1")
    fp = os.path.join(tempfile.gettempdir(), "reg_selftest.json")
    json.dump(reg2, open(fp, "w"))
    n = backfill_term_ids(fp, {"Phone": {"id": "t-1", "glossaryId": "gid-1"}})
    _c("backfill stamps resolved term_id (match by term_name)",
       n == 1 and json.load(open(fp))["concepts"][0]["term_id"] == "t-1")
    print(f"\n{len(_P)} passed, {len(_F)} failed")
    return 1 if _F else 0

if __name__ == "__main__":
    import sys; sys.exit(main())
