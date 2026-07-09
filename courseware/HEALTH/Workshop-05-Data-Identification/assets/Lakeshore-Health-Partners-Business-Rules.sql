-- =====================================================================
--  LAKESHORE HEALTH PARTNERS  -  PENTAHO DATA CATALOG BUSINESS RULES
--  Data Quality Rules for the lhp_clinical schema
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
--    Rule 2 fails 2/14  (SSNs leaked into clinical notes)
--    Rule 3 fails 1/2   (the marketing disclosure without authorization)
--    Rules 4, 5 and 6 pass - and keep watching on their schedule.
--
-- =====================================================================


-- =====================================================================
--  RULE 1  (the course flagship)
--  Name:       LHP-Marketing-OptOut-Compliance
--  Dimension:  Conformity        Table: lhp_clinical.patients
--  Intent:     HIPAA - marketing use of PHI requires authorization,
--              and a patient who has OPTED OUT must not sit on a
--              marketing extract with a live email. Non-compliant =
--              opted-out patients that still carry a contactable email
--              address (the extract must exclude or suppress them).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN p.mkt_optout THEN 1 ELSE 0 END)       AS "scopeCount",
        SUM(CASE WHEN p.mkt_optout
                  AND p.email IS NOT NULL
                  AND p.email <> ''            THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.patients p;


-- =====================================================================
--  RULE 2  (the planted PHI leak)
--  Name:       LHP-No-SSN-In-Clinical-Notes
--  Dimension:  Validity          Table: lhp_clinical.encounters
--  Intent:     Identifiers must never be documented in free-text
--              clinical notes. Any note matching an SSN shape
--              (NNN-NN-NNNN) is non-compliant. This rule fails by
--              design until the redaction remediation runs -
--              discussed in Workshop 5.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(e.note_txt)                                   AS "scopeCount",
        SUM(CASE WHEN e.note_txt ~ '[0-9]{3}-[0-9]{2}-[0-9]{4}'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.encounters e;


-- =====================================================================
--  RULE 3  (the planted disclosure violation)
--  Name:       LHP-Disclosure-Authorization
--  Dimension:  Conformity        Table: lhp_clinical.disclosure_log
--  Intent:     HIPAA - MARKETING and RESEARCH disclosures require a
--              signed authorization on file. In scope = disclosures
--              with those purposes; non-compliant = in scope without
--              the authorization flag (entry 30005 is the planted
--              violation the privacy audit also reports).
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        SUM(CASE WHEN d.purpose_cd IN ('MARKETING','RESEARCH')
                                               THEN 1 ELSE 0 END) AS "scopeCount",
        SUM(CASE WHEN d.purpose_cd IN ('MARKETING','RESEARCH')
                  AND NOT d.authorization_flag THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.disclosure_log d;


-- =====================================================================
--  RULE 4
--  Name:       LHP-MRN-Format-Validity
--  Dimension:  Conformity        Table: lhp_clinical.patients
--  Intent:     Every MRN must match LHP-nnnnnn. In scope when present.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(p.mrn)                                        AS "scopeCount",
        SUM(CASE WHEN p.mrn IS NOT NULL
                  AND p.mrn !~ '^LHP-[0-9]{6}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.patients p;


-- =====================================================================
--  RULE 5
--  Name:       LHP-NPI-Format-Validity
--  Dimension:  Conformity        Table: lhp_clinical.providers
--  Intent:     Every provider must carry a 10-digit NPI.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(pr.npi_no)                                    AS "scopeCount",
        SUM(CASE WHEN pr.npi_no IS NOT NULL
                  AND pr.npi_no !~ '^[0-9]{10}$'
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.providers pr;


-- =====================================================================
--  RULE 6
--  Name:       LHP-Paid-Not-Above-Billed
--  Dimension:  Consistency       Table: lhp_clinical.claims
--  Intent:     A payer can never pay (or allow) more than was billed.
-- =====================================================================
SELECT  count(*)                                            AS total_count,
        count(*)                                            AS "scopeCount",
        SUM(CASE WHEN c.paid_amt    > c.billed_amt
                   OR c.allowed_amt > c.billed_amt
                                               THEN 1 ELSE 0 END) AS "nonCompliant"
FROM    lhp_clinical.claims c;
