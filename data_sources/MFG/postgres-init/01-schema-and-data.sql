-- ==========================================
-- PDC Business Analyst Course
-- Sample Data: Cascade Precision Components (CPC)
-- Fictional Pacific Northwest precision manufacturer
-- (hydraulic valves, fittings and manifolds)
-- ==========================================

CREATE SCHEMA IF NOT EXISTS cpc_mfg;
SET search_path TO cpc_mfg;

-- ==========================================
-- Table 1: plants (CPC manufacturing network)
-- ==========================================
CREATE TABLE plants (
    pl_id INT PRIMARY KEY,
    pl_name VARCHAR(100) NOT NULL UNIQUE,
    pl_addr VARCHAR(200),
    pl_city VARCHAR(50),
    pl_st CHAR(2),
    pl_zip VARCHAR(10),
    pl_phone VARCHAR(20),
    mgr_emp_id INT,                      -- plant manager (FK added after employees)
    open_dt DATE,
    pl_status VARCHAR(20) DEFAULT 'Active' -- Active, Idle, Closed
);

INSERT INTO plants VALUES
(10, 'Portland Swan Island',  '4200 N Basin Ave',      'Portland',  'OR', '97217', '503-555-0510', NULL, '1994-06-01', 'Active'),
(20, 'Salem Fairview',        '3800 Fairview Industrial Dr SE', 'Salem', 'OR', '97302', '503-555-0520', NULL, '2001-03-19', 'Active'),
(30, 'Eugene West 11th',      '2890 W 11th Ave',       'Eugene',    'OR', '97402', '541-555-0530', NULL, '2006-09-08', 'Active'),
(40, 'Vancouver Columbia',    '5115 NW Lower River Rd','Vancouver', 'WA', '98660', '360-555-0540', NULL, '2010-04-26', 'Active'),
(50, 'Spokane Valley',        '11515 E Montgomery Dr', 'Spokane',   'WA', '99206', '509-555-0550', NULL, '2015-11-02', 'Active'),
(60, 'Bend Juniper Ridge',    '2050 NE Aviation Way',  'Bend',      'OR', '97701', '541-555-0560', NULL, '2019-07-15', 'Idle');

-- ==========================================
-- Table 2: employees (plant staff)
-- ==========================================
CREATE TABLE employees (
    emp_id INT PRIMARY KEY,
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    pl_id INT NOT NULL REFERENCES plants(pl_id),
    role_cd VARCHAR(30),                 -- MACHINIST, QA_INSPECTOR, PLANT_MGR, BUYER, PLANNER, MFG_ENGINEER
    hire_dt DATE,
    emp_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO employees VALUES
(501, 'Nora',   'Whitaker', 'nora.whitaker@cascadeprecision.com', 10, 'PLANNER',      '2011-05-09', 'Active'),
(502, 'Felix',  'Okonkwo',  'felix.okonkwo@cascadeprecision.com', 10, 'MFG_ENGINEER', '2014-08-18', 'Active'),
(503, 'Yuki',   'Mori',     'yuki.mori@cascadeprecision.com',     20, 'QA_INSPECTOR', '2013-02-25', 'Active'),
(504, 'Silas',  'Grant',    'silas.grant@cascadeprecision.com',   40, 'PLANT_MGR',    '2016-10-03', 'Active'),
(505, 'Petra',  'Novak',    'petra.novak@cascadeprecision.com',   10, 'BUYER',        '2017-06-12', 'Active'),
(506, 'Andre',  'Gibson',   'andre.gibson@cascadeprecision.com',  30, 'MFG_ENGINEER', '2018-01-29', 'Active'),
(507, 'Mia',    'Torres',   'mia.torres@cascadeprecision.com',    50, 'MACHINIST',    '2021-04-05', 'Active'),
(508, 'Owen',   'Fitch',    'owen.fitch@cascadeprecision.com',    20, 'MACHINIST',    '2019-09-16', 'Inactive');

ALTER TABLE plants ADD CONSTRAINT fk_plants_mgr
    FOREIGN KEY (mgr_emp_id) REFERENCES employees(emp_id);
UPDATE plants SET mgr_emp_id = 504 WHERE pl_id = 40;
UPDATE plants SET mgr_emp_id = 501 WHERE pl_id = 10;

-- ==========================================
-- Table 3: suppliers (approved supplier list)
-- Pacific Alloys is SUSPENDED (plating escapes) -
-- see the planted PO defect in purchase_orders
-- ==========================================
CREATE TABLE suppliers (
    supplier_id INT PRIMARY KEY,
    supplier_nm VARCHAR(100) NOT NULL,
    contact_email VARCHAR(100),
    phone VARCHAR(20),
    city VARCHAR(50),
    st CHAR(2),
    asl_status VARCHAR(20) DEFAULT 'Approved', -- Approved, Conditional, Suspended
    status_dt DATE,                       -- date the ASL status took effect
    quality_rating_cd CHAR(1)             -- A, B, C
);

INSERT INTO suppliers VALUES
(201, 'Willamette Bar & Alloy',   'orders@willamettealloy.example',   '503-555-0601', 'Portland',   'OR', 'Approved',    '2024-01-15', 'A'),
(202, 'Pacific Alloys Finishing', 'sales@pacificalloys.example',      '360-555-0602', 'Longview',   'WA', 'Suspended',   '2026-05-30', 'C'),
(203, 'Cascade Seal & Gasket',    'ar@cascadeseal.example',           '541-555-0603', 'Eugene',     'OR', 'Approved',    '2023-08-01', 'A'),
(204, 'Inland Fastener Supply',   'billing@inlandfastener.example',   '509-555-0604', 'Spokane',    'WA', 'Approved',    '2024-06-10', 'B'),
(205, 'Sound Heat Treat',         'quotes@soundheattreat.example',    '253-555-0605', 'Tacoma',     'WA', 'Conditional', '2026-02-20', 'B'),
(206, 'Bridgetown Castings',      'edi@bridgetowncastings.example',   '503-555-0606', 'Portland',   'OR', 'Approved',    '2022-11-05', 'A');

-- ==========================================
-- Table 4: parts (item master)
-- Part number format CPC-nnnnn; unit_cost is
-- COMMERCIALLY SENSITIVE; safety_critical_flag drives
-- the traceability and MRB rules
-- ==========================================
CREATE TABLE parts (
    part_id INT PRIMARY KEY,
    part_no VARCHAR(10) NOT NULL UNIQUE, -- format CPC-nnnnn
    rev_cd CHAR(1) DEFAULT 'A',
    part_nm VARCHAR(100) NOT NULL,
    part_type_cd VARCHAR(10),            -- VALVE, FITTING, MANIFOLD, SEAL_KIT, ACTUATOR, RAW
    uom_cd VARCHAR(4) DEFAULT 'EA',      -- EA, KG, M
    unit_cost NUMERIC(10,2),             -- commercially sensitive
    safety_critical_flag BOOLEAN DEFAULT FALSE,
    part_status VARCHAR(20) DEFAULT 'Active' -- Active, Obsolete, Hold
);

INSERT INTO parts VALUES
(1001, 'CPC-84120', 'C', 'HV-Series Relief Valve Assembly',   'VALVE',    'EA', 214.60, TRUE,  'Active'),
(1002, 'CPC-84121', 'B', 'HV-Series Valve Body, Machined',    'VALVE',    'EA',  74.85, TRUE,  'Active'),
(1003, 'CPC-84122', 'A', 'HV-Series Poppet, Hardened',        'VALVE',    'EA',  18.20, TRUE,  'Active'),
(1004, 'CPC-84123', 'A', 'HV-Series Spring, Inconel',         'VALVE',    'EA',   6.45, TRUE,  'Active'),
(1005, 'CPC-70210', 'D', 'MX Manifold Block, 6-Port',         'MANIFOLD', 'EA', 168.90, FALSE, 'Active'),
(1006, 'CPC-70211', 'A', 'MX Manifold Blank, Cast',           'MANIFOLD', 'EA',  52.30, FALSE, 'Active'),
(1007, 'CPC-61180', 'B', 'QC Fitting, 3/8 NPT, Plated',       'FITTING',  'EA',   4.15, FALSE, 'Active'),
(1008, 'CPC-61181', 'A', 'QC Fitting, 1/2 NPT, Plated',       'FITTING',  'EA',   4.85, FALSE, 'Active'),
(1009, 'CPC-61190', 'A', 'Elbow Fitting, 90deg, Stainless',   'FITTING',  'EA',   7.60, FALSE, 'Active'),
(1010, 'CPC-93300', 'B', 'Seal Kit, HV-Series, Viton',        'SEAL_KIT', 'EA',  11.25, TRUE,  'Active'),
(1011, 'CPC-93301', 'A', 'O-Ring Set, MX Manifold',           'SEAL_KIT', 'EA',   3.90, FALSE, 'Active'),
(1012, 'CPC-55040', 'C', 'Linear Actuator, 2in Bore',         'ACTUATOR', 'EA', 342.75, TRUE,  'Active'),
(1013, 'CPC-55041', 'A', 'Actuator Rod, Chromed',             'ACTUATOR', 'EA',  38.10, TRUE,  'Active'),
(1014, 'CPC-10005', 'A', 'Bar Stock, 17-4PH, 1.25in',         'RAW',      'M',   21.40, FALSE, 'Active'),
(1015, 'CPC-10011', 'A', 'Bar Stock, 6061-T6, 2in',           'RAW',      'M',    9.85, FALSE, 'Active'),
(1016, 'CPC-10022', 'A', 'Casting, MX Blank, A356',           'RAW',      'EA',  31.70, FALSE, 'Active'),
(1017, 'CPC-10031', 'A', 'Spring Wire, Inconel X-750',        'RAW',      'KG',  84.00, TRUE,  'Active'),
(1018, 'CPC-61175', 'A', 'QC Fitting, 1/4 NPT, Legacy',       'FITTING',  'EA',   3.55, FALSE, 'Obsolete'),
(1019, 'CPC-93310', 'A', 'Backup Ring Set, PTFE',             'SEAL_KIT', 'EA',   2.95, FALSE, 'Active'),
(1020, 'CPC-84119', 'A', 'HV-Series Adjustment Cap',          'VALVE',    'EA',   9.30, FALSE, 'Active');

-- ==========================================
-- Table 5: boms (bill of materials - the genealogy)
-- Parent/child part links with quantity per assembly.
-- This is the catalog's strongest LINEAGE story.
-- ==========================================
CREATE TABLE boms (
    bom_id INT PRIMARY KEY,
    parent_part_id INT NOT NULL REFERENCES parts(part_id),
    child_part_id INT NOT NULL REFERENCES parts(part_id),
    qty_per NUMERIC(8,3) NOT NULL,
    effective_dt DATE,
    bom_status VARCHAR(20) DEFAULT 'Released' -- Draft, Released, Superseded
);

INSERT INTO boms VALUES
(3001, 1001, 1002, 1,     '2025-01-10', 'Released'),  -- valve assy <- body
(3002, 1001, 1003, 1,     '2025-01-10', 'Released'),  -- valve assy <- poppet
(3003, 1001, 1004, 1,     '2025-01-10', 'Released'),  -- valve assy <- spring
(3004, 1001, 1010, 1,     '2025-01-10', 'Released'),  -- valve assy <- seal kit
(3005, 1001, 1020, 1,     '2025-01-10', 'Released'),  -- valve assy <- adj cap
(3006, 1002, 1014, 0.35,  '2025-01-10', 'Released'),  -- body <- 17-4PH bar (m)
(3007, 1003, 1014, 0.08,  '2025-01-10', 'Released'),  -- poppet <- 17-4PH bar (m)
(3008, 1004, 1017, 0.012, '2025-01-10', 'Released'),  -- spring <- inconel wire (kg)
(3009, 1005, 1006, 1,     '2024-06-02', 'Released'),  -- manifold <- cast blank
(3010, 1005, 1011, 1,     '2024-06-02', 'Released'),  -- manifold <- o-ring set
(3011, 1006, 1016, 1,     '2024-06-02', 'Released'),  -- blank <- casting
(3012, 1012, 1013, 1,     '2023-09-14', 'Released'),  -- actuator <- rod
(3013, 1012, 1010, 1,     '2023-09-14', 'Released'),  -- actuator <- seal kit
(3014, 1007, 1015, 0.06,  '2022-03-20', 'Released');  -- fitting <- 6061 bar (m)

-- ==========================================
-- Table 6: purchase_orders
-- PLANTED DEFECT: PO-30000112 was issued to Pacific
-- Alloys AFTER its 2026-05-30 suspension - the ASL
-- control the purchasing business rule measures.
-- ==========================================
CREATE TABLE purchase_orders (
    po_id INT PRIMARY KEY,
    po_no VARCHAR(14) NOT NULL UNIQUE,   -- format PO-nnnnnnnn
    supplier_id INT NOT NULL REFERENCES suppliers(supplier_id),
    part_id INT NOT NULL REFERENCES parts(part_id),
    qty_ordered INT NOT NULL,
    unit_price NUMERIC(10,2),
    order_dt DATE NOT NULL,
    promised_dt DATE,
    po_status VARCHAR(20) DEFAULT 'Open' -- Open, Received, Cancelled, Closed
);

INSERT INTO purchase_orders VALUES
(7001, 'PO-30000101', 201, 1014, 240, 20.15, '2026-04-06', '2026-04-27', 'Received'),
(7002, 'PO-30000102', 201, 1015, 180,  9.10, '2026-04-06', '2026-04-27', 'Received'),
(7003, 'PO-30000103', 206, 1016,  60, 29.85, '2026-04-14', '2026-05-12', 'Received'),
(7004, 'PO-30000104', 203, 1010, 400, 10.05, '2026-04-20', '2026-05-08', 'Received'),
(7005, 'PO-30000105', 203, 1011, 350,  3.40, '2026-04-20', '2026-05-08', 'Received'),
(7006, 'PO-30000106', 204, 1019, 500,  2.60, '2026-05-02', '2026-05-22', 'Received'),
(7007, 'PO-30000107', 202, 1007, 800,  3.75, '2026-05-11', '2026-06-01', 'Received'),
(7008, 'PO-30000108', 205, 1003, 300, 16.40, '2026-05-18', '2026-06-15', 'Received'),
(7009, 'PO-30000109', 201, 1017,  25, 79.50, '2026-05-26', '2026-06-19', 'Received'),
(7010, 'PO-30000110', 206, 1016,  40, 30.10, '2026-06-08', '2026-07-06', 'Open'),
(7011, 'PO-30000111', 203, 1010, 250, 10.05, '2026-06-15', '2026-07-03', 'Open'),
(7012, 'PO-30000112', 202, 1008, 600,  4.40, '2026-06-18', '2026-07-10', 'Open');

-- ==========================================
-- Table 7: work_orders (production)
-- ==========================================
CREATE TABLE work_orders (
    wo_id INT PRIMARY KEY,
    wo_no VARCHAR(14) NOT NULL UNIQUE,   -- format WO-nnnnnnnn
    part_id INT NOT NULL REFERENCES parts(part_id),
    pl_id INT NOT NULL REFERENCES plants(pl_id),
    qty_planned INT NOT NULL,
    qty_completed INT DEFAULT 0,
    qty_scrapped INT DEFAULT 0,
    start_dt DATE,
    due_dt DATE,
    wo_status VARCHAR(20) DEFAULT 'Planned' -- Planned, Released, InProcess, Complete, Closed
);

INSERT INTO work_orders VALUES
(8001, 'WO-50000201', 1002, 10, 150, 148, 2, '2026-04-28', '2026-05-15', 'Closed'),
(8002, 'WO-50000202', 1003, 10, 160, 155, 5, '2026-05-01', '2026-05-18', 'Closed'),
(8003, 'WO-50000203', 1004, 20, 200, 200, 0, '2026-05-05', '2026-05-20', 'Closed'),
(8004, 'WO-50000204', 1001, 10, 140, 138, 2, '2026-05-19', '2026-06-09', 'Closed'),
(8005, 'WO-50000205', 1006, 30,  55,  54, 1, '2026-05-12', '2026-05-29', 'Closed'),
(8006, 'WO-50000206', 1005, 30,  50,  50, 0, '2026-06-01', '2026-06-19', 'Complete'),
(8007, 'WO-50000207', 1013, 40,  90,  88, 2, '2026-05-26', '2026-06-12', 'Closed'),
(8008, 'WO-50000208', 1012, 40,  80,   0, 0, '2026-06-22', '2026-07-17', 'InProcess'),
(8009, 'WO-50000209', 1009, 50, 300,   0, 0, '2026-07-01', '2026-07-24', 'Released'),
(8010, 'WO-50000210', 1001, 10, 120,   0, 0, '2026-07-06', '2026-07-31', 'Planned');

-- ==========================================
-- Table 8: lots (traceability spine)
-- PLANTED DEFECT: lots 6006 and 6011 are Released with
-- NO Certificate of Conformance on file (coc_flag FALSE)
-- - the AS9100 traceability violation the flagship rule
-- measures. Lot 6003 was later RECALLED (plating escape
-- from the suspended supplier).
-- ==========================================
CREATE TABLE lots (
    lot_id INT PRIMARY KEY,
    lot_no VARCHAR(14) NOT NULL UNIQUE,  -- format LOT-2026-nnnn
    part_id INT NOT NULL REFERENCES parts(part_id),
    wo_id INT REFERENCES work_orders(wo_id),        -- NULL for purchased lots
    supplier_id INT REFERENCES suppliers(supplier_id), -- NULL for made lots
    qty INT NOT NULL,
    mfg_dt DATE,
    coc_flag BOOLEAN DEFAULT FALSE,      -- certificate of conformance on file
    lot_status VARCHAR(20) DEFAULT 'Quarantine' -- Quarantine, Released, Consumed, Recalled
);

INSERT INTO lots VALUES
(6001, 'LOT-2026-0101', 1014, NULL, 201, 240, '2026-04-24', TRUE,  'Consumed'),
(6002, 'LOT-2026-0102', 1015, NULL, 201, 180, '2026-04-24', TRUE,  'Consumed'),
(6003, 'LOT-2026-0107', 1007, NULL, 202, 800, '2026-05-29', TRUE,  'Recalled'),
(6004, 'LOT-2026-0110', 1010, NULL, 203, 400, '2026-05-06', TRUE,  'Released'),
(6005, 'LOT-2026-0111', 1011, NULL, 203, 350, '2026-05-06', TRUE,  'Consumed'),
(6006, 'LOT-2026-0117', 1003, NULL, 205, 300, '2026-06-12', FALSE, 'Released'),
(6007, 'LOT-2026-0121', 1016, NULL, 206,  60, '2026-05-09', TRUE,  'Consumed'),
(6008, 'LOT-2026-0125', 1017, NULL, 201,  25, '2026-06-17', TRUE,  'Released'),
(6009, 'LOT-2026-0131', 1002, 8001, NULL, 148, '2026-05-15', TRUE,  'Consumed'),
(6010, 'LOT-2026-0132', 1003, 8002, NULL, 155, '2026-05-18', TRUE,  'Consumed'),
(6011, 'LOT-2026-0133', 1004, 8003, NULL, 200, '2026-05-20', FALSE, 'Released'),
(6012, 'LOT-2026-0138', 1001, 8004, NULL, 138, '2026-06-09', TRUE,  'Released'),
(6013, 'LOT-2026-0140', 1006, 8005, NULL,  54, '2026-05-29', TRUE,  'Consumed'),
(6014, 'LOT-2026-0142', 1005, 8006, NULL,  50, '2026-06-19', TRUE,  'Released'),
(6015, 'LOT-2026-0145', 1013, 8007, NULL,  88, '2026-06-12', TRUE,  'Released'),
(6016, 'LOT-2026-0150', 1019, NULL, 204, 500, '2026-05-21', TRUE,  'Released');

-- ==========================================
-- Table 9: inspections
-- ==========================================
CREATE TABLE inspections (
    insp_id INT PRIMARY KEY,
    lot_id INT NOT NULL REFERENCES lots(lot_id),
    insp_type_cd VARCHAR(12),            -- INCOMING, IN_PROCESS, FINAL, AUDIT
    insp_dt DATE,
    inspector_emp_id INT REFERENCES employees(emp_id),
    sample_qty INT,
    defects_found INT DEFAULT 0,
    result_cd VARCHAR(12) DEFAULT 'PASS' -- PASS, FAIL, CONDITIONAL
);

INSERT INTO inspections VALUES
(9101, 6001, 'INCOMING',   '2026-04-27', 503, 13, 0, 'PASS'),
(9102, 6003, 'INCOMING',   '2026-06-02', 503, 32, 1, 'CONDITIONAL'),
(9103, 6004, 'INCOMING',   '2026-05-07', 503, 20, 0, 'PASS'),
(9104, 6006, 'INCOMING',   '2026-06-15', 503, 18, 0, 'PASS'),
(9105, 6007, 'INCOMING',   '2026-05-12', 503, 8,  0, 'PASS'),
(9106, 6009, 'IN_PROCESS', '2026-05-10', 503, 12, 1, 'PASS'),
(9107, 6009, 'FINAL',      '2026-05-15', 503, 15, 0, 'PASS'),
(9108, 6010, 'FINAL',      '2026-05-18', 503, 16, 2, 'CONDITIONAL'),
(9109, 6011, 'FINAL',      '2026-05-20', 503, 20, 0, 'PASS'),
(9110, 6012, 'FINAL',      '2026-06-09', 503, 14, 0, 'PASS'),
(9111, 6014, 'FINAL',      '2026-06-19', 503, 10, 0, 'PASS'),
(9112, 6003, 'AUDIT',      '2026-06-20', 503, 50, 9, 'FAIL');

-- ==========================================
-- Table 10: ncrs (nonconformance reports)
-- PLANTED DEFECT: NCR-2026-014 is CRITICAL severity
-- dispositioned USE_AS_IS with NO MRB approval on file
-- (mrb_approval_flag FALSE) - the quality-system
-- violation the MRB business rule measures.
-- ==========================================
CREATE TABLE ncrs (
    ncr_id INT PRIMARY KEY,
    ncr_no VARCHAR(14) NOT NULL UNIQUE,  -- format NCR-2026-nnn
    lot_id INT NOT NULL REFERENCES lots(lot_id),
    part_id INT NOT NULL REFERENCES parts(part_id),
    defect_cd VARCHAR(12),               -- DIM_OOT, SURFACE, MATERIAL, PLATING, DOC
    severity_cd VARCHAR(10),             -- MINOR, MAJOR, CRITICAL
    disposition_cd VARCHAR(12),          -- USE_AS_IS, REWORK, SCRAP, RTV
    mrb_approval_flag BOOLEAN DEFAULT FALSE, -- MRB sign-off (required for USE_AS_IS on MAJOR/CRITICAL)
    opened_dt DATE,
    opened_by_emp_id INT REFERENCES employees(emp_id),
    closed_dt DATE,
    ncr_status VARCHAR(20) DEFAULT 'Open' -- Open, Dispositioned, Closed
);

INSERT INTO ncrs VALUES
(4001, 'NCR-2026-009', 6010, 1003, 'DIM_OOT',  'MAJOR',    'REWORK',    TRUE,  '2026-05-18', 503, '2026-05-24', 'Closed'),
(4002, 'NCR-2026-011', 6009, 1002, 'SURFACE',  'MINOR',    'USE_AS_IS', TRUE,  '2026-05-10', 503, '2026-05-12', 'Closed'),
(4003, 'NCR-2026-014', 6006, 1003, 'MATERIAL', 'CRITICAL', 'USE_AS_IS', FALSE, '2026-06-16', 503, NULL,         'Dispositioned'),
(4004, 'NCR-2026-016', 6003, 1007, 'PLATING',  'MAJOR',    'RTV',       TRUE,  '2026-06-20', 503, '2026-06-28', 'Closed'),
(4005, 'NCR-2026-017', 6013, 1006, 'DIM_OOT',  'MINOR',    'REWORK',    TRUE,  '2026-06-02', 506, '2026-06-05', 'Closed'),
(4006, 'NCR-2026-019', 6011, 1004, 'DOC',      'MINOR',    'USE_AS_IS', TRUE,  '2026-06-24', 503, NULL,         'Open');

-- ==========================================
-- Table 11: shipments (customer deliveries)
-- Ship 5504 delivered fittings from the lot that was
-- later RECALLED - the traceability query the recall
-- letter in the document store follows.
-- ==========================================
CREATE TABLE shipments (
    ship_id INT PRIMARY KEY,
    ship_no VARCHAR(14) NOT NULL UNIQUE, -- format SH-nnnnnnnn
    customer_nm VARCHAR(100) NOT NULL,
    part_id INT NOT NULL REFERENCES parts(part_id),
    lot_id INT NOT NULL REFERENCES lots(lot_id),
    qty INT NOT NULL,
    ship_dt DATE,
    dest_city VARCHAR(50),
    dest_st CHAR(2),
    ship_status VARCHAR(20) DEFAULT 'Shipped' -- Staged, Shipped, Delivered, Returned
);

INSERT INTO shipments VALUES
(5501, 'SH-70000301', 'Columbia Hydraulics Inc',    1001, 6012, 60, '2026-06-11', 'Seattle',    'WA', 'Delivered'),
(5502, 'SH-70000302', 'Columbia Hydraulics Inc',    1001, 6012, 40, '2026-06-18', 'Seattle',    'WA', 'Delivered'),
(5503, 'SH-70000303', 'High Desert Equipment Co',   1005, 6014, 25, '2026-06-23', 'Boise',      'ID', 'Delivered'),
(5504, 'SH-70000304', 'Tidewater Marine Systems',   1007, 6003, 500,'2026-06-05', 'Astoria',    'OR', 'Returned'),
(5505, 'SH-70000305', 'Tidewater Marine Systems',   1010, 6004, 120,'2026-06-05', 'Astoria',    'OR', 'Delivered'),
(5506, 'SH-70000306', 'Klamath Ag Machinery',       1019, 6016, 200,'2026-06-14', 'Klamath Falls','OR','Delivered'),
(5507, 'SH-70000307', 'Puget Actuation LLC',        1013, 6015, 30, '2026-06-16', 'Everett',    'WA', 'Delivered'),
(5508, 'SH-70000308', 'High Desert Equipment Co',   1005, 6014, 15, '2026-07-01', 'Boise',      'ID', 'Shipped'),
(5509, 'SH-70000309', 'Columbia Hydraulics Inc',    1010, 6004, 80, '2026-07-02', 'Seattle',    'WA', 'Shipped'),
(5510, 'SH-70000310', 'Cascade Rail Services',      1013, 6015, 10, '2026-07-03', 'Portland',   'OR', 'Staged');

-- ==========================================
-- Views (reporting layer)
-- ==========================================
CREATE VIEW plant_production_summary AS
SELECT p.pl_id, p.pl_name, p.pl_city,
       COUNT(w.wo_id)                     AS work_orders,
       COALESCE(SUM(w.qty_completed), 0)  AS units_completed,
       COALESCE(SUM(w.qty_scrapped), 0)   AS units_scrapped
FROM plants p
LEFT JOIN work_orders w ON w.pl_id = p.pl_id
GROUP BY p.pl_id, p.pl_name, p.pl_city;

CREATE VIEW supplier_quality_summary AS
SELECT s.supplier_id, s.supplier_nm, s.asl_status, s.quality_rating_cd,
       COUNT(DISTINCT po.po_id)           AS pos_placed,
       COUNT(DISTINCT l.lot_id)           AS lots_received,
       COUNT(DISTINCT n.ncr_id)           AS ncrs_raised
FROM suppliers s
LEFT JOIN purchase_orders po ON po.supplier_id = s.supplier_id
LEFT JOIN lots l             ON l.supplier_id = s.supplier_id
LEFT JOIN ncrs n             ON n.lot_id = l.lot_id
GROUP BY s.supplier_id, s.supplier_nm, s.asl_status, s.quality_rating_cd;

CREATE VIEW lot_traceability AS
SELECT l.lot_id, l.lot_no, pt.part_no, pt.part_nm, pt.safety_critical_flag,
       l.lot_status, l.coc_flag,
       w.wo_no, s.supplier_nm,
       COUNT(sh.ship_id)                  AS shipments_made
FROM lots l
JOIN parts pt        ON pt.part_id = l.part_id
LEFT JOIN work_orders w ON w.wo_id = l.wo_id
LEFT JOIN suppliers s   ON s.supplier_id = l.supplier_id
LEFT JOIN shipments sh  ON sh.lot_id = l.lot_id
GROUP BY l.lot_id, l.lot_no, pt.part_no, pt.part_nm, pt.safety_critical_flag,
         l.lot_status, l.coc_flag, w.wo_no, s.supplier_nm;

-- ==========================================
-- PDC catalog comments (harvested by Metadata Ingest)
-- ==========================================
COMMENT ON TABLE parts IS 'Item master: part number, revision, type, cost and the safety-critical flag. Unit cost is COMMERCIALLY SENSITIVE - internal use only.';
COMMENT ON COLUMN parts.part_no IS 'Part number, format CPC-nnnnn (e.g. CPC-84120). The identifier on every drawing, traveler, lot and certificate. CRITICAL identifier.';
COMMENT ON COLUMN parts.unit_cost IS 'Standard unit cost. COMMERCIALLY SENSITIVE - do not expose in customer-facing systems or quotes without markup review.';
COMMENT ON COLUMN parts.safety_critical_flag IS 'TRUE for parts whose failure endangers people or equipment. Drives full lot traceability, CoC requirements and MRB authority. CRITICAL governance field.';
COMMENT ON COLUMN parts.rev_cd IS 'Engineering revision letter. A shipped part must match the revision on its certificate.';

COMMENT ON TABLE boms IS 'Bill of materials: parent/child part links with quantity per assembly. The product genealogy - the catalog''s strongest lineage story.';
COMMENT ON COLUMN boms.qty_per IS 'Quantity of the child consumed per unit of the parent (supports fractional units for bar stock and wire).';

COMMENT ON TABLE suppliers IS 'Approved supplier list (ASL) with status and quality rating. POs may only be placed with Approved or Conditional suppliers.';
COMMENT ON COLUMN suppliers.asl_status IS 'ASL status. Values: Approved, Conditional, Suspended. A Suspended supplier must receive NO new purchase orders. CRITICAL control field.';

COMMENT ON TABLE purchase_orders IS 'Purchase orders to ASL suppliers. Unit prices are commercially sensitive.';
COMMENT ON COLUMN purchase_orders.po_no IS 'Purchase order number, format PO-nnnnnnnn. CRITICAL identifier on receipts and supplier certificates.';

COMMENT ON TABLE work_orders IS 'Production work orders: planned/completed/scrapped quantities per plant. Scrap feeds the cost-of-quality reporting.';
COMMENT ON COLUMN work_orders.wo_no IS 'Work order number, format WO-nnnnnnnn. Appears on travelers and lot records. CRITICAL identifier.';

COMMENT ON TABLE lots IS 'Lot master - the traceability spine. Every made or purchased batch, its source (work order or supplier), certificate status and lifecycle. AS9100 requires an unbroken lot chain for safety-critical parts.';
COMMENT ON COLUMN lots.lot_no IS 'Lot number, format LOT-2026-nnnn. The traceability identifier on certificates, NCRs and shipments. CRITICAL identifier.';
COMMENT ON COLUMN lots.coc_flag IS 'TRUE when a Certificate of Conformance is on file. DEFECT: two Released lots in this dataset carry no CoC - a lot must not be Released without one. The quality workshops triangulate this field.';
COMMENT ON COLUMN lots.lot_status IS 'Lifecycle: Quarantine, Released, Consumed, Recalled. Recalled lots trigger the customer-notification traceability query.';

COMMENT ON TABLE inspections IS 'Incoming, in-process, final and audit inspections per lot: samples, defects and result.';
COMMENT ON COLUMN inspections.result_cd IS 'Inspection outcome. Values: PASS, FAIL, CONDITIONAL. FAIL and CONDITIONAL feed the NCR process.';

COMMENT ON TABLE ncrs IS 'Nonconformance reports: defect, severity, disposition and MRB sign-off. USE_AS_IS on MAJOR/CRITICAL severity requires Material Review Board approval. Entry NCR-2026-014 is the planted violation.';
COMMENT ON COLUMN ncrs.disposition_cd IS 'Disposition. Values: USE_AS_IS, REWORK, SCRAP, RTV (return to vendor). CRITICAL quality decision.';
COMMENT ON COLUMN ncrs.mrb_approval_flag IS 'TRUE when the Material Review Board has signed the disposition. Required for USE_AS_IS on MAJOR or CRITICAL severity. CRITICAL control field.';

COMMENT ON TABLE shipments IS 'Customer shipments by part and lot - the outbound half of traceability. A recalled lot''s shipments identify every affected customer.';
COMMENT ON COLUMN shipments.customer_nm IS 'Customer legal name. Business-contact data, not consumer PII.';

COMMENT ON TABLE plants IS 'CPC plant network reference data: six Pacific Northwest sites with manager and status.';
COMMENT ON TABLE employees IS 'Plant staff master: role, plant and status. The only individual PII in the estate (names, email).';

-- ==========================================
-- Sample data complete - Cascade Precision Components
-- ==========================================
