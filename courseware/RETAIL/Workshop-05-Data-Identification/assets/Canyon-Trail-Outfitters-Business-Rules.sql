-- =====================================================================
--  CANYON TRAIL OUTFITTERS  -  PENTAHO DATA CATALOG BUSINESS RULES
--  Data Quality Rules for the cto_retail schema
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
--    Rule 1 fails 3/3   (the planted privacy defect)
--    Rule 2 fails 6/6   (the planted PCI defect)
--    Rule 5 fails 1/25  (the over-policy clearance discount; the
--                        returns-policy audit notes the missing VP
--                        exception)
--    Rules 3, 4 and 6 pass - and keep watching on their schedule.
--
-- =====================================================================


-- =====================================================================
--  RULE 1  (the course flagship)
--  Name:       CTO-Marketing-OptOut-Compliance
--  Dimension:  Conformity        Table: cto_retail.customers
--  Intent:     Consumer privacy (CCPA-style) - a customer who has
--              OPTED OUT of marketing must not sit on a marketing
--              extract with a live email. Non-compliant = opted-out
--              customers that still carry a contactable email address
--              (the extract must exclude or suppress them).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN c.opted_out_marketing THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN c.opted_out_marketing
                  AND c.email IS NOT NULL
                  AND c.email <> ''            THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.customers c;


-- =====================================================================
--  RULE 2  (the planted PCI violation)
--  Name:       CTO-PCI-No-Full-PAN
--  Dimension:  Validity          Table: cto_retail.payments
--  Intent:     PCI DSS 3.2 - the full primary account number must NOT
--              be stored after authorization. Any card_no matching a
--              full 16-digit PAN shape is non-compliant (a tokenized
--              value or a last-4 suffix would not match). This rule
--              fails by design until the tokenization purge runs -
--              discussed in Workshop 5.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(p.card_no)                                    AS "scopeCount",
        SUM(CASE WHEN p.card_no ~ '^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.payments p;


-- =====================================================================
--  RULE 3
--  Name:       CTO-SKU-Format-Validity
--  Dimension:  Conformity        Table: cto_retail.products
--  Intent:     Every SKU must match CT-AAA-nnnn (category prefix and
--              four digits). In scope when present.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(p.sku)                                        AS "scopeCount",
        SUM(CASE WHEN p.sku IS NOT NULL
                  AND p.sku !~ '^CT-[A-Z]{3}-[0-9]{4}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.products p;


-- =====================================================================
--  RULE 4
--  Name:       CTO-Refund-Not-Above-Order
--  Dimension:  Consistency       Table: cto_retail.returns
--  Intent:     A refund can never exceed the total of the order it
--              came from.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN r.refund_amt > o.total_amt
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.returns r
JOIN    cto_retail.orders  o ON o.order_id = r.order_id;


-- =====================================================================
--  RULE 5  (fails 1/25 by design)
--  Name:       CTO-Discount-Within-Policy
--  Dimension:  Validity          Table: cto_retail.order_items
--  Intent:     Company policy caps line discounts at 40%; anything
--              above requires a VP exception on file. The shipped data
--              carries one 50% clearance line whose exception is
--              missing (see the returns-policy audit in the document
--              store) - so this rule reports one non-compliant row.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN i.discount_pct < 0
                   OR i.discount_pct > 40      THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.order_items i;


-- =====================================================================
--  RULE 6
--  Name:       CTO-Inventory-Not-Negative
--  Dimension:  Consistency       Table: cto_retail.inventory
--  Intent:     On-hand stock can never be negative; a negative value
--              is a count error that must be investigated.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN v.qty_on_hand < 0        THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cto_retail.inventory v;
