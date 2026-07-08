-- =====================================================================
--  ARIZONA WATER COMPANY  -  PENTAHO DATA CATALOG BUSINESS RULES
--  Data Quality Rules for the awc_operations schema
--  PDC 10.2.11  |  Business Analyst Happy Path course
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
--  The canonical PDC example (from the Chinook sample) is:
--
--    SELECT  count(*)            total_count,
--            count(c."Fax")      scopeCount,
--            SUM(CASE WHEN c."Fax" isnull THEN 1 ELSE 0 END) nonCompliant
--    FROM    chinook."Customer" c
--
--  Each rule below follows that exact shape so it can be pasted into
--  the "Set the rule scope and condition" SQL box on the Business Rule
--  Configuration tab.
--
--  CONFIGURING EACH RULE IN PDC
--  ---------------------------------------------------------------
--    1.  Data Operations  ->  Business Rules card  ->  Business Rules
--    2.  Add Business Rule  ->  enter the Name shown for each rule
--        (letters, digits, hyphens, underscores; spaces allowed but
--         no trailing spaces)
--    3.  Create Business Rule  ->  Configure
--    4.  Set the Business Rule Type and the Data Quality Dimension
--        (Accuracy, Uniqueness, Consistency, Timeliness, Conformity,
--         Completeness, or Validity)
--    5.  Set the Schedule (Daily / Weekly / Monthly)
--    6.  Set the rule scope (target table/column) and paste the SQL
--    7.  Add Actions: Set Status (PASS/WARNING/FAIL thresholds),
--        Apply Tags, and/or Webhook
--    8.  Save Changes  ->  Run Now  ->  monitor on the Workers page
--
--  The recommended threshold for each rule is given in its header as a
--  percentage of nonCompliant / scopeCount.
-- =====================================================================


-- =====================================================================
--  RULE 1  -  AWC-Marketing-OptOut-Compliance        ** FLAGSHIP **
--  Dimension : Validity            Schedule : Daily
--  Scope     : awc_operations.customers
--  Thresholds: PASS = 0%   WARNING > 0%   FAIL >= 1 row
--  Purpose   : The GDPR / CCPA opt-out scenario. Finds customers who
--              opted OUT of marketing but still hold a contactable
--              email, i.e. anyone who could wrongly receive a campaign.
--              FAIL on a single offending row - this is a hard control.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.email)                                  AS scopeCount,
    SUM(CASE
            WHEN c.opted_out_marketing = TRUE
             AND c.email IS NOT NULL
             AND c.account_status = 'Active'
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c;


-- =====================================================================
--  RULE 2  -  AWC-Customer-Email-Validity
--  Dimension : Validity            Schedule : Weekly
--  Scope     : awc_operations.customers.email
--  Thresholds: PASS <= 2%   WARNING 2-5%   FAIL > 5%
--  Purpose   : Flags email values that do not match a basic email
--              pattern (e.g. bob@invalid, david.brown@company). These
--              are undeliverable and depress the customers quality
--              score below 100%.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.email)                                  AS scopeCount,
    SUM(CASE
            WHEN c.email IS NOT NULL
             AND c.email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c;


-- =====================================================================
--  RULE 3  -  AWC-Account-Number-Conformity
--  Dimension : Conformity          Schedule : Weekly
--  Scope     : awc_operations.customers.account_number
--  Thresholds: PASS = 0%   WARNING 0-1%   FAIL > 1%
--  Purpose   : Enforces the AWC account-number standard AWC-XX-######
--              (two-letter system code, six digits). Non-conforming
--              identifiers break joins and downstream billing.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.account_number)                         AS scopeCount,
    SUM(CASE
            WHEN c.account_number IS NULL
              OR c.account_number !~ '^AWC-[A-Z]{2}-[0-9]{6}$'
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c;


-- =====================================================================
--  RULE 4  -  AWC-Account-Number-Uniqueness
--  Dimension : Uniqueness          Schedule : Weekly
--  Scope     : awc_operations.customers.account_number
--  Thresholds: PASS = 0%   WARNING n/a   FAIL >= 1 duplicate
--  Purpose   : account_number must be unique. Counts rows that share a
--              duplicated account_number. A single duplicate FAILs.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.account_number)                         AS scopeCount,
    COALESCE(SUM(dup.cnt - 1), 0)                   AS nonCompliant
FROM awc_operations.customers c
LEFT JOIN (
    SELECT account_number, count(*) AS cnt
    FROM   awc_operations.customers
    WHERE  account_number IS NOT NULL
    GROUP BY account_number
    HAVING count(*) > 1
) dup ON dup.account_number = c.account_number;


-- =====================================================================
--  RULE 5  -  AWC-Customer-PII-Completeness
--  Dimension : Completeness        Schedule : Weekly
--  Scope     : awc_operations.customers
--  Thresholds: PASS <= 5%   WARNING 5-10%   FAIL > 10%
--  Purpose   : Active customers should have a reachable contact method.
--              Flags ACTIVE customers missing BOTH email and phone.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    SUM(CASE WHEN c.account_status = 'Active'
             THEN 1 ELSE 0 END)                     AS scopeCount,
    SUM(CASE
            WHEN c.account_status = 'Active'
             AND (c.email IS NULL OR c.email = '')
             AND (c.phone IS NULL OR c.phone = '')
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c;


-- =====================================================================
--  RULE 6  -  AWC-Billing-Total-Consistency
--  Dimension : Consistency         Schedule : Monthly
--  Scope     : awc_operations.monthly_usage
--  Thresholds: PASS = 0%   WARNING 0-1%   FAIL > 1%
--  Purpose   : The stored total_due must equal the sum of its parts:
--              base + tiered charges + wastewater + tax. Flags any bill
--              whose components do not reconcile (tolerance 1 cent).
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(m.total_due)                              AS scopeCount,
    SUM(CASE
            WHEN ABS(
                 m.total_due - (
                     COALESCE(m.base_charge,0)
                   + COALESCE(m.tier_1_charge,0)
                   + COALESCE(m.tier_2_charge,0)
                   + COALESCE(m.tier_3_charge,0)
                   + COALESCE(m.tier_4_charge,0)
                   + COALESCE(m.wastewater_charge,0)
                   + COALESCE(m.tax_amount,0)
                 )
            ) > 0.01
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.monthly_usage m;


-- =====================================================================
--  RULE 7  -  AWC-Usage-Tier-Consistency
--  Dimension : Consistency         Schedule : Monthly
--  Scope     : awc_operations.monthly_usage
--  Thresholds: PASS = 0%   WARNING 0-2%   FAIL > 2%
--  Purpose   : The four tier gallon buckets must sum to total usage.
--              Flags rows where tier_1..4 gallons != usage_gallons.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(m.usage_gallons)                          AS scopeCount,
    SUM(CASE
            WHEN m.usage_gallons <> (
                     COALESCE(m.usage_tier_1_gallons,0)
                   + COALESCE(m.usage_tier_2_gallons,0)
                   + COALESCE(m.usage_tier_3_gallons,0)
                   + COALESCE(m.usage_tier_4_gallons,0)
                 )
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.monthly_usage m;


-- =====================================================================
--  RULE 8  -  AWC-Overdue-Payment-Timeliness
--  Dimension : Timeliness          Schedule : Daily
--  Scope     : awc_operations.monthly_usage
--  Thresholds: PASS <= 5%   WARNING 5-15%   FAIL > 15%
--  Purpose   : Surfaces bills past their due date that remain unpaid.
--              Drives the collections worklist and the account_alerts
--              "Payment Overdue" entries.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    SUM(CASE WHEN m.payment_status IN ('Unpaid','Overdue','Disputed')
             THEN 1 ELSE 0 END)                     AS scopeCount,
    SUM(CASE
            WHEN m.payment_status IN ('Unpaid','Overdue','Disputed')
             AND m.due_date < CURRENT_DATE
             AND COALESCE(m.amount_paid,0) < m.total_due
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.monthly_usage m;


-- =====================================================================
--  RULE 9  -  AWC-Referential-Integrity-Customer-System
--  Dimension : Accuracy            Schedule : Weekly
--  Scope     : awc_operations.customers
--  Thresholds: PASS = 0%   WARNING n/a   FAIL >= 1 row
--  Purpose   : Every customer's service_area_system must reference a
--              real water_systems.system_name. Flags orphaned customers
--              whose service area does not exist in water_systems.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.service_area_system)                    AS scopeCount,
    SUM(CASE
            WHEN c.service_area_system IS NOT NULL
             AND ws.system_name IS NULL
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c
LEFT JOIN awc_operations.water_systems ws
       ON ws.system_name = c.service_area_system;


-- =====================================================================
--  RULE 10 -  AWC-Water-Quality-EPA-Compliance
--  Dimension : Validity            Schedule : Daily
--  Scope     : awc_operations.water_quality_reports
--  Thresholds: PASS = 0%   WARNING 0%   FAIL >= 1 violation
--  Purpose   : Mirrors data quality as regulatory quality. Flags any
--              monitoring report that breaches an EPA limit:
--                turbidity >= 0.5 NTU, lead > 15 ppb,
--                or bacteria present. FAIL on any single breach.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(q.report_id)                              AS scopeCount,
    SUM(CASE
            WHEN q.turbidity_ntu >= 0.5
              OR q.lead_ppb      > 15
              OR q.bacteria_present = TRUE
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.water_quality_reports q;


-- =====================================================================
--  RULE 11 -  AWC-Customer-Status-Validity
--  Dimension : Validity            Schedule : Weekly
--  Scope     : awc_operations.customers.account_status
--  Thresholds: PASS = 0%   WARNING 0-1%   FAIL > 1%
--  Purpose   : account_status must be drawn from the controlled
--              vocabulary. Flags any value outside the allowed set.
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(c.account_status)                         AS scopeCount,
    SUM(CASE
            WHEN c.account_status IS NULL
              OR c.account_status NOT IN
                 ('Active','Suspended','Closed','Pending')
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.customers c;


-- =====================================================================
--  RULE 12 -  AWC-Suspended-Account-Billing-Consistency
--  Dimension : Consistency         Schedule : Monthly
--  Scope     : awc_operations.monthly_usage
--  Thresholds: PASS = 0%   WARNING 0-2%   FAIL > 2%
--  Purpose   : Suspended/closed accounts should not accrue NEW unpaid
--              usage charges. Flags bills for non-active customers that
--              still carry a positive balance due. (e.g. the Bisbee Inn
--              suspended-account scenario.)
-- =====================================================================
SELECT
    count(*)                                        AS total_count,
    count(m.usage_id)                               AS scopeCount,
    SUM(CASE
            WHEN c.account_status IN ('Suspended','Closed')
             AND m.payment_status IN ('Unpaid','Overdue')
             AND m.total_due > 0
            THEN 1 ELSE 0
        END)                                        AS nonCompliant
FROM awc_operations.monthly_usage m
JOIN awc_operations.customers c
  ON c.customer_id = m.customer_id;


-- =====================================================================
--  END OF AWC BUSINESS RULES
--  12 rules covering all 7 PDC data-quality dimensions:
--    Validity     : Rules 1, 2, 10, 11
--    Conformity   : Rule 3
--    Uniqueness   : Rule 4
--    Completeness : Rule 5
--    Consistency  : Rules 6, 7, 12
--    Timeliness   : Rule 8
--    Accuracy     : Rule 9
-- =====================================================================
