-- =====================================================================
--  COPPER STATE CREDIT UNION  -  PENTAHO DATA CATALOG BUSINESS RULES
--  Data Quality Rules for the cscu_core schema
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
-- =====================================================================


-- =====================================================================
--  RULE 1  (the course flagship)
--  Name:       CSCU-Marketing-OptOut-Compliance
--  Dimension:  Conformity        Table: cscu_core.members
--  Intent:     GDPR/CCPA - a member who has OPTED OUT of marketing
--              must not sit on a marketing extract with a live email.
--              Non-compliant = opted-out members that still carry a
--              contactable email address (the extract must exclude
--              or suppress them).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN m.opted_out_marketing THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN m.opted_out_marketing
                  AND m.email IS NOT NULL
                  AND m.email <> ''            THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.members m;


-- =====================================================================
--  RULE 2  (the planted PCI violation)
--  Name:       CSCU-PCI-No-Stored-CVV
--  Dimension:  Validity          Table: cscu_core.cards
--  Intent:     PCI DSS 3.2 - card verification values must NOT be
--              stored after authorization. ANY populated cvv_cd row
--              is non-compliant. This rule fails by design until the
--              remediation purge runs - discussed in Workshop 5.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN c.cvv_cd IS NOT NULL
                  AND c.cvv_cd <> ''           THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.cards c;


-- =====================================================================
--  RULE 3
--  Name:       CSCU-SSN-Format-Validity
--  Dimension:  Conformity        Table: cscu_core.members
--  Intent:     SSN must match NNN-NN-NNNN. In scope when present.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(m.ssn)                                        AS "scopeCount",
        SUM(CASE WHEN m.ssn IS NOT NULL
                  AND m.ssn !~ '^[0-9]{3}-[0-9]{2}-[0-9]{4}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.members m;


-- =====================================================================
--  RULE 4
--  Name:       CSCU-Available-Not-Above-Ledger
--  Dimension:  Consistency       Table: cscu_core.accounts
--  Intent:     Available balance can never exceed the ledger balance.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN a.avail_bal_amt > a.bal_amt
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.accounts a
WHERE   a.acct_status = 'Open';


-- =====================================================================
--  RULE 5
--  Name:       CSCU-APR-Within-Program-Limits
--  Dimension:  Validity          Table: cscu_core.loans
--  Intent:     Reg-Z sanity - APR must sit between 0% and 36% on any
--              loan that is not paid off.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN l.ln_status <> 'PaidOff' THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN l.ln_status <> 'PaidOff'
                  AND (l.apr_rt <= 0 OR l.apr_rt > 0.36)
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.loans l;


-- =====================================================================
--  RULE 6
--  Name:       CSCU-ACH-Routing-Number-Format
--  Dimension:  Conformity        Table: cscu_core.ach_payments
--  Intent:     An ABA routing number is exactly nine digits.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(p.ach_rte_no)                                 AS "scopeCount",
        SUM(CASE WHEN p.ach_rte_no IS NOT NULL
                  AND p.ach_rte_no !~ '^[0-9]{9}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    cscu_core.ach_payments p;


-- =====================================================================
--  All Copper State Credit Union data is fictional - training only.
-- =====================================================================
