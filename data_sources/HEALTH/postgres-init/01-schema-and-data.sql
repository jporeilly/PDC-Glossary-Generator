-- ==========================================
-- PDC Business Analyst Course
-- Sample Data: Lakeshore Health Partners (LHP)
-- Fictional Minnesota clinic network
-- ==========================================

CREATE SCHEMA IF NOT EXISTS lhp_clinical;
SET search_path TO lhp_clinical;

-- ==========================================
-- Table 1: clinics (LHP clinic network)
-- ==========================================
CREATE TABLE clinics (
    cl_id INT PRIMARY KEY,
    cl_name VARCHAR(100) NOT NULL UNIQUE,
    cl_addr VARCHAR(200),
    cl_city VARCHAR(50),
    cl_county VARCHAR(30),
    cl_zip VARCHAR(10),
    cl_phone VARCHAR(20),
    mgr_staff_id INT,                    -- clinic manager (FK added after staff)
    open_dt DATE,
    cl_status VARCHAR(20) DEFAULT 'Open' -- Open, Closed, Relocating
);

INSERT INTO clinics VALUES
(10, 'Minneapolis Uptown',   '2934 Hennepin Ave',    'Minneapolis', 'Hennepin', '55408', '612-555-0310', NULL, '2003-05-12', 'Open'),
(20, 'St. Paul Como',        '1360 Lexington Pkwy N','St. Paul',    'Ramsey',   '55103', '651-555-0320', NULL, '2007-09-24', 'Open'),
(30, 'Duluth Harborview',    '402 E Superior St',    'Duluth',      'St. Louis','55802', '218-555-0330', NULL, '2005-03-08', 'Open'),
(40, 'Rochester Southtown',  '1523 S Broadway',      'Rochester',   'Olmsted',  '55904', '507-555-0340', NULL, '2012-11-15', 'Open'),
(50, 'St. Cloud Riverside',  '812 W St Germain St',  'St. Cloud',   'Stearns',  '56301', '320-555-0350', NULL, '2016-06-20', 'Open'),
(60, 'Bloomington Southdale','8020 Penn Ave S',      'Bloomington', 'Hennepin', '55431', '952-555-0360', NULL, '2010-02-11', 'Open');

-- ==========================================
-- Table 2: staff (non-provider clinic staff)
-- ==========================================
CREATE TABLE staff (
    staff_id INT PRIMARY KEY,
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    cl_id INT NOT NULL REFERENCES clinics(cl_id),
    role_cd VARCHAR(30),                 -- RN, MA, FRONT_DESK, CLINIC_MGR, BILLING, HIM
    hire_dt DATE,
    staff_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO staff VALUES
(701, 'Maya',   'Lindqvist', 'maya.lindqvist@lakeshorehealth.org', 10, 'CLINIC_MGR', '2012-04-16', 'Active'),
(702, 'Anders', 'Berg',      'anders.berg@lakeshorehealth.org',    10, 'HIM',        '2015-08-03', 'Active'),
(703, 'Rosa',   'Jimenez',   'rosa.jimenez@lakeshorehealth.org',   20, 'BILLING',    '2014-01-27', 'Active'),
(704, 'Hannah', 'Weiss',     'hannah.weiss@lakeshorehealth.org',   10, 'HIM',        '2013-10-06', 'Active'),
(705, 'Victor', 'Osei',      'victor.osei@lakeshorehealth.org',    30, 'CLINIC_MGR', '2016-05-23', 'Active'),
(706, 'Ingrid', 'Dahl',      'ingrid.dahl@lakeshorehealth.org',    20, 'RN',         '2018-02-12', 'Active'),
(707, 'Jamal',  'Carter',    'jamal.carter@lakeshorehealth.org',   40, 'FRONT_DESK', '2021-07-19', 'Active'),
(708, 'Beth',   'Nakamura',  'beth.nakamura@lakeshorehealth.org',  60, 'MA',         '2019-11-04', 'Inactive');

ALTER TABLE clinics ADD CONSTRAINT fk_clinics_mgr
    FOREIGN KEY (mgr_staff_id) REFERENCES staff(staff_id);
UPDATE clinics SET mgr_staff_id = 701 WHERE cl_id = 10;
UPDATE clinics SET mgr_staff_id = 705 WHERE cl_id = 30;

-- ==========================================
-- Table 3: providers (physicians & APPs)
-- NPI is the national 10-digit provider identifier
-- ==========================================
CREATE TABLE providers (
    prov_id INT PRIMARY KEY,
    npi_no CHAR(10) NOT NULL UNIQUE,     -- 10-digit NPI (fictional)
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    specialty_cd VARCHAR(10),            -- FAMMED, PEDS, CARDIO, DERM, ORTHO, BEHAV
    cl_id INT NOT NULL REFERENCES clinics(cl_id),
    license_no VARCHAR(20),
    prov_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO providers VALUES
(601, '1902847361', 'Susan',  'Hargrove', 'FAMMED', 10, 'MN-44821', 'Active'),
(602, '1938264057', 'Peter',  'Vang',     'PEDS',   20, 'MN-51907', 'Active'),
(603, '1974638210', 'Amara',  'Diallo',   'CARDIO', 30, 'MN-38264', 'Active'),
(604, '1946082735', 'Erik',   'Sundberg', 'FAMMED', 40, 'MN-60142', 'Active'),
(605, '1927501846', 'Leah',   'Goldman',  'DERM',   60, 'MN-55873', 'Active'),
(606, '1953816420', 'Tomas',  'Reyes',    'BEHAV',  50, 'MN-62490', 'OnLeave');

-- ==========================================
-- Table 4: patients (the PHI master)
-- mkt_optout TRUE + live email = the planted privacy
-- defect (3 rows). HIPAA: marketing contact requires
-- authorization; extracts MUST suppress these rows.
-- ==========================================
CREATE TABLE patients (
    pt_id INT PRIMARY KEY,
    mrn VARCHAR(12) NOT NULL UNIQUE,     -- medical record number, format LHP-nnnnnn
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    ssn CHAR(11),                        -- NNN-NN-NNNN (fictional 9xx values)
    dob DATE,
    sex_cd CHAR(1),                      -- F, M, X
    email VARCHAR(100),
    phone VARCHAR(20),
    addr1 VARCHAR(100),
    city VARCHAR(50),
    st CHAR(2),
    zip VARCHAR(10),
    primary_prov_id INT REFERENCES providers(prov_id),
    enrolled_dt DATE,
    mkt_optout BOOLEAN DEFAULT FALSE,
    pt_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO patients VALUES
(4001, 'LHP-300101', 'Alma',    'Petersen',  '900-21-4417', '1958-03-14', 'F', 'alma.petersen@email.com',   '612-555-2101', '4520 Colfax Ave S',    'Minneapolis', 'MN', '55419', 601, '2015-06-02', FALSE, 'Active'),
(4002, 'LHP-300102', 'Gordon',  'Bly',       '900-38-7752', '1946-11-02', 'M', 'gordon.bly@email.com',      '651-555-2102', '988 Ashland Ave',      'St. Paul',    'MN', '55104', 602, '2016-02-19', TRUE,  'Active'),
(4003, 'LHP-300103', 'Farida',  'Hassan',    '900-45-1120', '1989-07-23', 'F', 'farida.hassan@email.com',   '612-555-2103', '2210 Pillsbury Ave',   'Minneapolis', 'MN', '55404', 601, '2019-09-30', FALSE, 'Active'),
(4004, 'LHP-300104', 'Walter',  'Kowalski',  '900-52-9986', '1951-05-08', 'M', 'walter.kowalski@email.com', '218-555-2104', '311 N 40th Ave E',     'Duluth',      'MN', '55804', 603, '2014-12-11', FALSE, 'Active'),
(4005, 'LHP-300105', 'Soua',    'Yang',      '900-63-2274', '1996-01-17', 'F', 'soua.yang@email.com',       '651-555-2105', '1745 Maryland Ave E',  'St. Paul',    'MN', '55106', 602, '2021-04-06', TRUE,  'Active'),
(4006, 'LHP-300106', 'Dennis',  'Okafor',    '900-74-8830', '1978-09-29', 'M', 'dennis.okafor@email.com',   '507-555-2106', '2635 18th Ave NW',     'Rochester',   'MN', '55901', 604, '2018-07-24', FALSE, 'Active'),
(4007, 'LHP-300107', 'Birgit',  'Aune',      '900-81-5563', '1962-12-05', 'F', 'birgit.aune@email.com',     '218-555-2107', '1522 E 3rd St',        'Duluth',      'MN', '55812', 603, '2017-03-15', FALSE, 'Active'),
(4008, 'LHP-300108', 'Ray',     'Littlefeather','900-92-3348','1949-08-21','M', 'ray.littlefeather@email.com','320-555-2108','604 5th Ave S',        'St. Cloud',   'MN', '56301', 606, '2020-10-08', FALSE, 'Active'),
(4009, 'LHP-300109', 'Celeste', 'Moreau',    '900-17-6691', '1984-04-11', 'F', 'celeste.moreau@email.com',  '952-555-2109', '8811 Queen Ave S',     'Bloomington', 'MN', '55431', 605, '2022-01-27', TRUE,  'Active'),
(4010, 'LHP-300110', 'Hakim',   'Warsame',   '900-26-4405', '2001-10-30', 'M', 'hakim.warsame@email.com',   '612-555-2110', '1509 E Franklin Ave',  'Minneapolis', 'MN', '55404', 601, '2023-05-18', FALSE, 'Active'),
(4011, 'LHP-300111', 'June',    'Sandvik',   '900-33-9917', '1972-06-26', 'F', 'june.sandvik@email.com',    '507-555-2111', '844 7th St SW',        'Rochester',   'MN', '55902', 604, '2019-11-12', FALSE, 'Active'),
(4012, 'LHP-300112', 'Theo',    'Lindgren',  '900-48-2286', '2018-02-14', 'M', 'theo.lindgren@email.com',   '651-555-2112', '77 Wheelock Pkwy',     'St. Paul',    'MN', '55117', 602, '2023-08-03', FALSE, 'Active'),
(4013, 'LHP-300113', 'Opal',    'Bruns',     '900-55-7739', '1939-01-09', 'F', 'opal.bruns@email.com',      '320-555-2113', '218 Ramsey St',        'St. Cloud',   'MN', '56303', 606, '2016-09-21', FALSE, 'Inactive');

-- ==========================================
-- Table 5: payers (insurance / coverage)
-- ==========================================
CREATE TABLE payers (
    payer_id INT PRIMARY KEY,
    payer_nm VARCHAR(100) NOT NULL,
    payer_type_cd VARCHAR(15),           -- COMMERCIAL, MEDICARE, MEDICAID, SELF_PAY
    contact_email VARCHAR(100),
    phone VARCHAR(20),
    city VARCHAR(50),
    st CHAR(2),
    payer_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO payers VALUES
(301, 'North Star Mutual Health',  'COMMERCIAL', 'claims@northstarmutual.example', '612-555-0401', 'Minneapolis', 'MN', 'Active'),
(302, 'Medicare Part B (MN MAC)',  'MEDICARE',   'partb@cmsmac.example',           '866-555-0402', 'Bloomington', 'MN', 'Active'),
(303, 'MN Medical Assistance',     'MEDICAID',   'ma-claims@dhs.example',          '651-555-0403', 'St. Paul',    'MN', 'Active'),
(304, 'Boundary Waters Benefits',  'COMMERCIAL', 'edi@bwbenefits.example',         '218-555-0404', 'Duluth',      'MN', 'Active'),
(305, 'Self Pay',                  'SELF_PAY',   NULL,                             NULL,           NULL,          NULL, 'Active'),
(306, 'Prairie Health Plan',       'COMMERCIAL', 'claims@prairiehp.example',       '507-555-0406', 'Rochester',   'MN', 'OnHold');

-- ==========================================
-- Table 6: appointments
-- ==========================================
CREATE TABLE appointments (
    appt_id INT PRIMARY KEY,
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    prov_id INT NOT NULL REFERENCES providers(prov_id),
    cl_id INT NOT NULL REFERENCES clinics(cl_id),
    appt_dt DATE NOT NULL,
    appt_type_cd VARCHAR(15),            -- NEW, FOLLOWUP, PHYSICAL, TELEHEALTH, URGENT
    appt_status VARCHAR(20) DEFAULT 'Scheduled' -- Scheduled, Completed, NoShow, Cancelled
);

INSERT INTO appointments VALUES
(50001, 4001, 601, 10, '2026-05-05', 'PHYSICAL',   'Completed'),
(50002, 4004, 603, 30, '2026-05-07', 'FOLLOWUP',   'Completed'),
(50003, 4002, 602, 20, '2026-05-12', 'FOLLOWUP',   'Completed'),
(50004, 4006, 604, 40, '2026-05-14', 'NEW',        'Completed'),
(50005, 4009, 605, 60, '2026-05-19', 'NEW',        'Completed'),
(50006, 4003, 601, 10, '2026-05-21', 'TELEHEALTH', 'Completed'),
(50007, 4008, 606, 50, '2026-05-27', 'FOLLOWUP',   'Completed'),
(50008, 4012, 602, 20, '2026-06-02', 'PHYSICAL',   'Completed'),
(50009, 4007, 603, 30, '2026-06-04', 'URGENT',     'Completed'),
(50010, 4011, 604, 40, '2026-06-09', 'FOLLOWUP',   'Completed'),
(50011, 4005, 602, 20, '2026-06-11', 'FOLLOWUP',   'NoShow'),
(50012, 4010, 601, 10, '2026-06-16', 'NEW',        'Completed'),
(50013, 4013, 606, 50, '2026-06-18', 'FOLLOWUP',   'Cancelled'),
(50014, 4001, 601, 10, '2026-06-23', 'FOLLOWUP',   'Completed'),
(50015, 4004, 603, 30, '2026-06-25', 'FOLLOWUP',   'Completed'),
(50016, 4009, 605, 60, '2026-07-01', 'FOLLOWUP',   'Scheduled');

-- ==========================================
-- Table 7: encounters (clinical visits)
-- PLANTED PHI DEFECT: two note_txt values carry a
-- patient SSN in free text. PHI/PII must never sit in
-- unstructured note fields - the identification and
-- quality workshops triangulate this. Fictional values.
-- ==========================================
CREATE TABLE encounters (
    enc_id INT PRIMARY KEY,
    appt_id INT REFERENCES appointments(appt_id),
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    prov_id INT NOT NULL REFERENCES providers(prov_id),
    enc_dt DATE NOT NULL,
    chief_complaint_txt VARCHAR(200),
    dx_cd VARCHAR(10),                   -- primary diagnosis, ICD-10-CM
    note_txt TEXT,                       -- DEFECT: free text; two rows leak an SSN
    enc_status VARCHAR(20) DEFAULT 'Closed' -- Open, Closed, Amended
);

INSERT INTO encounters VALUES
(90001, 50001, 4001, 601, '2026-05-05', 'Annual physical',              'Z00.00',
 'Annual wellness visit. BP 128/82. Labs ordered: CMP, lipid panel. Flu vaccine declined. Follow up 12 months.', 'Closed'),
(90002, 50002, 4004, 603, '2026-05-07', 'Hypertension follow-up',       'I10',
 'BP improved on lisinopril 20mg. Continue current regimen. Recheck 6 weeks with home log.', 'Closed'),
(90003, 50003, 4002, 602, '2026-05-12', 'Type 2 diabetes follow-up',    'E11.9',
 'A1c 7.4, down from 8.1. Continue metformin. Patient provided SSN 900-38-7752 for Medicare crossover form - recorded here for billing. Nutrition referral placed.', 'Closed'),
(90004, 50004, 4006, 604, '2026-05-14', 'Knee pain, new patient',       'M25.561',
 'Right knee pain 3 months, worse with stairs. X-ray ordered. NSAIDs, PT referral.', 'Closed'),
(90005, 50005, 4009, 605, '2026-05-19', 'New rash evaluation',          'L30.9',
 'Eczematous dermatitis, forearms. Triamcinolone 0.1% BID. Return 4 weeks if not improved.', 'Closed'),
(90006, 50006, 4003, 601, '2026-05-21', 'Medication review (telehealth)','F41.1',
 'GAD stable on sertraline 50mg. Sleep improved. Refill 90 days.', 'Closed'),
(90007, 50007, 4008, 606, '2026-05-27', 'Depression follow-up',         'F33.1',
 'PHQ-9 down to 9 from 15. Continue duloxetine. Safety plan reviewed. Caller verified identity with SSN 900-92-3348 before phone follow-up - documented per front-desk note.', 'Closed'),
(90008, 50008, 4012, 602, '2026-06-02', 'Well-child check, age 8',      'Z00.129',
 'Growth 60th percentile. Vision screen passed. Immunizations up to date.', 'Closed'),
(90009, 50009, 4007, 603, '2026-06-04', 'Palpitations',                 'R00.2',
 'Intermittent palpitations. ECG normal sinus. Holter ordered. Caffeine reduction advised.', 'Closed'),
(90010, 50010, 4011, 604, '2026-06-09', 'Hypothyroid follow-up',        'E03.9',
 'TSH 2.8 on levothyroxine 75mcg. Stable. Annual labs next visit.', 'Closed'),
(90011, 50012, 4010, 601, '2026-06-16', 'Sports physical, new patient', 'Z02.5',
 'Cleared for intramural soccer. No cardiac history. BMI normal.', 'Closed'),
(90012, 50014, 4001, 601, '2026-06-23', 'Lab review',                   'E78.5',
 'LDL 162. Discussed statin; patient wishes to try diet first. Recheck 3 months.', 'Closed'),
(90013, 50015, 4004, 603, '2026-06-25', 'Cardiology follow-up',         'I25.10',
 'Stable angina, no change in pattern. Stress test scheduled. Continue metoprolol.', 'Closed'),
(90014, 50009, 4007, 603, '2026-06-28', 'Holter results review',        'R00.2',
 'Holter: rare PVCs, no sustained arrhythmia. Reassurance. Return PRN.', 'Amended');

-- ==========================================
-- Table 8: lab_results
-- LOINC codes identify the tests
-- ==========================================
CREATE TABLE lab_results (
    lab_id INT PRIMARY KEY,
    enc_id INT NOT NULL REFERENCES encounters(enc_id),
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    loinc_cd VARCHAR(10),                -- LOINC test identifier
    test_nm VARCHAR(100),
    result_val VARCHAR(30),
    result_unit VARCHAR(20),
    ref_range VARCHAR(30),
    abnormal_flag CHAR(1),               -- N normal, H high, L low
    result_dt DATE
);

INSERT INTO lab_results VALUES
(81001, 90001, 4001, '2093-3',  'Cholesterol, total',    '228',  'mg/dL',  '<200',        'H', '2026-05-06'),
(81002, 90001, 4001, '13457-7', 'LDL cholesterol',       '162',  'mg/dL',  '<130',        'H', '2026-05-06'),
(81003, 90001, 4001, '2345-7',  'Glucose',               '94',   'mg/dL',  '70-99',       'N', '2026-05-06'),
(81004, 90003, 4002, '4548-4',  'Hemoglobin A1c',        '7.4',  '%',      '<7.0',        'H', '2026-05-12'),
(81005, 90003, 4002, '2160-0',  'Creatinine',            '1.1',  'mg/dL',  '0.7-1.3',     'N', '2026-05-12'),
(81006, 90007, 4008, '718-7',   'Hemoglobin',            '13.8', 'g/dL',   '13.5-17.5',   'N', '2026-05-28'),
(81007, 90009, 4007, '2157-6',  'CK',                    '88',   'U/L',    '30-200',      'N', '2026-06-04'),
(81008, 90010, 4011, '3016-3',  'TSH',                   '2.8',  'mIU/L',  '0.4-4.0',     'N', '2026-06-09'),
(81009, 90010, 4011, '3024-7',  'Free T4',               '1.1',  'ng/dL',  '0.8-1.8',     'N', '2026-06-09'),
(81010, 90012, 4001, '13457-7', 'LDL cholesterol',       '162',  'mg/dL',  '<130',        'H', '2026-06-22'),
(81011, 90013, 4004, '2093-3',  'Cholesterol, total',    '176',  'mg/dL',  '<200',        'N', '2026-06-24'),
(81012, 90008, 4012, '718-7',   'Hemoglobin',            '12.9', 'g/dL',   '11.5-14.5',   'N', '2026-06-02');

-- ==========================================
-- Table 9: prescriptions
-- NDC identifies the drug product; DEA schedule marks
-- controlled substances
-- ==========================================
CREATE TABLE prescriptions (
    rx_id INT PRIMARY KEY,
    enc_id INT NOT NULL REFERENCES encounters(enc_id),
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    prov_id INT NOT NULL REFERENCES providers(prov_id),
    ndc_cd VARCHAR(13),                  -- NDC 11-digit (5-4-2), fictional
    drug_nm VARCHAR(100),
    dose_txt VARCHAR(50),
    qty INT,
    refills INT,
    dea_schedule_cd VARCHAR(4),          -- II, III, IV, V or NULL (non-controlled)
    rx_dt DATE,
    rx_status VARCHAR(20) DEFAULT 'Active' -- Active, Completed, Cancelled
);

INSERT INTO prescriptions VALUES
(71001, 90002, 4004, 603, '00093-1039-01', 'Lisinopril',    '20 mg daily',        90, 3, NULL, '2026-05-07', 'Active'),
(71002, 90003, 4002, 602, '00093-7267-01', 'Metformin',     '1000 mg BID',        180, 3, NULL, '2026-05-12', 'Active'),
(71003, 90005, 4009, 605, '00168-0027-15', 'Triamcinolone', '0.1% cream BID',     1,  1, NULL, '2026-05-19', 'Active'),
(71004, 90006, 4003, 601, '00049-4900-30', 'Sertraline',    '50 mg daily',        90, 3, NULL, '2026-05-21', 'Active'),
(71005, 90007, 4008, 606, '00002-3235-30', 'Duloxetine',    '60 mg daily',        90, 2, NULL, '2026-05-27', 'Active'),
(71006, 90004, 4006, 604, '00045-0444-30', 'Naproxen',      '500 mg BID PRN',     60, 1, NULL, '2026-05-14', 'Active'),
(71007, 90013, 4004, 603, '00186-1090-39', 'Metoprolol',    '50 mg BID',          180, 3, NULL, '2026-06-25', 'Active'),
(71008, 90010, 4011, 604, '00074-4552-90', 'Levothyroxine', '75 mcg daily',       90, 3, NULL, '2026-06-09', 'Active'),
(71009, 90004, 4006, 604, '00406-0512-01', 'Tramadol',      '50 mg q6h PRN pain', 30, 0, 'IV', '2026-05-14', 'Completed'),
(71010, 90009, 4007, 603, '00378-1805-01', 'Lorazepam',     '0.5 mg PRN anxiety', 15, 0, 'IV', '2026-06-04', 'Completed');

-- ==========================================
-- Table 10: claims (revenue cycle)
-- CPT codes carry the billed procedures
-- ==========================================
CREATE TABLE claims (
    claim_id INT PRIMARY KEY,
    claim_no VARCHAR(14) NOT NULL UNIQUE, -- format CLM-nnnnnnnn
    enc_id INT NOT NULL REFERENCES encounters(enc_id),
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    payer_id INT REFERENCES payers(payer_id),
    cpt_cd VARCHAR(5),                    -- CPT procedure code
    billed_amt NUMERIC(10,2),
    allowed_amt NUMERIC(10,2),
    paid_amt NUMERIC(10,2),
    claim_dt DATE,
    claim_status VARCHAR(20) DEFAULT 'Submitted' -- Submitted, Paid, Denied, Appealed
);

INSERT INTO claims VALUES
(61001, 'CLM-40000001', 90001, 4001, 301, '99396', 285.00, 214.60, 214.60, '2026-05-08', 'Paid'),
(61002, 'CLM-40000002', 90002, 4004, 302, '99213', 168.00, 92.47,  92.47,  '2026-05-10', 'Paid'),
(61003, 'CLM-40000003', 90003, 4002, 302, '99214', 246.00, 131.25, 131.25, '2026-05-15', 'Paid'),
(61004, 'CLM-40000004', 90004, 4006, 301, '99204', 372.00, 289.14, 289.14, '2026-05-17', 'Paid'),
(61005, 'CLM-40000005', 90005, 4009, 304, '99203', 294.00, 226.80, 226.80, '2026-05-22', 'Paid'),
(61006, 'CLM-40000006', 90006, 4003, 303, '99214', 246.00, 118.92, 118.92, '2026-05-24', 'Paid'),
(61007, 'CLM-40000007', 90007, 4008, 302, '99213', 168.00, 92.47,  92.47,  '2026-05-30', 'Paid'),
(61008, 'CLM-40000008', 90008, 4012, 303, '99392', 255.00, 132.60, 132.60, '2026-06-05', 'Paid'),
(61009, 'CLM-40000009', 90009, 4007, 304, '93000', 143.00, 0.00,   0.00,   '2026-06-07', 'Appealed'),
(61010, 'CLM-40000010', 90010, 4011, 301, '99213', 168.00, 129.36, 129.36, '2026-06-12', 'Paid'),
(61011, 'CLM-40000011', 90011, 4010, 305, '99385', 240.00, 240.00, 120.00, '2026-06-18', 'Submitted'),
(61012, 'CLM-40000012', 90012, 4001, 301, '99213', 168.00, 129.36, 0.00,   '2026-06-26', 'Submitted'),
(61013, 'CLM-40000013', 90013, 4004, 302, '99214', 246.00, 131.25, 0.00,   '2026-06-28', 'Submitted'),
(61014, 'CLM-40000014', 90014, 4007, 304, '99212', 121.00, 0.00,   0.00,   '2026-06-30', 'Denied'),
(61015, 'CLM-40000015', 90001, 4001, 301, '80053', 89.00,  41.83,  41.83,  '2026-05-08', 'Paid');

-- ==========================================
-- Table 11: disclosure_log
-- HIPAA accounting of disclosures. PLANTED DEFECT:
-- entry 30005 discloses PHI for MARKETING without a
-- signed authorization - the compliance violation the
-- disclosure business rule measures.
-- ==========================================
CREATE TABLE disclosure_log (
    dl_id INT PRIMARY KEY,
    pt_id INT NOT NULL REFERENCES patients(pt_id),
    requested_by_txt VARCHAR(150),
    purpose_cd VARCHAR(20) NOT NULL,     -- TPO, PATIENT_REQUEST, LEGAL, RESEARCH, MARKETING
    disclosed_dt DATE,
    disclosed_by_staff_id INT REFERENCES staff(staff_id),
    authorization_flag BOOLEAN DEFAULT FALSE, -- signed authorization on file
    notes_txt TEXT
);

INSERT INTO disclosure_log VALUES
(30001, 4004, 'Boundary Waters Benefits - claims review',       'TPO',             '2026-05-20', 703, FALSE,
 'Records for claim CLM-40000002 adjudication. TPO - no authorization required.'),
(30002, 4007, 'Patient (records request, email)',               'PATIENT_REQUEST', '2026-06-06', 704, TRUE,
 'Full record copy to patient portal per signed request. Identity verified.'),
(30003, 4006, 'Olmsted County District Court - subpoena 26-CV-1188', 'LEGAL',      '2026-06-10', 704, FALSE,
 'Subpoena response, minimum necessary applied. Legal review completed.'),
(30004, 4001, 'University research registry - lipid outcomes study', 'RESEARCH',   '2026-06-15', 704, TRUE,
 'IRB-approved study; signed authorization on file. De-identification waived per authorization.'),
(30005, 4009, 'Dermaline Skincare LLC - product mailing list',  'MARKETING',       '2026-06-17', 707, FALSE,
 'Contact list shared for cosmetic product mailing. NO AUTHORIZATION ON FILE - flagged by privacy officer 2026-06-24, remediation open.'),
(30006, 4002, 'North Star Mutual Health - care coordination',   'TPO',             '2026-06-21', 703, FALSE,
 'Care-plan summary to payer case manager. TPO - no authorization required.');

-- ==========================================
-- Views (reporting layer)
-- ==========================================
CREATE VIEW clinic_visit_summary AS
SELECT c.cl_id, c.cl_name, c.cl_city,
       COUNT(a.appt_id)                                     AS appts_booked,
       SUM(CASE WHEN a.appt_status = 'Completed' THEN 1 ELSE 0 END) AS appts_completed,
       SUM(CASE WHEN a.appt_status = 'NoShow'    THEN 1 ELSE 0 END) AS no_shows
FROM clinics c
LEFT JOIN appointments a ON a.cl_id = c.cl_id
GROUP BY c.cl_id, c.cl_name, c.cl_city;

CREATE VIEW payer_claims_summary AS
SELECT p.payer_id, p.payer_nm, p.payer_type_cd,
       COUNT(cl.claim_id)                 AS claims_submitted,
       COALESCE(SUM(cl.billed_amt), 0)    AS total_billed,
       COALESCE(SUM(cl.paid_amt), 0)      AS total_paid,
       SUM(CASE WHEN cl.claim_status = 'Denied' THEN 1 ELSE 0 END) AS denials
FROM payers p
LEFT JOIN claims cl ON cl.payer_id = p.payer_id
GROUP BY p.payer_id, p.payer_nm, p.payer_type_cd;

CREATE VIEW provider_panel_summary AS
SELECT pr.prov_id, pr.last_nm, pr.specialty_cd, pr.npi_no,
       COUNT(DISTINCT pt.pt_id)           AS panel_size,
       COUNT(DISTINCT e.enc_id)           AS encounters_ytd
FROM providers pr
LEFT JOIN patients  pt ON pt.primary_prov_id = pr.prov_id
LEFT JOIN encounters e ON e.prov_id = pr.prov_id
GROUP BY pr.prov_id, pr.last_nm, pr.specialty_cd, pr.npi_no;

-- ==========================================
-- PDC catalog comments (harvested by Metadata Ingest)
-- ==========================================
COMMENT ON TABLE patients IS 'Patient demographic master - Protected Health Information (PHI) under HIPAA. Identity, contact details, primary provider and marketing consent. HIGHEST confidentiality in the clinical estate.';
COMMENT ON COLUMN patients.mrn IS 'Medical record number, format LHP-nnnnnn (e.g. LHP-300101). The patient identifier used across every system and document. CRITICAL identifier.';
COMMENT ON COLUMN patients.ssn IS 'Social Security number of the patient (fictional 9xx values in this lab). PHI + PII - permitted here for billing crossover, but must NEVER appear in free-text fields.';
COMMENT ON COLUMN patients.mkt_optout IS 'TRUE when the patient has opted out of marketing contact. HIPAA: marketing use of PHI requires signed authorization; extracts MUST suppress these rows. CRITICAL privacy field.';
COMMENT ON COLUMN patients.dob IS 'Date of birth. PHI and one of the 18 HIPAA identifiers.';

COMMENT ON TABLE providers IS 'Rendering and primary-care providers with NPI, specialty and licence. Business-contact data plus credentialing detail.';
COMMENT ON COLUMN providers.npi_no IS 'National Provider Identifier - the national 10-digit provider id (fictional values). CRITICAL identifier on every claim.';
COMMENT ON COLUMN providers.specialty_cd IS 'Specialty. Values: FAMMED, PEDS, CARDIO, DERM, ORTHO, BEHAV. Drives scheduling and referral routing.';

COMMENT ON TABLE appointments IS 'Scheduled visits across the six clinics. Status drives the no-show reporting the operations team tracks.';
COMMENT ON COLUMN appointments.appt_type_cd IS 'Visit type. Values: NEW, FOLLOWUP, PHYSICAL, TELEHEALTH, URGENT.';

COMMENT ON TABLE encounters IS 'Clinical encounters: chief complaint, primary ICD-10 diagnosis and the visit note. PHI - the note is free text and is the known leak path for identifiers (see note_txt).';
COMMENT ON COLUMN encounters.dx_cd IS 'Primary diagnosis, ICD-10-CM (e.g. E11.9 type 2 diabetes, I10 hypertension). Drives quality registries and claims coding.';
COMMENT ON COLUMN encounters.note_txt IS 'Free-text clinical note. DEFECT: two notes in this dataset carry a patient SSN in clear text - identifiers must never be documented in notes. The identification and quality workshops triangulate this field.';

COMMENT ON TABLE lab_results IS 'Laboratory results with LOINC test identifiers, values, reference ranges and abnormal flags. PHI.';
COMMENT ON COLUMN lab_results.loinc_cd IS 'LOINC code identifying the test (e.g. 4548-4 Hemoglobin A1c).';

COMMENT ON TABLE prescriptions IS 'Medication orders with NDC product codes. Controlled substances carry a DEA schedule - access to those rows is monitored.';
COMMENT ON COLUMN prescriptions.ndc_cd IS 'National Drug Code (11-digit, 5-4-2 format; fictional). Identifies the exact drug product.';
COMMENT ON COLUMN prescriptions.dea_schedule_cd IS 'DEA schedule for controlled substances (II, III, IV, V); NULL for non-controlled. CRITICAL for diversion monitoring.';

COMMENT ON TABLE claims IS 'Professional claims: CPT procedure, billed/allowed/paid amounts and adjudication status. Revenue-cycle data; PHI by linkage.';
COMMENT ON COLUMN claims.claim_no IS 'Claim number, format CLM-nnnnnnnn. Appears on remittances, statements and appeal correspondence. CRITICAL identifier.';
COMMENT ON COLUMN claims.cpt_cd IS 'CPT procedure code (e.g. 99213 established-patient office visit). Coding accuracy is audited quarterly.';

COMMENT ON TABLE payers IS 'Insurance payers and coverage programs with type and contact details.';
COMMENT ON COLUMN payers.payer_type_cd IS 'Coverage type. Values: COMMERCIAL, MEDICARE, MEDICAID, SELF_PAY. Drives billing rules and fee schedules.';

COMMENT ON TABLE disclosure_log IS 'HIPAA accounting of disclosures: who received PHI, for what purpose, and whether an authorization was on file. MARKETING and RESEARCH purposes require a signed authorization. Entry 30005 is the planted violation.';
COMMENT ON COLUMN disclosure_log.purpose_cd IS 'Disclosure purpose. Values: TPO (treatment/payment/operations - no authorization needed), PATIENT_REQUEST, LEGAL, RESEARCH, MARKETING. CRITICAL compliance field.';
COMMENT ON COLUMN disclosure_log.authorization_flag IS 'TRUE when a signed HIPAA authorization is on file. Required for MARKETING and RESEARCH disclosures.';

COMMENT ON TABLE clinics IS 'LHP clinic network reference data: six Minnesota clinics with manager and status.';
COMMENT ON TABLE staff IS 'Non-provider clinic staff master: role, clinic and status. Contains employee PII (names, email).';

-- ==========================================
-- Sample data complete - Lakeshore Health Partners
-- ==========================================
