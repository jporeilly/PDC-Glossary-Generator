-- =====================================================================
--  CASCADE PRECISION COMPONENTS  -  PENTAHO DATA CATALOG BUSINESS RULES
--  Data Quality Rules for the cpc_mfg schema
--  PDC 11.0.0  |  Business Analyst Happy Path course
-- =====================================================================
--
--  HOW PDC BUSINESS RULES WORK
--  ---------------------------------------------------------------
--  In Pentaho Data Catalog, a Business Rule is a hierarchical layer
--  above one or more SQL "data quality rules". Each SQL condition is
--  written to return THREE aggregate columns, which the Rules Engine
--  uses to evaluate compliance and set a PASS / WARNING / FAIL status:
--
--    total_count   -  the total number of rows examined
--    scopeCount    -  the number of rows actually IN SCOPE for the rule
--    nonCompliant  -  the number of in-scope rows that FAIL the rule
--
--  Each rule below follows that exact shape so it can be pasted into
--  the "Set the rule scope and condition" SQL box on the Business Rule
--  Configuration tab.
--
--  CONFIGURING EACH RULE IN PDC
--  ---------------------------------------------------------------
--    1.  Data Operations  ->  Business Rules card  ->  Business Rules
--    2.  Add Business Rule  ->  enter the Name shown for each rule
--    3.  Create Business Rule  ->  Configure
--    4.  Set the Business Rule Type and the Data Quality Dimension
--        (Accuracy, Uniqueness, Consistency, Timeliness, Conformity,
--         Completeness, or Validity)
--    5.  Set the Schedule (Daily / Weekly / Monthly)
--    6.  Set the rule scope (target table/column) and paste the SQL
--
--  EXPECTED RESULTS ON THE SHIPPED DATA
--  ---------------------------------------------------------------
--    Rule 1 fails 2/15  (Released/Consumed/Recalled lots without CoC)
--    Rule 2 fails 1/1   (NCR-2026-014: USE_AS_IS on CRITICAL, no MRB)
--    Rule 3 fails 1/2   (PO-30000112 issued after the suspension)
--    Rules 4, 5 and 6 pass - and keep watching on their schedule.
--
-- =====================================================================


-- =====================================================================
--  RULE 1  (the course flagship - traceability)
--  Name:       CPC-Lot-CoC-Before-Release
--  Dimension:  Conformity        Table: cpc_mfg.lots
--  Intent:     AS9100 traceability - a lot must not leave Quarantine
--              without a Certificate of Conformance on file. In scope =
--              lots in Released, Consumed or Recalled status;
--              non-compliant = in scope without the CoC flag. This rule
--              fails by design until the certificate remediation runs -
--              discussed in Workshop 5.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN l.lot_status IN ('Released','Consumed','Recalled')
                                               THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN l.lot_status IN ('Released','Consumed','Recalled')
                  AND NOT l.coc_flag           THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.lots l;


-- =====================================================================
--  RULE 2  (the planted MRB violation)
--  Name:       CPC-Critical-NCR-MRB-Approval
--  Dimension:  Validity          Table: cpc_mfg.ncrs
--  Intent:     AS9100 8.7 - USE_AS_IS on MAJOR or CRITICAL severity
--              requires Material Review Board sign-off. In scope =
--              USE_AS_IS dispositions at those severities;
--              non-compliant = in scope without the MRB flag
--              (NCR-2026-014 is the planted violation the internal
--              audit also reports).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN n.disposition_cd = 'USE_AS_IS'
                  AND n.severity_cd IN ('MAJOR','CRITICAL')
                                               THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN n.disposition_cd = 'USE_AS_IS'
                  AND n.severity_cd IN ('MAJOR','CRITICAL')
                  AND NOT n.mrb_approval_flag  THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.ncrs n;


-- =====================================================================
--  RULE 3  (the planted ASL violation)
--  Name:       CPC-No-PO-To-Suspended-Supplier
--  Dimension:  Conformity        Tables: purchase_orders + suppliers
--  Intent:     A Suspended supplier must receive no new purchase
--              orders. In scope = POs whose supplier is currently
--              Suspended; non-compliant = those ordered on or after the
--              suspension date (PO-30000112 is the planted violation
--              the expedite-email thread documents).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN s.asl_status = 'Suspended'
                                               THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN s.asl_status = 'Suspended'
                  AND po.order_dt >= s.status_dt
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.purchase_orders po
JOIN    cpc_mfg.suppliers s ON s.supplier_id = po.supplier_id;


-- =====================================================================
--  RULE 4
--  Name:       CPC-PartNo-Format-Validity
--  Dimension:  Conformity        Table: cpc_mfg.parts
--  Intent:     Every part number must match CPC-nnnnn. In scope when
--              present.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(p.part_no)                                    AS "scopeCount",
        SUM(CASE WHEN p.part_no IS NOT NULL
                  AND p.part_no !~ '^CPC-[0-9]{5}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.parts p;


-- =====================================================================
--  RULE 5
--  Name:       CPC-WO-Quantity-Consistency
--  Dimension:  Consistency       Table: cpc_mfg.work_orders
--  Intent:     Completed plus scrapped units can never exceed the
--              planned quantity.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN w.qty_completed + w.qty_scrapped > w.qty_planned
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.work_orders w;


-- =====================================================================
--  RULE 6
--  Name:       CPC-Inspection-Sample-Within-Lot
--  Dimension:  Consistency       Tables: inspections + lots
--  Intent:     An inspection sample can never exceed the size of the
--              lot it samples.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN i.sample_qty > l.qty     THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cpc_mfg.inspections i
JOIN    cpc_mfg.lots l ON l.lot_id = i.lot_id;
