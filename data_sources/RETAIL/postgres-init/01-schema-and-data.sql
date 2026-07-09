-- ==========================================
-- PDC Business Analyst Course
-- Sample Data: Canyon Trail Outfitters (CTO)
-- Fictional Arizona outdoor-gear retailer
-- ==========================================

CREATE SCHEMA IF NOT EXISTS cto_retail;
SET search_path TO cto_retail;

-- ==========================================
-- Table 1: stores (CTO store network)
-- ==========================================
CREATE TABLE stores (
    st_id INT PRIMARY KEY,
    st_name VARCHAR(100) NOT NULL UNIQUE,
    st_addr VARCHAR(200),
    st_city VARCHAR(50),
    st_county VARCHAR(30),
    st_zip VARCHAR(10),
    st_phone VARCHAR(20),
    mgr_emp_id INT,                      -- manager (FK added after employees)
    open_dt DATE,
    st_status VARCHAR(20) DEFAULT 'Open' -- Open, Closed, Remodeling
);

INSERT INTO stores VALUES
(10, 'Phoenix Camelback',   '2415 E Camelback Rd',  'Phoenix',     'Maricopa', '85016', '602-555-0210', NULL, '2002-03-15', 'Open'),
(20, 'Tempe Mill Avenue',   '520 S Mill Ave',       'Tempe',       'Maricopa', '85281', '480-555-0220', NULL, '2006-11-04', 'Open'),
(30, 'Tucson Speedway',     '4880 E Speedway Blvd', 'Tucson',      'Pima',     '85712', '520-555-0230', NULL, '2004-05-22', 'Open'),
(40, 'Casa Grande Outlet',  '2200 E Florence Blvd', 'Casa Grande', 'Pinal',    '85122', '520-555-0240', NULL, '2014-08-09', 'Open'),
(50, 'Globe Basecamp',      '388 N Broad St',       'Globe',       'Gila',     '85501', '928-555-0250', NULL, '2018-04-21', 'Open'),
(60, 'Prescott Whiskey Row','130 S Montezuma St',   'Prescott',    'Yavapai',  '86301', '928-555-0260', NULL, '2010-06-30', 'Open');

-- ==========================================
-- Table 2: employees (store staff)
-- ==========================================
CREATE TABLE employees (
    emp_id INT PRIMARY KEY,
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    st_id INT NOT NULL REFERENCES stores(st_id),
    role_cd VARCHAR(30),                 -- CASHIER, SALES_ASSOC, ST_MGR, BUYER, LP_OFFICER
    hire_dt DATE,
    emp_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO employees VALUES
(801, 'Sofia',  'Marin',    'sofia.marin@canyontrailoutfitters.com',   10, 'ST_MGR',      '2013-02-11', 'Active'),
(802, 'Derek',  'Boone',    'derek.boone@canyontrailoutfitters.com',   10, 'BUYER',       '2016-07-25', 'Active'),
(803, 'Alicia', 'Vega',     'alicia.vega@canyontrailoutfitters.com',   10, 'LP_OFFICER',  '2015-10-05', 'Active'),
(804, 'Ken',    'Tanaka',   'ken.tanaka@canyontrailoutfitters.com',    20, 'ST_MGR',      '2017-03-13', 'Active'),
(805, 'Tessa',  'Nguyen',   'tessa.nguyen@canyontrailoutfitters.com',  20, 'SALES_ASSOC', '2019-06-17', 'Active'),
(806, 'Leo',    'Fischer',  'leo.fischer@canyontrailoutfitters.com',   30, 'ST_MGR',      '2012-09-03', 'Active'),
(807, 'Casey',  'Holt',     'casey.holt@canyontrailoutfitters.com',    40, 'CASHIER',     '2021-11-29', 'Active'),
(808, 'Robin',  'Pierce',   'robin.pierce@canyontrailoutfitters.com',  60, 'SALES_ASSOC', '2020-02-18', 'Inactive');

ALTER TABLE stores ADD CONSTRAINT fk_stores_mgr
    FOREIGN KEY (mgr_emp_id) REFERENCES employees(emp_id);
UPDATE stores SET mgr_emp_id = 801 WHERE st_id = 10;
UPDATE stores SET mgr_emp_id = 804 WHERE st_id = 20;
UPDATE stores SET mgr_emp_id = 806 WHERE st_id = 30;

-- ==========================================
-- Table 3: customers (loyalty program members)
-- opted_out_marketing TRUE + live email = the planted
-- privacy defect (3 rows) the flagship rule measures
-- ==========================================
CREATE TABLE customers (
    cust_id INT PRIMARY KEY,
    loyalty_no VARCHAR(12) NOT NULL UNIQUE,  -- format CTO-nnnnnn
    first_nm VARCHAR(50) NOT NULL,
    last_nm VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    addr1 VARCHAR(100),
    city VARCHAR(50),
    st CHAR(2),
    zip VARCHAR(10),
    joined_dt DATE,
    loyalty_tier VARCHAR(10) DEFAULT 'BASE', -- BASE, SILVER, GOLD
    opted_out_marketing BOOLEAN DEFAULT FALSE,
    cust_status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO customers VALUES
(7001, 'CTO-200101', 'Alicia',  'Mendoza',  'alicia.mendoza@email.com',   '602-555-1101', '4181 N 24th St',      'Phoenix',     'AZ', '85016', '2019-04-02', 'GOLD',   FALSE, 'Active'),
(7002, 'CTO-200102', 'Brian',   'Okafor',   'brian.okafor@email.com',     '480-555-1102', '77 E Broadway Rd',    'Tempe',       'AZ', '85282', '2020-01-19', 'SILVER', TRUE,  'Active'),
(7003, 'CTO-200103', 'Carmen',  'Delgado',  'carmen.delgado@email.com',   '520-555-1103', '2310 E 5th St',       'Tucson',      'AZ', '85719', '2018-09-27', 'GOLD',   FALSE, 'Active'),
(7004, 'CTO-200104', 'Dmitri',  'Volkov',   'dmitri.volkov@email.com',    '520-555-1104', '901 W Cottonwood Ln', 'Casa Grande', 'AZ', '85122', '2021-06-13', 'BASE',   TRUE,  'Active'),
(7005, 'CTO-200105', 'Erin',    'Whitfield','erin.whitfield@email.com',   '928-555-1105', '1220 E Ash St',       'Globe',       'AZ', '85501', '2022-02-01', 'BASE',   FALSE, 'Active'),
(7006, 'CTO-200106', 'Felix',   'Arroyo',   'felix.arroyo@email.com',     '928-555-1106', '425 S Granite St',    'Prescott',    'AZ', '86303', '2017-12-08', 'SILVER', FALSE, 'Active'),
(7007, 'CTO-200107', 'Grace',   'Liang',    'grace.liang@email.com',      '602-555-1107', '3626 W Maryland Ave', 'Phoenix',     'AZ', '85019', '2020-10-22', 'GOLD',   TRUE,  'Active'),
(7008, 'CTO-200108', 'Hector',  'Fuentes',  'hector.fuentes@email.com',   '480-555-1108', '1815 E Apache Blvd',  'Tempe',       'AZ', '85281', '2023-03-11', 'BASE',   FALSE, 'Active'),
(7009, 'CTO-200109', 'Isabel',  'Romero',   'isabel.romero@email.com',    '520-555-1109', '640 N Alvernon Way',  'Tucson',      'AZ', '85711', '2019-08-30', 'SILVER', FALSE, 'Active'),
(7010, 'CTO-200110', 'Jonas',   'Bergman',  'jonas.bergman@email.com',    '928-555-1110', '212 W Gurley St',     'Prescott',    'AZ', '86301', '2021-05-17', 'BASE',   FALSE, 'Active'),
(7011, 'CTO-200111', 'Keiko',   'Sato',     'keiko.sato@email.com',       '602-555-1111', '5150 N 7th Ave',      'Phoenix',     'AZ', '85013', '2022-08-24', 'SILVER', FALSE, 'Active'),
(7012, 'CTO-200112', 'Luis',    'Cabrera',  'luis.cabrera@email.com',     '520-555-1112', '3400 E Ajo Way',      'Tucson',      'AZ', '85713', '2023-01-09', 'BASE',   FALSE, 'Active'),
(7013, 'CTO-200113', 'Maren',   'Ostberg',  'maren.ostberg@email.com',    '928-555-1113', '990 S Hill St',       'Globe',       'AZ', '85501', '2024-04-15', 'BASE',   FALSE, 'Active');

-- ==========================================
-- Table 4: suppliers (merchandise vendors)
-- ==========================================
CREATE TABLE suppliers (
    supplier_id INT PRIMARY KEY,
    supplier_nm VARCHAR(100) NOT NULL,
    contact_email VARCHAR(100),
    phone VARCHAR(20),
    city VARCHAR(50),
    st CHAR(2),
    terms_cd VARCHAR(10),                -- NET30, NET45, NET60, PREPAID
    supplier_status VARCHAR(20) DEFAULT 'Approved'
);

INSERT INTO suppliers VALUES
(501, 'Alpine Peak Gear',     'orders@alpinepeakgear.example',    '303-555-0501', 'Denver',        'CO', 'NET30',   'Approved'),
(502, 'Desert Sun Apparel',   'sales@desertsunapparel.example',   '602-555-0502', 'Phoenix',       'AZ', 'NET45',   'Approved'),
(503, 'Rio Verde Watersports','accounts@rioverdews.example',      '480-555-0503', 'Scottsdale',    'AZ', 'NET30',   'Approved'),
(504, 'Granite Ridge Footwear','ar@graniteridgefw.example',       '801-555-0504', 'Salt Lake City','UT', 'NET60',   'Approved'),
(505, 'Sierra Trail Foods',   'billing@sierratrailfoods.example', '775-555-0505', 'Reno',          'NV', 'PREPAID', 'Approved'),
(506, 'Mesa Climb Co',        'invoices@mesaclimbco.example',     '928-555-0506', 'Flagstaff',     'AZ', 'NET30',   'OnHold');

-- ==========================================
-- Table 5: products (merchandise master)
-- SKU format CT-AAA-nnnn (category prefix + number)
-- ==========================================
CREATE TABLE products (
    prod_id INT PRIMARY KEY,
    sku VARCHAR(12) NOT NULL UNIQUE,     -- format CT-AAA-nnnn
    prod_nm VARCHAR(100) NOT NULL,
    category_cd VARCHAR(10),             -- CAMP, HIKE, CLIMB, WATER, APPAREL, FOOTWEAR
    supplier_id INT REFERENCES suppliers(supplier_id),
    unit_cost NUMERIC(10,2),
    list_price NUMERIC(10,2),
    prod_status VARCHAR(20) DEFAULT 'Active' -- Active, Discontinued, Seasonal
);

INSERT INTO products VALUES
(3001, 'CT-CMP-0101', 'Sonoran 2P Backpacking Tent',      'CAMP',     501,  138.00, 279.95, 'Active'),
(3002, 'CT-CMP-0102', 'Mogollon 20F Down Sleeping Bag',   'CAMP',     501,   92.50, 199.95, 'Active'),
(3003, 'CT-CMP-0103', 'Basecamp 2-Burner Stove',          'CAMP',     501,   47.25,  99.95, 'Active'),
(3004, 'CT-HIK-0201', 'Rim-to-Rim 55L Pack',              'HIKE',     501,   96.00, 219.95, 'Active'),
(3005, 'CT-HIK-0202', 'Saguaro Trekking Poles (pair)',    'HIKE',     501,   31.40,  79.95, 'Active'),
(3006, 'CT-HIK-0203', 'Canyon 3L Hydration Reservoir',    'HIKE',     503,   14.80,  39.95, 'Active'),
(3007, 'CT-CLB-0301', 'Mesa Pro Climbing Harness',        'CLIMB',    506,   38.90,  89.95, 'Active'),
(3008, 'CT-CLB-0302', 'Basalt 9.8mm Dynamic Rope 60m',    'CLIMB',    506,  104.00, 229.95, 'Active'),
(3009, 'CT-CLB-0303', 'Chalk Bag - Desert Bloom',         'CLIMB',    506,    6.10,  19.95, 'Active'),
(3010, 'CT-WTR-0401', 'Verde Inflatable Kayak',           'WATER',    503,  248.00, 549.95, 'Seasonal'),
(3011, 'CT-WTR-0402', 'Salt River PFD Vest',              'WATER',    503,   29.70,  69.95, 'Active'),
(3012, 'CT-APP-0501', 'Ocotillo Sun Hoodie',              'APPAREL',  502,   22.40,  59.95, 'Active'),
(3013, 'CT-APP-0502', 'Ironwood Rain Shell',              'APPAREL',  502,   58.00, 149.95, 'Active'),
(3014, 'CT-APP-0503', 'Cholla Hiking Shorts',             'APPAREL',  502,   18.90,  49.95, 'Active'),
(3015, 'CT-APP-0504', 'Juniper Fleece Quarter-Zip',       'APPAREL',  502,   26.50,  69.95, 'Discontinued'),
(3016, 'CT-FTW-0601', 'Bright Angel Hiking Boots',        'FOOTWEAR', 504,   74.00, 169.95, 'Active'),
(3017, 'CT-FTW-0602', 'Havasu Trail Runners',             'FOOTWEAR', 504,   55.60, 129.95, 'Active'),
(3018, 'CT-FTW-0603', 'Slickrock Approach Shoes',         'FOOTWEAR', 504,   61.20, 139.95, 'Active'),
(3019, 'CT-CMP-0104', 'Dutch Oven 6qt Cast Iron',         'CAMP',     505,   28.30,  64.95, 'Active'),
(3020, 'CT-HIK-0204', 'Trail Mix Variety Crate (12)',     'HIKE',     505,   16.20,  42.95, 'Active');

-- ==========================================
-- Table 6: inventory (per-store stock positions)
-- ==========================================
CREATE TABLE inventory (
    inv_id INT PRIMARY KEY,
    prod_id INT NOT NULL REFERENCES products(prod_id),
    st_id INT NOT NULL REFERENCES stores(st_id),
    qty_on_hand INT NOT NULL DEFAULT 0,
    qty_reserved INT NOT NULL DEFAULT 0,
    reorder_pt INT,
    last_count_dt DATE,
    UNIQUE (prod_id, st_id)
);

INSERT INTO inventory VALUES
(9001, 3001, 10, 14, 2, 6,  '2026-06-28'),
(9002, 3001, 30, 9,  1, 6,  '2026-06-27'),
(9003, 3002, 10, 22, 0, 8,  '2026-06-28'),
(9004, 3003, 20, 11, 0, 5,  '2026-06-25'),
(9005, 3004, 10, 17, 3, 8,  '2026-06-28'),
(9006, 3004, 60, 7,  0, 4,  '2026-06-24'),
(9007, 3005, 20, 25, 0, 10, '2026-06-25'),
(9008, 3006, 30, 31, 2, 12, '2026-06-27'),
(9009, 3007, 30, 12, 1, 6,  '2026-06-27'),
(9010, 3008, 30, 6,  0, 3,  '2026-06-27'),
(9011, 3009, 30, 40, 0, 15, '2026-06-27'),
(9012, 3010, 20, 4,  1, 2,  '2026-06-25'),
(9013, 3011, 20, 18, 0, 8,  '2026-06-25'),
(9014, 3012, 10, 36, 4, 15, '2026-06-28'),
(9015, 3012, 40, 21, 0, 10, '2026-06-26'),
(9016, 3013, 10, 13, 1, 6,  '2026-06-28'),
(9017, 3014, 40, 27, 0, 12, '2026-06-26'),
(9018, 3015, 60, 3,  0, 0,  '2026-06-24'),
(9019, 3016, 10, 19, 2, 8,  '2026-06-28'),
(9020, 3016, 50, 8,  0, 4,  '2026-06-23'),
(9021, 3017, 20, 23, 1, 10, '2026-06-25'),
(9022, 3018, 60, 10, 0, 5,  '2026-06-24'),
(9023, 3019, 50, 12, 0, 6,  '2026-06-23'),
(9024, 3020, 50, 30, 0, 12, '2026-06-23');

-- ==========================================
-- Table 7: orders (sales orders, all channels)
-- ==========================================
CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    order_no VARCHAR(14) NOT NULL UNIQUE, -- format SO-nnnnnnnn
    cust_id INT REFERENCES customers(cust_id),
    st_id INT REFERENCES stores(st_id),   -- NULL for web orders
    channel_cd VARCHAR(10) NOT NULL,      -- STORE, WEB, PHONE
    order_dt DATE NOT NULL,
    order_status VARCHAR(20) DEFAULT 'OPEN', -- OPEN, PAID, SHIPPED, RETURNED, CANCELLED
    total_amt NUMERIC(10,2)
);

INSERT INTO orders VALUES
(60001, 'SO-30000001', 7001, 10,   'STORE', '2026-05-04', 'PAID',      479.90),
(60002, 'SO-30000002', 7003, NULL, 'WEB',   '2026-05-09', 'SHIPPED',   279.95),
(60003, 'SO-30000003', 7006, 60,   'STORE', '2026-05-15', 'PAID',      219.95),
(60004, 'SO-30000004', 7009, 30,   'STORE', '2026-05-18', 'RETURNED',  549.95),
(60005, 'SO-30000005', 7002, NULL, 'WEB',   '2026-05-23', 'SHIPPED',   129.88),
(60006, 'SO-30000006', 7011, 10,   'STORE', '2026-05-30', 'PAID',      207.81),
(60007, 'SO-30000007', 7009, 30,   'STORE', '2026-06-02', 'RETURNED',  229.95),
(60008, 'SO-30000008', 7005, 50,   'STORE', '2026-06-06', 'PAID',      107.90),
(60009, 'SO-30000009', 7008, 20,   'STORE', '2026-06-10', 'PAID',      149.95),
(60010, 'SO-30000010', 7009, NULL, 'WEB',   '2026-06-14', 'RETURNED',  169.95),
(60011, 'SO-30000011', 7012, 30,   'STORE', '2026-06-17', 'PAID',       59.95),
(60012, 'SO-30000012', 7007, NULL, 'WEB',   '2026-06-21', 'SHIPPED',   399.85),
(60013, 'SO-30000013', 7010, 60,   'PHONE', '2026-06-24', 'PAID',      139.95),
(60014, 'SO-30000014', 7013, 50,   'STORE', '2026-06-27', 'PAID',       84.90),
(60015, 'SO-30000015', 7004, NULL, 'WEB',   '2026-07-01', 'CANCELLED',  99.95);

-- ==========================================
-- Table 8: order_items (order lines)
-- ==========================================
CREATE TABLE order_items (
    item_id INT PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(order_id),
    prod_id INT NOT NULL REFERENCES products(prod_id),
    qty INT NOT NULL DEFAULT 1,
    unit_price NUMERIC(10,2) NOT NULL,
    discount_pct NUMERIC(5,2) DEFAULT 0   -- policy ceiling 40%
);

INSERT INTO order_items VALUES
(70001, 60001, 3001, 1, 279.95, 0),
(70002, 60001, 3002, 1, 199.95, 0),
(70003, 60002, 3001, 1, 279.95, 0),
(70004, 60003, 3004, 1, 219.95, 0),
(70005, 60004, 3010, 1, 549.95, 0),
(70006, 60005, 3006, 1,  39.95, 0),
(70007, 60005, 3005, 1,  79.95, 0),
(70008, 60005, 3009, 1,  19.95, 50.00),  -- clearance line: exceeds the 40% policy ceiling
(70009, 60006, 3012, 2,  59.95, 0),
(70010, 60006, 3014, 1,  49.95, 10.00),
(70011, 60006, 3020, 1,  42.95, 0),
(70012, 60007, 3008, 1, 229.95, 0),
(70013, 60008, 3019, 1,  64.95, 0),
(70014, 60008, 3020, 1,  42.95, 0),
(70015, 60009, 3013, 1, 149.95, 0),
(70016, 60010, 3016, 1, 169.95, 0),
(70017, 60011, 3012, 1,  59.95, 0),
(70018, 60012, 3016, 1, 169.95, 0),
(70019, 60012, 3013, 1, 149.95, 0),
(70020, 60012, 3005, 1,  79.95, 0),
(70021, 60013, 3018, 1, 139.95, 0),
(70022, 60014, 3019, 1,  64.95, 0),
(70023, 60014, 3009, 1,  19.95, 0),
(70024, 60015, 3003, 1,  99.95, 0),
(70025, 60004, 3011, 0,  69.95, 0);      -- zero-qty line: data-quality curiosity for profiling

-- ==========================================
-- Table 9: payments
-- PLANTED PCI DEFECT: card_no stores the FULL card number
-- (PAN) unmasked. PCI DSS requires truncation or tokenization
-- (first 6 / last 4 at most). The remediation purge is
-- discussed in Workshop 5. Fictional test PANs only.
-- ==========================================
CREATE TABLE payments (
    pay_id INT PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(order_id),
    pay_method_cd VARCHAR(10) NOT NULL,  -- CARD, CASH, GIFT_CARD, PAYPAL
    card_no VARCHAR(19),                 -- DEFECT: full PAN stored; must hold token/last4 only
    auth_cd VARCHAR(10),
    pay_amt NUMERIC(10,2) NOT NULL,
    pay_dt DATE,
    pay_status VARCHAR(20) DEFAULT 'Settled' -- Authorized, Settled, Refunded, Voided
);

INSERT INTO payments VALUES
(80001, 60001, 'CARD',      '4111-1111-1111-2001', 'A83K21', 479.90, '2026-05-04', 'Settled'),
(80002, 60002, 'CARD',      '4111-1111-1111-2002', 'B77Q54', 279.95, '2026-05-09', 'Settled'),
(80003, 60003, 'CASH',      NULL,                  NULL,     219.95, '2026-05-15', 'Settled'),
(80004, 60004, 'CARD',      '4111-1111-1111-2003', 'C19M08', 549.95, '2026-05-18', 'Refunded'),
(80005, 60005, 'PAYPAL',    NULL,                  'PP4471', 129.88, '2026-05-23', 'Settled'),
(80006, 60006, 'CARD',      '4111-1111-1111-2004', 'D62T33', 207.81, '2026-05-30', 'Settled'),
(80007, 60007, 'CARD',      '4111-1111-1111-2005', 'E05R90', 229.95, '2026-06-02', 'Refunded'),
(80008, 60008, 'CASH',      NULL,                  NULL,     107.90, '2026-06-06', 'Settled'),
(80009, 60009, 'GIFT_CARD', NULL,                  'GC8812', 149.95, '2026-06-10', 'Settled'),
(80010, 60010, 'CARD',      '4111-1111-1111-2006', 'F48W17', 169.95, '2026-06-14', 'Refunded'),
(80011, 60012, 'PAYPAL',    NULL,                  'PP9024', 399.85, '2026-06-21', 'Settled'),
(80012, 60013, 'GIFT_CARD', NULL,                  'GC3307', 139.95, '2026-06-24', 'Settled'),
(80013, 60011, 'CASH',      NULL,                  NULL,      59.95, '2026-06-17', 'Settled'),
(80014, 60014, 'CASH',      NULL,                  NULL,      84.90, '2026-06-27', 'Settled');

-- ==========================================
-- Table 10: returns
-- Customer 7009 is the planted refund-abuse pattern:
-- three high-value returns in six weeks -> LP case 95001
-- ==========================================
CREATE TABLE returns (
    ret_id INT PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(order_id),
    prod_id INT NOT NULL REFERENCES products(prod_id),
    ret_reason_cd VARCHAR(20),           -- DEFECT, WRONG_SIZE, CHANGED_MIND, FRAUD_SUSPECTED
    ret_dt DATE,
    refund_amt NUMERIC(10,2),
    ret_status VARCHAR(20) DEFAULT 'Completed' -- Requested, Approved, Completed, Denied
);

INSERT INTO returns VALUES
(91001, 60004, 3010, 'CHANGED_MIND',    '2026-05-26', 549.95, 'Completed'),
(91002, 60007, 3008, 'CHANGED_MIND',    '2026-06-09', 229.95, 'Completed'),
(91003, 60010, 3016, 'FRAUD_SUSPECTED', '2026-06-20', 169.95, 'Denied'),
(91004, 60001, 3002, 'WRONG_SIZE',      '2026-05-12', 199.95, 'Completed'),
(91005, 60006, 3014, 'DEFECT',          '2026-06-05',  44.96, 'Completed'),
(91006, 60009, 3013, 'CHANGED_MIND',    '2026-06-15', 149.95, 'Requested'),
(91007, 60011, 3012, 'DEFECT',          '2026-06-22',  59.95, 'Approved'),
(91008, 60013, 3018, 'WRONG_SIZE',      '2026-06-30', 139.95, 'Requested');

-- ==========================================
-- Table 11: loss_prevention_cases
-- Retail's fraud/compliance record - the SAR parallel.
-- Case notes are sensitive; access is restricted to LP.
-- ==========================================
CREATE TABLE loss_prevention_cases (
    lp_id INT PRIMARY KEY,
    st_id INT REFERENCES stores(st_id),
    cust_id INT REFERENCES customers(cust_id),
    emp_id INT REFERENCES employees(emp_id),
    case_type_cd VARCHAR(20) NOT NULL,   -- REFUND_ABUSE, SHRINK, CARD_FRAUD, TILL_SHORTAGE
    opened_dt DATE,
    opened_by_emp_id INT REFERENCES employees(emp_id),
    case_status VARCHAR(20) DEFAULT 'Open', -- Open, UnderReview, Closed, Referred
    notes_txt TEXT
);

INSERT INTO loss_prevention_cases VALUES
(95001, 30, 7009, NULL, 'REFUND_ABUSE',  '2026-06-21', 803, 'UnderReview',
 'Loyalty CTO-200109: three returns totaling $949.85 in six weeks (SO-30000004, SO-30000007, SO-30000010). Third return denied pending review. Pattern matches serial-return abuse.'),
(95002, 30, NULL, NULL, 'SHRINK',        '2026-06-28', 806, 'Open',
 'Cycle count variance in CLIMB category at Tucson Speedway: 4 units of CT-CLB-0302 unaccounted for since 2026-06-01 count.'),
(95003, NULL, 7009, NULL, 'CARD_FRAUD',  '2026-06-20', 803, 'Referred',
 'Web order SO-30000010 paid with card ending 2006; issuing bank reports card disputed as stolen. Referred to processor and Tucson PD.'),
(95004, 40, NULL, 807, 'TILL_SHORTAGE',  '2026-06-26', 804, 'Closed',
 'Register 2 at Casa Grande Outlet short $40.00 on 2026-06-25 close. Recount resolved: mis-keyed cash drop. No action.');

-- ==========================================
-- Views (reporting layer)
-- ==========================================
CREATE VIEW store_sales_summary AS
SELECT s.st_id, s.st_name, s.st_city,
       COUNT(o.order_id)               AS orders_taken,
       COALESCE(SUM(o.total_amt), 0)   AS gross_sales
FROM stores s
LEFT JOIN orders o ON o.st_id = s.st_id AND o.order_status <> 'CANCELLED'
GROUP BY s.st_id, s.st_name, s.st_city;

CREATE VIEW product_return_rates AS
SELECT p.prod_id, p.sku, p.prod_nm, p.category_cd,
       COUNT(DISTINCT oi.order_id)     AS times_ordered,
       COUNT(DISTINCT r.ret_id)        AS times_returned,
       COALESCE(SUM(r.refund_amt), 0)  AS refunds_paid
FROM products p
LEFT JOIN order_items oi ON oi.prod_id = p.prod_id
LEFT JOIN returns r      ON r.prod_id  = p.prod_id
GROUP BY p.prod_id, p.sku, p.prod_nm, p.category_cd;

CREATE VIEW customer_loyalty_summary AS
SELECT c.cust_id, c.loyalty_no, c.loyalty_tier, c.city,
       c.opted_out_marketing,
       COUNT(o.order_id)               AS orders_placed,
       COALESCE(SUM(o.total_amt), 0)   AS lifetime_spend,
       COUNT(r.ret_id)                 AS returns_made
FROM customers c
LEFT JOIN orders o  ON o.cust_id = c.cust_id
LEFT JOIN returns r ON r.order_id = o.order_id
GROUP BY c.cust_id, c.loyalty_no, c.loyalty_tier, c.city, c.opted_out_marketing;

-- ==========================================
-- PDC catalog comments (harvested by Metadata Ingest)
-- ==========================================
COMMENT ON TABLE customers IS 'Loyalty program customer master: identity, contact details, tier and marketing consent. Contains customer PII - CONFIDENTIAL under CCPA/consumer-privacy policy.';
COMMENT ON COLUMN customers.loyalty_no IS 'Loyalty program number, format CTO-nnnnnn (e.g. CTO-200101). The customer-facing identifier printed on receipts and cards. CRITICAL identifier.';
COMMENT ON COLUMN customers.opted_out_marketing IS 'TRUE when the customer has opted out of marketing contact (CCPA do-not-sell/contact request). Marketing extracts MUST suppress these rows. CRITICAL privacy field.';
COMMENT ON COLUMN customers.loyalty_tier IS 'Loyalty tier. Values: BASE, SILVER, GOLD. Drives discount eligibility and promotion targeting.';

COMMENT ON TABLE products IS 'Merchandise master: SKU, name, category, supplier and pricing. Unit cost is commercially sensitive - internal use only.';
COMMENT ON COLUMN products.sku IS 'Stock-keeping unit, format CT-AAA-nnnn where AAA is the category prefix (CMP, HIK, CLB, WTR, APP, FTW). CRITICAL merchandising identifier.';
COMMENT ON COLUMN products.category_cd IS 'Merchandise category. Values: CAMP, HIKE, CLIMB, WATER, APPAREL, FOOTWEAR. Drives assortment planning and the web taxonomy.';
COMMENT ON COLUMN products.unit_cost IS 'Landed unit cost from the supplier. COMMERCIALLY SENSITIVE - do not expose in customer-facing systems.';

COMMENT ON TABLE suppliers IS 'Approved merchandise vendors with payment terms and status. Supplier contact details are business-contact data.';
COMMENT ON COLUMN suppliers.terms_cd IS 'Payment terms. Values: NET30, NET45, NET60, PREPAID. Drives accounts-payable scheduling.';

COMMENT ON TABLE inventory IS 'Per-store stock positions: on-hand, reserved and reorder point per SKU. Feeds replenishment and the shrink (cycle-count) process.';
COMMENT ON COLUMN inventory.qty_on_hand IS 'Units physically on hand at the store at last count. Negative values indicate a count error and must be investigated.';

COMMENT ON TABLE orders IS 'Sales orders across all channels (store, web, phone). Total is denormalized for reporting; lines are in order_items.';
COMMENT ON COLUMN orders.order_no IS 'Customer-facing order number, format SO-nnnnnnnn. Printed on receipts and used in correspondence. CRITICAL identifier.';
COMMENT ON COLUMN orders.channel_cd IS 'Sales channel. Values: STORE, WEB, PHONE. Web orders carry no store id.';
COMMENT ON COLUMN orders.order_status IS 'Lifecycle status. Values: OPEN, PAID, SHIPPED, RETURNED, CANCELLED.';

COMMENT ON TABLE order_items IS 'Order lines: product, quantity, price and line discount. Discount policy ceiling is 40% - see business rule CTO-Discount-Within-Policy.';
COMMENT ON COLUMN order_items.discount_pct IS 'Line discount percentage. Company policy caps discounts at 40%; values above that require a VP exception and fail the discount business rule.';

COMMENT ON TABLE payments IS 'Order payments across tenders. WARNING: card_no currently stores the FULL card number (PAN) unmasked - a PCI DSS violation planted for the course. Remediation: tokenize and truncate to last 4.';
COMMENT ON COLUMN payments.card_no IS 'Payment card number. DEFECT: full PAN stored in clear text. PCI DSS permits at most first 6 / last 4 after authorization. The identification and quality workshops triangulate this field. Fictional test PANs only.';
COMMENT ON COLUMN payments.pay_method_cd IS 'Tender type. Values: CARD, CASH, GIFT_CARD, PAYPAL. Only CARD rows carry a card number.';

COMMENT ON TABLE returns IS 'Merchandise returns and refunds. Reason codes feed product-quality reporting; repeated returns per customer feed loss prevention.';
COMMENT ON COLUMN returns.ret_reason_cd IS 'Return reason. Values: DEFECT, WRONG_SIZE, CHANGED_MIND, FRAUD_SUSPECTED. FRAUD_SUSPECTED routes to loss prevention.';

COMMENT ON TABLE loss_prevention_cases IS 'Loss prevention case tracking: refund abuse, shrink, card fraud and till shortages. Case notes contain sensitive investigation detail - access restricted to LP staff. HIGHEST confidentiality in the retail estate.';
COMMENT ON COLUMN loss_prevention_cases.case_type_cd IS 'Case classification. Values: REFUND_ABUSE, SHRINK, CARD_FRAUD, TILL_SHORTAGE. CRITICAL for loss reporting.';

COMMENT ON TABLE stores IS 'CTO store network reference data: six Arizona stores with manager and status.';
COMMENT ON TABLE employees IS 'Store staff master: role, store and status. Contains employee PII (names, email).';

-- ==========================================
-- Sample data complete - Canyon Trail Outfitters
-- ==========================================
