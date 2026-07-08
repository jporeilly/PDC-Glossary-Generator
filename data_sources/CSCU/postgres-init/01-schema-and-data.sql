-- ==========================================
-- PDC Business Analyst Course
-- Sample Data: Copper State Credit Union (CSCU)
-- Fictional Arizona credit union - core banking
-- ==========================================

CREATE SCHEMA IF NOT EXISTS cscu_core;
SET search_path TO cscu_core;

-- ==========================================
-- Table 1: branches (CSCU branch network)
-- ==========================================
CREATE TABLE branches (
    br_id INT PRIMARY KEY,
    br_name VARCHAR(100) NOT NULL UNIQUE,
    br_addr VARCHAR(200),
    br_city VARCHAR(50),
    br_county VARCHAR(30),
    br_zip VARCHAR(10),
    br_phone VARCHAR(20),
    mgr_emp_id INT,                      -- manager (FK added after employees)
    open_dt DATE,
    br_status VARCHAR(20) DEFAULT 'Open' -- Open, Closed, Relocating
);

INSERT INTO branches VALUES
(10, 'Phoenix Camelback',   '2201 E Camelback Rd',  'Phoenix',     'Maricopa', '85016', '602-555-0110', NULL, '1998-04-12', 'Open'),
(20, 'Tempe University',    '798 S Mill Ave',       'Tempe',       'Maricopa', '85281', '480-555-0120', NULL, '2004-09-01', 'Open'),
(30, 'Tucson Speedway',     '4550 E Speedway Blvd', 'Tucson',      'Pima',     '85712', '520-555-0130', NULL, '2001-06-18', 'Open'),
(40, 'Casa Grande Plaza',   '1355 E Florence Blvd', 'Casa Grande', 'Pinal',    '85122', '520-555-0140', NULL, '2012-02-27', 'Open');

-- ==========================================
-- Table 2: employees (branch staff)
-- ==========================================
CREATE TABLE employees (
    emp_id INT PRIMARY KEY,
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    br_id INT NOT NULL REFERENCES branches(br_id),
    role_cd VARCHAR(30),                 -- TELLER, MSR, LOAN_OFFICER, BR_MGR, COMPLIANCE
    hire_dt DATE,
    emp_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO employees VALUES
(901, 'Elena',  'Ramirez',  'elena.ramirez@copperstatecu.org', 10, 'BR_MGR',       '2015-03-02', 'Active'),
(902, 'Marcus', 'Webb',     'marcus.webb@copperstatecu.org',   10, 'LOAN_OFFICER', '2017-08-14', 'Active'),
(903, 'Priya',  'Nair',     'priya.nair@copperstatecu.org',    10, 'COMPLIANCE',   '2016-01-25', 'Active'),
(904, 'Tom',    'Callahan', 'tom.callahan@copperstatecu.org',  20, 'BR_MGR',       '2011-11-07', 'Active'),
(905, 'Dana',   'Ortiz',    'dana.ortiz@copperstatecu.org',    30, 'MSR',          '2019-06-03', 'Active'),
(906, 'Sam',    'Whitfield','sam.whitfield@copperstatecu.org', 40, 'TELLER',       '2022-02-21', 'Active');

ALTER TABLE branches
    ADD CONSTRAINT fk_branches_mgr FOREIGN KEY (mgr_emp_id) REFERENCES employees(emp_id);
UPDATE branches SET mgr_emp_id = 901 WHERE br_id = 10;
UPDATE branches SET mgr_emp_id = 904 WHERE br_id = 20;

-- ==========================================
-- Table 3: members (the credit-union member master file)
-- Deliberately cryptic column names - the glossary
-- generator's abbreviation expansion is part of the lab.
-- ==========================================
CREATE TABLE members (
    mbr_id INT PRIMARY KEY,
    mbr_no VARCHAR(20) NOT NULL UNIQUE,  -- member number CSCU-NNNNNN
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    ssn VARCHAR(11),                     -- fictional 000-xx-xxxx values only
    dob DATE,
    email VARCHAR(100),
    phone VARCHAR(20),
    addr_1 VARCHAR(200),
    city VARCHAR(50),
    st VARCHAR(2),
    zip VARCHAR(10),
    br_id INT REFERENCES branches(br_id),
    mbr_since_dt DATE,
    mbr_status VARCHAR(20) DEFAULT 'Active',  -- Active, Dormant, Closed
    opted_out_marketing BOOLEAN DEFAULT FALSE
);

INSERT INTO members VALUES
(5001, 'CSCU-100501', 'James',   'Porter',   '000-52-1147', '1978-02-11', 'james.porter@email.com',   '602-555-0201', '1832 W Osborn Rd',    'Phoenix',     'AZ', '85015', 10, '2009-05-14', 'Active', FALSE),
(5002, 'CSCU-100502', 'Alicia',  'Mendoza',  '000-63-8820', '1985-09-30', 'alicia.mendoza@email.com', '602-555-0202', '4419 N 16th St',      'Phoenix',     'AZ', '85016', 10, '2013-01-22', 'Active', TRUE),
(5003, 'CSCU-100503', 'Derek',   'Huang',    '000-71-3395', '1992-06-04', 'derek.huang@email.com',    '480-555-0203', '215 E Apache Blvd',   'Tempe',       'AZ', '85281', 20, '2018-08-30', 'Active', FALSE),
(5004, 'CSCU-100504', 'Sofia',   'Reyes',    '000-44-9012', '1969-12-19', 'sofia.reyes@email.com',    '480-555-0204', '901 S Rural Rd',      'Tempe',       'AZ', '85281', 20, '2006-03-11', 'Active', TRUE),
(5005, 'CSCU-100505', 'Nathan',  'Brooks',   '000-38-5566', '1988-04-25', 'nathan.brooks@email.com',  '520-555-0205', '3702 E 5th St',       'Tucson',      'AZ', '85716', 30, '2015-10-02', 'Active', FALSE),
(5006, 'CSCU-100506', 'Grace',   'Okafor',   '000-90-2278', '1996-07-08', 'grace.okafor@email.com',   '520-555-0206', '1120 N Alvernon Way', 'Tucson',      'AZ', '85712', 30, '2021-04-19', 'Active', FALSE),
(5007, 'CSCU-100507', 'Ray',     'Delgado',  '000-27-6634', '1955-01-03', 'ray.delgado@email.com',    '520-555-0207', '508 E Cottonwood Ln', 'Casa Grande', 'AZ', '85122', 40, '2000-09-15', 'Dormant', TRUE),
(5008, 'CSCU-100508', 'Monica',  'Steele',   '000-19-4451', '1983-11-27', 'monica.steele@email.com',  '602-555-0208', '6040 N 7th Ave',      'Phoenix',     'AZ', '85013', 10, '2011-06-08', 'Active', FALSE),
(5009, 'CSCU-100509', 'Victor',  'Kowalski', '000-85-7709', '1974-08-16', 'victor.kowalski@email.com','480-555-0209', '1745 E Broadway Rd',  'Tempe',       'AZ', '85282', 20, '2016-12-01', 'Active', FALSE),
(5010, 'CSCU-100510', 'Leah',    'Tsosie',   '000-31-9987', '1990-03-22', 'leah.tsosie@email.com',    '520-555-0210', '2210 W McCartney Rd', 'Casa Grande', 'AZ', '85122', 40, '2020-07-27', 'Active', FALSE);

-- ==========================================
-- Table 4: accounts (share/checking/certificate accounts)
-- ==========================================
CREATE TABLE accounts (
    acct_id INT PRIMARY KEY,
    acct_no VARCHAR(20) NOT NULL UNIQUE, -- ACC-NNNNNNNN
    mbr_id INT NOT NULL REFERENCES members(mbr_id),
    br_id INT REFERENCES branches(br_id),
    acct_type_cd VARCHAR(20),            -- SHARE, CHECKING, MONEY_MKT, CERT_12MO, CERT_36MO
    open_dt DATE,
    close_dt DATE,
    acct_status VARCHAR(20) DEFAULT 'Open',  -- Open, Frozen, Closed
    bal_amt DECIMAL(12,2),
    avail_bal_amt DECIMAL(12,2),
    int_rt DECIMAL(6,4)                  -- dividend/interest rate (APY basis)
);

INSERT INTO accounts VALUES
(70001, 'ACC-00070001', 5001, 10, 'SHARE',     '2009-05-14', NULL, 'Open',   12480.55, 12480.55, 0.0150),
(70002, 'ACC-00070002', 5001, 10, 'CHECKING',  '2009-05-14', NULL, 'Open',    3212.10,  3112.10, 0.0005),
(70003, 'ACC-00070003', 5002, 10, 'CHECKING',  '2013-01-22', NULL, 'Open',    1875.42,  1875.42, 0.0005),
(70004, 'ACC-00070004', 5003, 20, 'SHARE',     '2018-08-30', NULL, 'Open',     640.00,   640.00, 0.0150),
(70005, 'ACC-00070005', 5004, 20, 'MONEY_MKT', '2010-02-01', NULL, 'Open',   85400.00, 85400.00, 0.0325),
(70006, 'ACC-00070006', 5005, 30, 'CHECKING',  '2015-10-02', NULL, 'Open',    2960.18,  2960.18, 0.0005),
(70007, 'ACC-00070007', 5006, 30, 'SHARE',     '2021-04-19', NULL, 'Open',    1150.75,  1150.75, 0.0150),
(70008, 'ACC-00070008', 5007, 40, 'SHARE',     '2000-09-15', NULL, 'Open',      25.00,    25.00, 0.0150),
(70009, 'ACC-00070009', 5008, 10, 'CERT_36MO', '2024-06-30', NULL, 'Open',   50000.00,     0.00, 0.0450),
(70010, 'ACC-00070010', 5009, 20, 'CHECKING',  '2016-12-01', NULL, 'Open',    5321.90,  5321.90, 0.0005),
(70011, 'ACC-00070011', 5010, 40, 'CHECKING',  '2020-07-27', NULL, 'Open',     418.63,   418.63, 0.0005),
(70012, 'ACC-00070012', 5004, 20, 'CERT_12MO', '2025-11-15', NULL, 'Open',   25000.00,     0.00, 0.0410);

-- ==========================================
-- Table 5: cards (payment cards issued on accounts)
-- NOTE: cvv_cd is planted for the governance lab -
-- PCI DSS forbids storing CVV after authorization.
-- Stewards are expected to flag it during review.
-- ==========================================
CREATE TABLE cards (
    card_id INT PRIMARY KEY,
    acct_id INT NOT NULL REFERENCES accounts(acct_id),
    card_no VARCHAR(19) NOT NULL UNIQUE, -- fictional 4111... test PANs only
    card_type_cd VARCHAR(15),            -- DEBIT, CREDIT
    exp_dt DATE,
    cvv_cd VARCHAR(4),                   -- MUST NOT EXIST: see table comment
    issued_dt DATE,
    card_status VARCHAR(20) DEFAULT 'Active'  -- Active, Blocked, Expired, Reported
);

INSERT INTO cards VALUES
(80001, 70002, '4111-1111-1111-1001', 'DEBIT',  '2028-05-31', '123', '2024-06-01', 'Active'),
(80002, 70003, '4111-1111-1111-1002', 'DEBIT',  '2027-11-30', '482', '2023-12-01', 'Active'),
(80003, 70006, '4111-1111-1111-1003', 'DEBIT',  '2029-01-31', '077', '2026-02-01', 'Active'),
(80004, 70010, '4111-1111-1111-1004', 'DEBIT',  '2027-08-31', '905', '2023-09-01', 'Blocked'),
(80005, 70005, '4111-1111-1111-1005', 'CREDIT', '2028-10-31', '316', '2024-11-01', 'Active'),
(80006, 70011, '4111-1111-1111-1006', 'DEBIT',  '2026-04-30', '654', '2022-05-01', 'Expired');

-- ==========================================
-- Table 6: transactions (posted monetary activity)
-- ==========================================
CREATE TABLE transactions (
    txn_id BIGINT PRIMARY KEY,
    acct_id INT NOT NULL REFERENCES accounts(acct_id),
    txn_dt TIMESTAMP,
    post_dt DATE,
    txn_amt DECIMAL(12,2),               -- negative = debit, positive = credit
    txn_type_cd VARCHAR(20),             -- POS, ATM, ACH_CR, ACH_DR, XFER, FEE, DIVIDEND, CHECK
    merch_nm VARCHAR(100),
    mcc_cd VARCHAR(4),                   -- merchant category code
    memo_txt VARCHAR(200)
);

INSERT INTO transactions VALUES
(900001, 70002, '2026-06-01 08:14:22', '2026-06-01',  -54.20, 'POS',      'Fry''s Food Stores #42',   '5411', 'groceries'),
(900002, 70002, '2026-06-02 12:40:03', '2026-06-02', -120.00, 'ATM',      'CSCU ATM Camelback',       '6011', 'cash withdrawal'),
(900003, 70002, '2026-06-05 00:00:00', '2026-06-05', 2150.00, 'ACH_CR',   'DESERT SUN LLC PAYROLL',   NULL,   'direct deposit'),
(900004, 70003, '2026-06-05 00:00:00', '2026-06-05', 1893.44, 'ACH_CR',   'MARICOPA CTY PAYROLL',     NULL,   'direct deposit'),
(900005, 70003, '2026-06-07 19:22:48', '2026-06-07',  -89.99, 'POS',      'AMZN Mktp US',             '5942', 'online purchase'),
(900006, 70006, '2026-06-08 09:03:11', '2026-06-08',  -42.75, 'POS',      'Chevron 0093',             '5541', 'fuel'),
(900007, 70006, '2026-06-10 00:00:00', '2026-06-10', -650.00, 'ACH_DR',   'DESERT RIDGE APTS',        NULL,   'rent autopay'),
(900008, 70010, '2026-06-11 13:55:37', '2026-06-11', -230.00, 'CHECK',    NULL,                       NULL,   'check 1044'),
(900009, 70010, '2026-06-12 10:02:59', '2026-06-12',  -35.00, 'FEE',      NULL,                       NULL,   'overdraft fee'),
(900010, 70005, '2026-06-30 00:00:00', '2026-06-30',  231.19, 'DIVIDEND', NULL,                       NULL,   'monthly dividend'),
(900011, 70011, '2026-06-14 17:26:40', '2026-06-14',  -18.50, 'POS',      'In-N-Out Burger 211',      '5814', 'dining'),
(900012, 70011, '2026-06-15 08:00:00', '2026-06-15', -400.00, 'XFER',     NULL,                       NULL,   'transfer to loan 91004'),
(900013, 70002, '2026-06-16 21:12:05', '2026-06-16', -9450.00,'ACH_DR',   'COIN-XCHNG DIGITAL',       NULL,   'external transfer'),
(900014, 70002, '2026-06-17 21:15:44', '2026-06-17', -9450.00,'ACH_DR',   'COIN-XCHNG DIGITAL',       NULL,   'external transfer'),
(900015, 70004, '2026-06-20 11:30:00', '2026-06-20',   25.00, 'XFER',     NULL,                       NULL,   'share deposit');

-- ==========================================
-- Table 7: loans (consumer + real-estate lending)
-- ==========================================
CREATE TABLE loans (
    ln_id INT PRIMARY KEY,
    ln_no VARCHAR(20) NOT NULL UNIQUE,   -- LN-NNNNNN
    mbr_id INT NOT NULL REFERENCES members(mbr_id),
    ln_type_cd VARCHAR(20),              -- AUTO, PERSONAL, HELOC, MORTGAGE, CREDIT_CARD
    orig_amt DECIMAL(12,2),
    prin_bal_amt DECIMAL(12,2),
    apr_rt DECIMAL(6,4),
    term_mo INT,
    orig_dt DATE,
    maturity_dt DATE,
    collateral_desc VARCHAR(200),
    ln_status VARCHAR(20) DEFAULT 'Current'  -- Current, Delinquent30, Delinquent60, ChargedOff, PaidOff
);

INSERT INTO loans VALUES
(91001, 'LN-091001', 5001, 'AUTO',     28500.00, 19342.77, 0.0649, 72,  '2023-04-18', '2029-04-18', '2023 Toyota Tacoma VIN 3TYAX5GN…', 'Current'),
(91002, 'LN-091002', 5004, 'MORTGAGE', 310000.00, 248990.12, 0.0575, 360, '2016-07-01', '2046-07-01', '901 S Rural Rd, Tempe AZ (deed of trust)', 'Current'),
(91003, 'LN-091003', 5005, 'PERSONAL', 12000.00,  8104.33, 0.1125, 48,  '2024-09-12', '2028-09-12', NULL, 'Current'),
(91004, 'LN-091004', 5010, 'AUTO',     18900.00, 16512.00, 0.0724, 60,  '2025-03-05', '2030-03-05', '2021 Honda Civic VIN 2HGFC2F5…', 'Delinquent30'),
(91005, 'LN-091005', 5008, 'HELOC',    75000.00, 21500.00, 0.0850, 120, '2022-10-20', '2032-10-20', '6040 N 7th Ave, Phoenix AZ (2nd lien)', 'Current'),
(91006, 'LN-091006', 5007, 'PERSONAL',  5000.00,     0.00, 0.1299, 36,  '2019-02-14', '2022-02-14', NULL, 'PaidOff');

-- ==========================================
-- Table 8: ach_payments (external electronic payments)
-- ==========================================
CREATE TABLE ach_payments (
    ach_id INT PRIMARY KEY,
    acct_id INT NOT NULL REFERENCES accounts(acct_id),
    ach_rte_no VARCHAR(9),               -- external ABA routing number (fictional)
    ext_acct_no VARCHAR(20),             -- external account (fictional)
    dir_cd VARCHAR(6),                   -- CREDIT (incoming) / DEBIT (outgoing)
    ach_amt DECIMAL(12,2),
    eff_dt DATE,
    ach_status VARCHAR(20) DEFAULT 'Settled', -- Pending, Settled, Returned
    return_cd VARCHAR(4)                 -- NACHA return reason (R01 = NSF ...)
);

INSERT INTO ach_payments VALUES
(95001, 70002, '122100024', '9944810022',  'CREDIT', 2150.00, '2026-06-05', 'Settled',  NULL),
(95002, 70003, '122100024', '5511230876',  'CREDIT', 1893.44, '2026-06-05', 'Settled',  NULL),
(95003, 70006, '322172496', '7100442199',  'DEBIT',   650.00, '2026-06-10', 'Settled',  NULL),
(95004, 70002, '121000358', '8802341567',  'DEBIT',  9450.00, '2026-06-16', 'Settled',  NULL),
(95005, 70002, '121000358', '8802341567',  'DEBIT',  9450.00, '2026-06-17', 'Settled',  NULL),
(95006, 70011, '322172496', '3308871020',  'DEBIT',   120.00, '2026-06-18', 'Returned', 'R01');

-- ==========================================
-- Table 9: kyc_reviews (know-your-customer reviews)
-- ==========================================
CREATE TABLE kyc_reviews (
    kyc_id INT PRIMARY KEY,
    mbr_id INT NOT NULL REFERENCES members(mbr_id),
    review_dt DATE,
    risk_rating_cd VARCHAR(10),          -- LOW, MEDIUM, HIGH
    id_doc_type_cd VARCHAR(20),          -- DRIVERS_LICENSE, PASSPORT, STATE_ID
    id_doc_no VARCHAR(30),               -- fictional document numbers
    reviewer_emp_id INT REFERENCES employees(emp_id),
    kyc_status VARCHAR(20) DEFAULT 'Complete',  -- Complete, Pending, Escalated
    notes VARCHAR(500)
);

INSERT INTO kyc_reviews VALUES
(96001, 5001, '2025-05-14', 'LOW',    'DRIVERS_LICENSE', 'AZ-D08812345', 903, 'Complete',  'Routine 5-year refresh. No changes.'),
(96002, 5002, '2025-01-22', 'LOW',    'DRIVERS_LICENSE', 'AZ-D0772390',  903, 'Complete',  'Routine refresh.'),
(96003, 5004, '2026-02-01', 'MEDIUM', 'PASSPORT',        'P55023981',    903, 'Complete',  'Large money-market balances; source of funds documented (property sale).'),
(96004, 5007, '2026-03-10', 'MEDIUM', 'STATE_ID',        'AZ-S0331276',  903, 'Pending',   'Dormant account reactivation request. Awaiting updated ID.'),
(96005, 5009, '2025-12-01', 'LOW',    'DRIVERS_LICENSE', 'AZ-D09018852', 903, 'Complete',  'Routine refresh.'),
(96006, 5001, '2026-06-18', 'HIGH',   'DRIVERS_LICENSE', 'AZ-D08812345', 903, 'Escalated', 'Escalated after repeated just-under-threshold external transfers. See SAR 97001.');

-- ==========================================
-- Table 10: suspicious_activity (BSA/AML case tracking)
-- ==========================================
CREATE TABLE suspicious_activity (
    sar_id INT PRIMARY KEY,
    mbr_id INT REFERENCES members(mbr_id),
    acct_id INT REFERENCES accounts(acct_id),
    filed_dt DATE,
    activity_type_cd VARCHAR(30),        -- STRUCTURING, FRAUD, IDENTITY_THEFT, ELDER_ABUSE
    sar_amt DECIMAL(12,2),
    narrative_txt VARCHAR(1000),
    filed_by_emp_id INT REFERENCES employees(emp_id),
    sar_status VARCHAR(20) DEFAULT 'Draft'   -- Draft, Filed, Closed
);

INSERT INTO suspicious_activity VALUES
(97001, 5001, 70002, '2026-06-19', 'STRUCTURING', 18900.00,
 'Two consecutive external ACH transfers of $9,450 on 2026-06-16 and 2026-06-17 to the same digital-currency exchange, each just below the $10,000 reporting threshold. Pattern consistent with structuring. Member contacted; explanation pending. KYC risk rating raised to HIGH.',
 903, 'Filed'),
(97002, 5007, 70008, '2026-04-02', 'ELDER_ABUSE', 3200.00,
 'Dormant-account reactivation attempted by a third party holding power of attorney of uncertain validity. Branch declined the withdrawal; adult-protective-services referral made.',
 903, 'Filed'),
(97003, NULL, 70010, '2026-06-13', 'FRAUD', 230.00,
 'Check 1044 reported by the member as never written; signature does not match card on file. Card blocked, check returned, affidavit of forgery taken.',
 903, 'Closed'),
(97004, 5006, 70007, '2026-05-28', 'IDENTITY_THEFT', 0.00,
 'Member reported a fraudulent credit application at another institution using her identity. Flagged for enhanced monitoring; credit bureaus notified. No CSCU loss.',
 903, 'Closed');

-- ==========================================
-- Table 11: gl_entries (general-ledger postings)
-- ==========================================
CREATE TABLE gl_entries (
    gl_id BIGINT PRIMARY KEY,
    gl_acct_no VARCHAR(10),              -- 1xxx assets, 2xxx liabilities, 4xxx income, 5xxx expense
    post_dt DATE,
    dr_amt DECIMAL(14,2),
    cr_amt DECIMAL(14,2),
    br_id INT REFERENCES branches(br_id),
    desc_txt VARCHAR(200)
);

INSERT INTO gl_entries VALUES
(990001, '1010', '2026-06-30', 231.19,     0.00, 10, 'Dividend expense funding - money market'),
(990002, '2205', '2026-06-30',   0.00,   231.19, 10, 'Member dividend payable - ACC-00070005'),
(990003, '4020', '2026-06-12',   0.00,    35.00, 20, 'Overdraft fee income - ACC-00070010'),
(990004, '1210', '2026-06-16', 9450.00,    0.00, 10, 'ACH settlement clearing - outgoing'),
(990005, '1210', '2026-06-17', 9450.00,    0.00, 10, 'ACH settlement clearing - outgoing'),
(990006, '5110', '2026-06-15', 1200.00,    0.00, 30, 'Branch operating expense - Tucson Speedway'),
(990007, '1050', '2026-06-20',  25.00,     0.00, 20, 'Share deposit - teller drawer'),
(990008, '2100', '2026-06-20',   0.00,    25.00, 20, 'Member share liability - ACC-00070004'),
(990009, '1310', '2026-06-30', 16512.00,   0.00, 40, 'Auto loan principal outstanding - LN-091004'),
(990010, '4010', '2026-06-30',   0.00,   118.35, 40, 'Loan interest income - June accrual');

-- ==========================================
-- Create indexes for performance
-- ==========================================
CREATE INDEX idx_members_city ON members(city);
CREATE INDEX idx_members_branch ON members(br_id);
CREATE INDEX idx_members_status ON members(mbr_status);
CREATE INDEX idx_accounts_member ON accounts(mbr_id);
CREATE INDEX idx_accounts_type ON accounts(acct_type_cd);
CREATE INDEX idx_txn_account ON transactions(acct_id);
CREATE INDEX idx_txn_post ON transactions(post_dt);
CREATE INDEX idx_txn_type ON transactions(txn_type_cd);
CREATE INDEX idx_loans_member ON loans(mbr_id);
CREATE INDEX idx_loans_status ON loans(ln_status);
CREATE INDEX idx_ach_account ON ach_payments(acct_id);
CREATE INDEX idx_kyc_member ON kyc_reviews(mbr_id);
CREATE INDEX idx_sar_member ON suspicious_activity(mbr_id);
CREATE INDEX idx_gl_acct ON gl_entries(gl_acct_no);

-- ==========================================
-- Create views for BA analysis
-- ==========================================

-- View: Member relationship summary
CREATE VIEW member_relationship_summary AS
SELECT
    m.mbr_id,
    m.mbr_no,
    m.first_nm || ' ' || m.last_nm AS member_name,
    m.city,
    m.mbr_status,
    b.br_name,
    COUNT(DISTINCT a.acct_id) AS open_accounts,
    COALESCE(SUM(a.bal_amt), 0) AS total_deposits,
    COUNT(DISTINCT l.ln_id) FILTER (WHERE l.ln_status <> 'PaidOff') AS open_loans,
    COALESCE(SUM(l.prin_bal_amt) FILTER (WHERE l.ln_status <> 'PaidOff'), 0) AS total_loan_balance
FROM members m
LEFT JOIN branches b ON m.br_id = b.br_id
LEFT JOIN accounts a ON m.mbr_id = a.mbr_id AND a.acct_status = 'Open'
LEFT JOIN loans l    ON m.mbr_id = l.mbr_id
GROUP BY m.mbr_id, m.mbr_no, m.first_nm, m.last_nm, m.city, m.mbr_status, b.br_name;

-- View: Branch activity for June 2026
CREATE VIEW branch_activity_summary AS
SELECT
    b.br_id,
    b.br_name,
    COUNT(DISTINCT m.mbr_id) AS members,
    COUNT(DISTINCT t.txn_id) AS june_transactions,
    ROUND(COALESCE(SUM(CASE WHEN t.txn_amt < 0 THEN -t.txn_amt END), 0), 2) AS june_debits,
    ROUND(COALESCE(SUM(CASE WHEN t.txn_amt > 0 THEN t.txn_amt END), 0), 2) AS june_credits
FROM branches b
LEFT JOIN members m ON m.br_id = b.br_id
LEFT JOIN accounts a ON a.mbr_id = m.mbr_id
LEFT JOIN transactions t ON t.acct_id = a.acct_id
     AND t.post_dt BETWEEN '2026-06-01' AND '2026-06-30'
GROUP BY b.br_id, b.br_name
ORDER BY b.br_name;

-- View: Open compliance items (KYC + SAR)
CREATE VIEW compliance_open_items AS
SELECT
    'KYC' AS item_type,
    k.kyc_id AS item_id,
    m.mbr_no,
    k.risk_rating_cd AS severity,
    k.kyc_status AS status,
    k.review_dt AS item_date,
    k.notes AS detail
FROM kyc_reviews k
JOIN members m ON m.mbr_id = k.mbr_id
WHERE k.kyc_status <> 'Complete'
UNION ALL
SELECT
    'SAR',
    s.sar_id,
    m.mbr_no,
    s.activity_type_cd,
    s.sar_status,
    s.filed_dt,
    LEFT(s.narrative_txt, 120)
FROM suspicious_activity s
LEFT JOIN members m ON m.mbr_id = s.mbr_id
WHERE s.sar_status <> 'Closed';

-- ==========================================
-- Add metadata comments for PDC
-- ==========================================
COMMENT ON TABLE members IS 'Copper State Credit Union member master file. Contains PII (names, SSN, DOB, addresses, phone, email) for every member across the four Arizona branches. CONFIDENTIAL.';

COMMENT ON COLUMN members.mbr_no IS 'Unique CSCU member number in format CSCU-NNNNNN. Primary member identifier used on statements and in correspondence. CONFIDENTIAL PII.';

COMMENT ON COLUMN members.ssn IS 'Member Social Security Number (fictional 000-xx-xxxx training values). HIGHEST sensitivity - GLBA/identity-theft exposure. Mask everywhere outside servicing.';

COMMENT ON COLUMN members.opted_out_marketing IS 'GDPR/CCPA marketing-consent flag. TRUE means the member has opted OUT of marketing communications and must not receive marketing email. CRITICAL compliance control - see business rule CSCU-Marketing-OptOut-Compliance.';

COMMENT ON TABLE accounts IS 'Member share, checking, money-market and certificate accounts with current and available balances and dividend rates.';

COMMENT ON COLUMN accounts.acct_no IS 'Unique account number in format ACC-NNNNNNNN. Appears on statements and ACH entries. CONFIDENTIAL PII under GLBA.';

COMMENT ON COLUMN accounts.acct_type_cd IS 'Account product code. Values: SHARE (regular savings), CHECKING (share draft), MONEY_MKT, CERT_12MO, CERT_36MO. Drives dividend rate and statement grouping.';

COMMENT ON TABLE cards IS 'Payment cards issued on member accounts. Card numbers are fictional 4111 test PANs. PCI DSS scope.';

COMMENT ON COLUMN cards.card_no IS 'Payment card primary account number (PAN). PCI DSS: render unreadable wherever stored; display last four only. Fictional test values in this lab.';

COMMENT ON COLUMN cards.cvv_cd IS 'Card verification value. PCI DSS 3.2 prohibits storing CVV after authorization - THIS COLUMN SHOULD NOT EXIST and is planted for the data-governance exercise: the steward must flag it during glossary review.';

COMMENT ON TABLE transactions IS 'Posted monetary transactions across all member accounts: card purchases, ATM, ACH credits/debits, checks, fees and dividends. Negative amounts are debits.';

COMMENT ON COLUMN transactions.txn_type_cd IS 'Transaction type. Values: POS (card purchase), ATM, ACH_CR (incoming ACH), ACH_DR (outgoing ACH), XFER (internal transfer), FEE, DIVIDEND, CHECK. Routes to statement sections and fee analysis.';

COMMENT ON COLUMN transactions.mcc_cd IS 'Merchant category code (ISO 18245) for card transactions. Used in spend analysis and fraud rules.';

COMMENT ON TABLE loans IS 'Consumer and real-estate loans: auto, personal, HELOC and mortgage. Tracks origination and current principal, APR, term and collateral. CONFIDENTIAL under GLBA.';

COMMENT ON COLUMN loans.apr_rt IS 'Annual percentage rate as a decimal (0.0649 = 6.49%). Regulation Z disclosure value. CRITICAL for pricing and compliance review.';

COMMENT ON COLUMN loans.ln_status IS 'Servicing status. Values: Current, Delinquent30, Delinquent60, ChargedOff, PaidOff. Drives collections workflow and ALLL reporting.';

COMMENT ON TABLE ach_payments IS 'ACH entries to and from external institutions (NACHA). Carries external routing and account numbers - CONFIDENTIAL.';

COMMENT ON COLUMN ach_payments.ach_rte_no IS 'External ABA routing number (9 digits) of the counterparty institution. Fictional values in this lab.';

COMMENT ON COLUMN ach_payments.return_cd IS 'NACHA return reason code when status is Returned (R01 = insufficient funds, R02 = account closed, ...).';

COMMENT ON TABLE kyc_reviews IS 'Know-Your-Customer reviews per member: risk rating, identity document, reviewer and status. BSA/AML program record. CONFIDENTIAL.';

COMMENT ON COLUMN kyc_reviews.risk_rating_cd IS 'AML risk rating assigned at review. Values: LOW, MEDIUM, HIGH. HIGH triggers enhanced due diligence. CRITICAL compliance field.';

COMMENT ON TABLE suspicious_activity IS 'Suspicious Activity Report (SAR) case tracking for the BSA/AML program: structuring, fraud, identity theft, elder abuse. HIGHEST confidentiality - federal law prohibits disclosing a SAR to the subject.';

COMMENT ON COLUMN suspicious_activity.activity_type_cd IS 'Suspicious-activity classification. Values: STRUCTURING (sub-threshold patterns), FRAUD, IDENTITY_THEFT, ELDER_ABUSE. CRITICAL for regulatory reporting.';

COMMENT ON TABLE gl_entries IS 'General-ledger postings (double entry): 1xxx assets, 2xxx liabilities, 4xxx income, 5xxx expense. Feeds the call report and financial statements.';

COMMENT ON TABLE branches IS 'CSCU branch network reference data: four Arizona branches with manager and status.';

COMMENT ON TABLE employees IS 'Branch staff master: role, branch and status. Contains employee PII (names, email).';

-- ==========================================
-- Sample data complete - Copper State Credit Union
-- ==========================================
