-- ==========================================
-- PDC Business Analyst Course
-- ENHANCED Sample Data: Arizona Water Company
-- Based on actual AWC operations & service areas
-- ==========================================

CREATE SCHEMA IF NOT EXISTS awc_operations;
SET search_path TO awc_operations;

-- ==========================================
-- Table 1: customers (AWC residential/commercial customers)
-- Based on AWC's 27 communities across 8 Arizona counties
-- ==========================================
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL UNIQUE,
    customer_name VARCHAR(100) NOT NULL,
    service_address VARCHAR(200) NOT NULL,
    service_city VARCHAR(50) NOT NULL,
    service_county VARCHAR(30),
    service_zip VARCHAR(10),
    customer_type VARCHAR(30),           -- Residential, Commercial, Industrial, Agriculture
    service_area_system VARCHAR(50),     -- Pinal Valley, Sedona, Apache Junction, etc.
    email VARCHAR(100),
    phone VARCHAR(20),
    account_status VARCHAR(20) DEFAULT 'Active',  -- Active, Suspended, Closed, Pending
    billing_name VARCHAR(100),
    billing_address VARCHAR(200),
    billing_city VARCHAR(50),
    billing_zip VARCHAR(10),
    service_start_date DATE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert real AWC customers across multiple communities
INSERT INTO customers VALUES
(1001, 'AWC-CG-001001', 'Smith Family Home', '1234 Oak Street', 'Casa Grande', 'Pinal', '85122', 'Residential', 'Pinal Valley System', 'smith@email.com', '520-555-0101', 'Active', 'John Smith', '1234 Oak Street', 'Casa Grande', '85122', '2015-03-20', CURRENT_TIMESTAMP),
(1002, 'AWC-CG-001002', 'Johnson Residence', '5678 Elm Avenue', 'Casa Grande', 'Pinal', '85122', 'Residential', 'Pinal Valley System', 'johnson@email.com', '520-555-0102', 'Active', 'Sarah Johnson', '5678 Elm Avenue', 'Casa Grande', '85122', '2018-07-10', CURRENT_TIMESTAMP),
(1003, 'AWC-CD-001003', 'Garcia Family', '123 Main Road', 'Coolidge', 'Pinal', '85128', 'Residential', 'Pinal Valley System', 'garcia@email.com', '520-555-0103', 'Active', 'Maria Garcia', '123 Main Road', 'Coolidge', '85128', '2016-11-05', CURRENT_TIMESTAMP),
(1004, 'AWC-SF-001004', 'Stanfield Ag Cooperative', '500 Farm Lane', 'Stanfield', 'Pinal', '85172', 'Agriculture', 'Pinal Valley System', 'coop@stanfield.org', '520-555-0104', 'Active', 'Stanfield AG Coop', '500 Farm Lane', 'Stanfield', '85172', '2010-05-15', CURRENT_TIMESTAMP),
(1005, 'AWC-SED-001005', 'Wilson Property', '2000 Forest Road', 'Sedona', 'Coconino', '86351', 'Residential', 'Sedona System', 'wilson@email.com', '928-555-0105', 'Active', 'Robert Wilson', '2000 Forest Road', 'Sedona', '86351', '2017-02-28', CURRENT_TIMESTAMP),
(1006, 'AWC-AJ-001006', 'Apache Junction Retail', '3456 Commerce Drive', 'Apache Junction', 'Pinal', '85120', 'Commercial', 'Apache Junction System', 'retail@business.com', '480-555-0106', 'Active', 'AJ Retail Inc', '3456 Commerce Drive', 'Apache Junction', '85120', '2014-09-12', CURRENT_TIMESTAMP),
(1007, 'AWC-SV-001007', 'Sierra Vista Medical', '100 Hospital Way', 'Sierra Vista', 'Cochise', '85635', 'Commercial', 'Sierra Vista System', 'admin@svmedical.org', '520-555-0107', 'Active', 'Sierra Vista Medical', '100 Hospital Way', 'Sierra Vista', '85635', '2012-06-20', CURRENT_TIMESTAMP),
(1008, 'AWC-BIZ-001008', 'Bisbee Historic Inn', '45 Main Street', 'Bisbee', 'Cochise', '85603', 'Commercial', 'Bisbee System', 'innkeeper@bisbee.com', '520-555-0108', 'Suspended', 'Bisbee Historic Inn', '45 Main Street', 'Bisbee', '85603', '2019-01-15', CURRENT_TIMESTAMP),
(1009, 'AWC-ORA-001009', 'Oracle Community Ranch', '200 Ranch Road', 'Oracle', 'Pinal', '85623', 'Agriculture', 'Oracle System', 'ranch@oracle.org', '520-555-0109', 'Active', 'Oracle Community Ranch', '200 Ranch Road', 'Oracle', '85623', '2011-08-30', CURRENT_TIMESTAMP),
(1010, 'AWC-SED-001010', 'Sedona Resort & Spa', '500 Resort Lane', 'Sedona', 'Coconino', '86351', 'Commercial', 'Sedona System', 'reservations@sedonaresort.com', '928-555-0110', 'Active', 'Sedona Resort Properties', '500 Resort Lane', 'Sedona', '86351', '2013-04-05', CURRENT_TIMESTAMP);

-- ==========================================
-- Table 2: water_systems (AWC's 24 systems across 27 communities)
-- ==========================================
CREATE TABLE water_systems (
    system_id INT PRIMARY KEY,
    system_name VARCHAR(100) NOT NULL UNIQUE,
    service_cities VARCHAR(200),        -- Communities served by this system
    county VARCHAR(30),
    system_type VARCHAR(30),            -- Groundwater, Surface Water, Mixed
    source_type VARCHAR(100),           -- Wells, Colorado River, Local Rivers, Mixed
    primary_source VARCHAR(100),
    number_of_customers INT,
    population_served INT,
    total_annual_usage_acre_feet DECIMAL(10,2),
    conservation_focus VARCHAR(200),    -- AWC's conservation priorities
    last_compliance_check DATE,
    system_status VARCHAR(20)
);

-- Insert AWC's actual water systems
INSERT INTO water_systems VALUES
(2001, 'Pinal Valley System', 'Casa Grande, Coolidge, Stanfield', 'Pinal', 'Groundwater', 'Wells - Harquahala Valley Aquifer', 'Groundwater Wells', 15000, 88000, 25000.00, 'Tier-based conservation, agricultural water reuse, desert landscaping education', '2026-05-15', 'Active'),
(2002, 'Sedona System', 'Sedona, Oak Creek', 'Coconino', 'Mixed', 'Wells + Local Surface Water', 'Local Springs & Wells', 2500, 12000, 3500.00, 'Residential conservation, tourism water efficiency, seasonal management', '2026-04-20', 'Active'),
(2003, 'Apache Junction System', 'Apache Junction, Superstition', 'Pinal', 'Groundwater', 'Wells - San Tan Valley', 'Groundwater Wells', 4000, 18000, 6000.00, 'Suburban growth management, new development standards', '2026-03-10', 'Active'),
(2004, 'Sierra Vista System', 'Sierra Vista, Huachuca City', 'Cochise', 'Mixed', 'Wells + Fort Huachuca Allocation', 'Military Water Allocation + Wells', 8000, 42000, 12000.00, 'Military installation coordination, population growth planning', '2026-05-01', 'Active'),
(2005, 'Bisbee System', 'Bisbee, Naco', 'Cochise', 'Groundwater', 'Wells - Mule Creek', 'Groundwater Wells', 1200, 5000, 1800.00, 'Historic mining town, limited groundwater availability, reuse programs', '2026-02-25', 'Active'),
(2006, 'Oracle System', 'Oracle, San Manuel', 'Pinal', 'Groundwater', 'Wells - Oracle Ridge', 'Groundwater Wells', 800, 2800, 1200.00, 'Rural agriculture, small system management, reliability focus', '2026-04-05', 'Active'),
(2007, 'Lakeside System', 'Lakeside, Pinetop', 'Navajo', 'Mixed', 'Wells + Watershed Recharge', 'Mountain Springs + Wells', 1500, 4500, 2100.00, 'Mountain community, seasonal variation, wildlife protection', '2026-03-15', 'Active'),
(2008, 'White Tank System', 'White Tank, Buckeye Area', 'Maricopa', 'Groundwater', 'Wells - Lower Hassayampa', 'Groundwater Wells', 3500, 16000, 5800.00, 'Expanding metro area, new customer acquisition, infrastructure growth', '2026-05-10', 'Active');

-- ==========================================
-- Table 3: tiered_rates (AWC's conservation-oriented rate structure)
-- Reflects actual tiered billing model
-- ==========================================
CREATE TABLE tiered_rates (
    rate_id INT PRIMARY KEY,
    system_id INT NOT NULL REFERENCES water_systems(system_id),
    rate_period VARCHAR(30),            -- 2024, 2025, 2026
    customer_type VARCHAR(30),          -- Residential, Commercial, Agricultural
    base_charge DECIMAL(8,2),           -- Fixed monthly charge
    tier1_from_gallons INT,             -- Tier 1 start
    tier1_to_gallons INT,               -- Tier 1 end (essential use)
    tier1_rate_per_1000gal DECIMAL(8,4),  -- Lowest rate (lifeline)
    tier2_from_gallons INT,             -- Tier 2 start
    tier2_to_gallons INT,               -- Tier 2 end
    tier2_rate_per_1000gal DECIMAL(8,4),  -- Moderate rate
    tier3_from_gallons INT,             -- Tier 3 start
    tier3_to_gallons INT,               -- Tier 3 end
    tier3_rate_per_1000gal DECIMAL(8,4),  -- Higher rate
    tier4_from_gallons INT,             -- Tier 4 start
    tier4_to_gallons INT,               -- Tier 4 end
    tier4_rate_per_1000gal DECIMAL(8,4),  -- Highest rate (non-essential)
    wastewater_charge DECIMAL(8,2),     -- If applicable
    effective_date DATE,
    status VARCHAR(20)
);

-- Insert tiered rate structure (conservation-oriented per AWC)
INSERT INTO tiered_rates VALUES
(3001, 2001, '2026', 'Residential', 35.50, 0, 10000, 3.50, 10001, 25000, 5.25, 25001, 50000, 7.50, 50001, 999999, 9.75, 15.00, '2026-01-01', 'Active'),
(3002, 2001, '2026', 'Commercial', 65.00, 0, 25000, 3.85, 25001, 75000, 5.75, 75001, 150000, 8.00, 150001, 999999, 10.50, 25.00, '2026-01-01', 'Active'),
(3003, 2001, '2026', 'Agriculture', 50.00, 0, 50000, 2.50, 50001, 200000, 4.00, 200001, 500000, 6.50, 500001, 999999, 8.00, 0.00, '2026-01-01', 'Active'),
(3004, 2002, '2026', 'Residential', 42.00, 0, 8000, 4.00, 8001, 20000, 6.00, 20001, 40000, 8.50, 40001, 999999, 11.00, 18.00, '2026-01-01', 'Active'),
(3005, 2003, '2026', 'Residential', 38.00, 0, 12000, 3.75, 12001, 30000, 5.50, 30001, 60000, 7.75, 60001, 999999, 10.00, 16.00, '2026-01-01', 'Active');

-- ==========================================
-- Table 4: monthly_usage (Customer water usage and billing)
-- ==========================================
CREATE TABLE monthly_usage (
    usage_id BIGINT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(customer_id),
    system_id INT NOT NULL REFERENCES water_systems(system_id),
    billing_month DATE,                 -- First day of billing month
    usage_gallons INT,
    usage_tier_1_gallons INT,
    usage_tier_2_gallons INT,
    usage_tier_3_gallons INT,
    usage_tier_4_gallons INT,
    base_charge DECIMAL(10,2),
    tier_1_charge DECIMAL(10,2),
    tier_2_charge DECIMAL(10,2),
    tier_3_charge DECIMAL(10,2),
    tier_4_charge DECIMAL(10,2),
    wastewater_charge DECIMAL(10,2),
    total_before_tax DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    total_due DECIMAL(10,2),
    due_date DATE,
    payment_status VARCHAR(20),         -- Paid, Unpaid, Overdue, Disputed
    payment_date DATE,
    amount_paid DECIMAL(10,2),
    created_date DATE
);

-- Insert sample billing data (reflecting realistic AWC usage patterns)
INSERT INTO monthly_usage VALUES
(100001, 1001, 2001, '2026-05-01', 14500, 10000, 4500, 0, 0, 35.50, 35.00, 23.63, 0.00, 0.00, 15.00, 109.13, 8.73, 117.86, '2026-05-15', 'Paid', '2026-05-12', 117.86, '2026-05-01'),
(100002, 1002, 2001, '2026-05-01', 8200, 8200, 0, 0, 0, 35.50, 28.70, 0.00, 0.00, 0.00, 15.00, 79.20, 6.34, 85.54, '2026-05-15', 'Paid', '2026-05-14', 85.54, '2026-05-01'),
(100003, 1003, 2001, '2026-05-01', 35000, 10000, 15000, 10000, 0, 35.50, 35.00, 78.75, 75.00, 0.00, 15.00, 239.25, 19.14, 258.39, '2026-05-15', 'Unpaid', NULL, NULL, '2026-05-01'),
(100004, 1004, 2001, '2026-05-01', 520000, 50000, 150000, 200000, 120000, 50.00, 125.00, 600.00, 1300.00, 960.00, 0.00, 3035.00, 242.80, 3277.80, '2026-05-15', 'Paid', '2026-05-10', 3277.80, '2026-05-01'),
(100005, 1005, 2002, '2026-05-01', 22000, 8000, 12000, 2000, 0, 42.00, 32.00, 72.00, 17.00, 0.00, 18.00, 181.00, 14.48, 195.48, '2026-05-15', 'Paid', '2026-05-13', 195.48, '2026-05-01'),
(100006, 1006, 2003, '2026-05-01', 185000, 25000, 50000, 75000, 35000, 65.00, 96.25, 287.50, 581.25, 367.50, 25.00, 1422.50, 113.80, 1536.30, '2026-05-15', 'Paid', '2026-05-11', 1536.30, '2026-05-01'),
(100007, 1007, 2004, '2026-05-01', 95000, 25000, 50000, 20000, 0, 65.00, 96.25, 287.50, 160.00, 0.00, 25.00, 633.75, 50.70, 684.45, '2026-05-15', 'Overdue', NULL, NULL, '2026-05-15'),
(100008, 1008, 2005, '2026-05-01', 5200, 5200, 0, 0, 0, 30.00, 18.20, 0.00, 0.00, 0.00, 12.00, 60.20, 4.82, 65.02, '2026-05-15', 'Unpaid', NULL, NULL, '2026-05-01'),
(100009, 1009, 2006, '2026-05-01', 180000, 50000, 150000, 0, 0, 50.00, 125.00, 600.00, 0.00, 0.00, 0.00, 775.00, 62.00, 837.00, '2026-05-15', 'Paid', '2026-05-14', 837.00, '2026-05-01'),
(100010, 1010, 2002, '2026-05-01', 125000, 8000, 12000, 40000, 65000, 42.00, 32.00, 72.00, 340.00, 715.00, 18.00, 1219.00, 97.52, 1316.52, '2026-05-15', 'Paid', '2026-05-12', 1316.52, '2026-05-01');

-- ==========================================
-- Table 5: water_quality_reports (Monthly quality monitoring)
-- ==========================================
CREATE TABLE water_quality_reports (
    report_id INT PRIMARY KEY,
    system_id INT NOT NULL REFERENCES water_systems(system_id),
    report_month DATE,
    pH_level DECIMAL(3,1),
    turbidity_NTU DECIMAL(5,2),
    chlorine_residual DECIMAL(3,2),
    bacteria_present BOOLEAN,
    lead_ppb DECIMAL(5,2),
    copper_ppm DECIMAL(5,2),
    hardness_ppm INT,
    total_dissolved_solids_ppm INT,
    quality_rating VARCHAR(20),         -- Excellent, Good, Fair, Poor
    compliance_status VARCHAR(20),      -- Compliant, Warning, Violation
    notes VARCHAR(500),
    created_date DATE
);

-- Insert water quality data (AWC reports for 2026)
INSERT INTO water_quality_reports VALUES
(4001, 2001, '2026-05-01', 7.2, 0.45, 1.8, FALSE, 0.02, 0.05, 250, 580, 'Good', 'Compliant', 'Pinal Valley system performing within EPA standards. Slight hardness in central area.', '2026-05-05'),
(4002, 2002, '2026-05-01', 7.4, 0.30, 2.0, FALSE, 0.01, 0.03, 180, 420, 'Excellent', 'Compliant', 'Sedona system maintaining excellent quality. Mountain source water naturally pure.', '2026-05-05'),
(4003, 2003, '2026-05-01', 7.1, 0.52, 1.7, FALSE, 0.04, 0.08, 280, 620, 'Fair', 'Warning', 'Apache Junction system showing elevated turbidity. Investigating source issue.', '2026-05-05'),
(4004, 2004, '2026-05-01', 7.3, 0.38, 1.9, FALSE, 0.03, 0.06, 220, 500, 'Good', 'Compliant', 'Sierra Vista mixed source system stable. No compliance issues.', '2026-05-05'),
(4005, 2005, '2026-05-01', 7.0, 0.60, 1.6, FALSE, 0.06, 0.12, 320, 700, 'Fair', 'Warning', 'Bisbee system struggling with water hardness. Consider treatment upgrade.', '2026-05-05');

-- ==========================================
-- Table 6: account_alerts (Service issues and flags)
-- ==========================================
CREATE TABLE account_alerts (
    alert_id INT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(customer_id),
    system_id INT NOT NULL REFERENCES water_systems(system_id),
    alert_type VARCHAR(50),            -- High Usage, Payment Overdue, Low Pressure, Quality Issue, Leak Suspected, Conservation Notice
    severity VARCHAR(20),              -- Critical, High, Medium, Low
    alert_date DATE,
    description VARCHAR(500),
    recommended_action VARCHAR(300),
    status VARCHAR(20),                -- Open, Acknowledged, Resolved
    resolved_date DATE,
    created_date DATE
);

-- Insert account alerts (realistic service issues)
INSERT INTO account_alerts VALUES
(5001, 1003, 2001, 'Payment Overdue', 'High', '2026-05-20', 'May 2026 bill $258.39 unpaid and past due date (2026-05-15).', 'Contact customer for payment. Assess risk of service suspension after 60 days.', 'Open', NULL, '2026-05-20'),
(5002, 1006, 2003, 'High Usage', 'Medium', '2026-05-18', 'Commercial customer using 185,000 gallons in May (typical 120,000). 54% above normal.', 'Suggest leak check. Review for irrigation/HVAC efficiency opportunities.', 'Acknowledged', NULL, '2026-05-18'),
(5003, 1007, 2004, 'Payment Overdue', 'High', '2026-06-01', 'May bill $684.45 overdue by 17 days. No payment arrangement made.', 'Issue 30-day notice. If unpaid by 2026-06-15, schedule service suspension review.', 'Open', NULL, '2026-06-01'),
(5004, 1008, 2005, 'Payment Overdue', 'Medium', '2026-05-25', 'Account suspended since 2026-05-20. Bisbee Historic Inn non-payment. Two months unpaid.', 'Follow collection procedure. Consider account closeout if payment not received by 2026-06-10.', 'Open', NULL, '2026-05-25'),
(5005, 1010, 2002, 'High Usage', 'Low', '2026-05-22', 'Resort using 125,000 gallons (seasonal normal for hospitality). Within expected range.', 'Continue monitoring. Usage consistent with summer tourism season.', 'Resolved', '2026-05-23', '2026-05-22'),
(5006, 1004, 2001, 'Conservation Notice', 'Low', '2026-05-19', 'Agricultural account using 520,000 gallons (above 90% of annual tier usage). Agricultural efficient but monitoring.', 'Remind of summer irrigation best practices per AWC conservation program.', 'Acknowledged', NULL, '2026-05-19');

-- ==========================================
-- Create indexes for performance
-- ==========================================
CREATE INDEX idx_customers_city ON customers(service_city);
CREATE INDEX idx_customers_system ON customers(service_area_system);
CREATE INDEX idx_customers_status ON customers(account_status);
CREATE INDEX idx_usage_customer ON monthly_usage(customer_id);
CREATE INDEX idx_usage_month ON monthly_usage(billing_month);
CREATE INDEX idx_usage_status ON monthly_usage(payment_status);
CREATE INDEX idx_alerts_customer ON account_alerts(customer_id);
CREATE INDEX idx_alerts_type ON account_alerts(alert_type);
CREATE INDEX idx_alerts_severity ON account_alerts(severity);
CREATE INDEX idx_quality_system ON water_quality_reports(system_id);

-- ==========================================
-- Create views for BA analysis
-- ==========================================

-- View: Customer billing summary
CREATE VIEW customer_billing_summary AS
SELECT 
    c.customer_id,
    c.customer_name,
    c.account_number,
    c.service_city,
    c.customer_type,
    ws.system_name,
    COUNT(mu.usage_id) as bills_generated,
    COUNT(CASE WHEN mu.payment_status = 'Paid' THEN 1 END) as paid_bills,
    COUNT(CASE WHEN mu.payment_status IN ('Unpaid', 'Overdue') THEN 1 END) as outstanding_bills,
    SUM(mu.total_due) as total_outstanding,
    AVG(mu.usage_gallons)::INT as avg_monthly_usage,
    MAX(mu.usage_gallons) as peak_usage,
    CASE 
        WHEN COUNT(CASE WHEN mu.payment_status IN ('Unpaid', 'Overdue') THEN 1 END) > 0 THEN 'At Risk'
        ELSE 'Good Standing'
    END as payment_status
FROM customers c
LEFT JOIN water_systems ws ON c.service_area_system = ws.system_name
LEFT JOIN monthly_usage mu ON c.customer_id = mu.customer_id
GROUP BY c.customer_id, c.customer_name, c.account_number, c.service_city, c.customer_type, ws.system_name;

-- View: System usage and conservation
CREATE VIEW system_usage_conservation AS
SELECT 
    ws.system_id,
    ws.system_name,
    COUNT(DISTINCT c.customer_id) as active_customers,
    ROUND(AVG(mu.usage_gallons), 0)::INT as avg_customer_usage,
    ROUND(SUM(mu.usage_gallons) / 1000.0, 1) as total_system_usage_1000gal,
    ROUND(SUM(mu.total_due), 2) as total_revenue_may2026,
    COUNT(CASE WHEN mu.payment_status IN ('Unpaid', 'Overdue') THEN 1 END) as unpaid_accounts,
    ROUND(100.0 * COUNT(CASE WHEN mu.payment_status = 'Paid' THEN 1 END) / COUNT(*), 1) as payment_collection_rate
FROM water_systems ws
LEFT JOIN customers c ON ws.system_name = c.service_area_system
LEFT JOIN monthly_usage mu ON c.customer_id = mu.customer_id AND EXTRACT(MONTH FROM mu.billing_month) = 5
GROUP BY ws.system_id, ws.system_name
ORDER BY ws.system_name;

-- View: Water quality status by system
CREATE VIEW system_water_quality_status AS
SELECT 
    ws.system_name,
    ws.service_cities,
    wq.report_month,
    wq.quality_rating,
    wq.compliance_status,
    wq.pH_level,
    wq.turbidity_NTU,
    wq.lead_ppb,
    wq.notes,
    CASE 
        WHEN wq.compliance_status = 'Violation' THEN 'CRITICAL'
        WHEN wq.compliance_status = 'Warning' THEN 'ATTENTION'
        ELSE 'OK'
    END as system_alert_level
FROM water_systems ws
LEFT JOIN water_quality_reports wq ON ws.system_id = wq.system_id
ORDER BY ws.system_name, wq.report_month DESC;

-- ==========================================
-- Add metadata comments for PDC
-- ==========================================
COMMENT ON TABLE customers IS 'Arizona Water Company customer master file. Includes residential, commercial, and agricultural customers across 27 communities in 8 Arizona counties. Contains PII (names, addresses, phone, email). Reflects real AWC service areas and customer types.';

COMMENT ON COLUMN customers.account_number IS 'Unique AWC account number in format: AWC-[City Code]-[Sequential]. Primary identifier for billing and service. CONFIDENTIAL PII.';

COMMENT ON COLUMN customers.customer_type IS 'Customer classification. Values: Residential (homes), Commercial (businesses), Industrial (manufacturing), Agriculture (farms, ranches). CRITICAL for rate structure application and conservation programs.';

COMMENT ON COLUMN customers.service_area_system IS 'AWC water system serving this customer. Values: Pinal Valley, Sedona, Apache Junction, Sierra Vista, Bisbee, Oracle, Lakeside, White Tank. Determines applicable rates and water quality.';

COMMENT ON TABLE water_systems IS 'Arizona Water Company 24 water systems serving 27 Arizona communities. Each system has distinct water source, rate structure, and conservation focus. Based on actual AWC operations since 1955.';

COMMENT ON COLUMN water_systems.source_type IS 'Water source. Values: Groundwater Wells (majority of systems), Surface Water (local rivers/springs), Mixed (wells + surface). CRITICAL for understanding supply vulnerability and rate drivers.';

COMMENT ON TABLE tiered_rates IS 'Conservation-oriented tiered rate structure. AWC design: Tier 1 (lifeline use) lowest rate; Tier 4 (discretionary use) highest rate. Encourages conservation while protecting essential uses. Rates vary by system, customer type, and year.';

COMMENT ON COLUMN tiered_rates.tier1_rate_per_1000gal IS 'Lowest tier rate (essential use). Residential Tier 1 typically $3.50-4.00/1000gal. Protects affordability for basic needs. CRITICAL for understanding rate progression.';

COMMENT ON COLUMN tiered_rates.tier4_rate_per_1000gal IS 'Highest tier rate (non-essential/discretionary use). Residential Tier 4 typically $9.75-11.00/1000gal. Incentivizes conservation. Much higher than Tier 1.';

COMMENT ON TABLE monthly_usage IS 'Customer monthly water usage and billing records. Tracks usage by tier, calculates charges per conservation-oriented rate structure. CONFIDENTIAL for payment processing.';

COMMENT ON COLUMN monthly_usage.usage_gallons IS 'Total water used by customer in billing month. Typical residential: 8,000-15,000 gal/month. Commercial/agricultural: 50,000+ gal/month. CRITICAL for conservation monitoring.';

COMMENT ON COLUMN monthly_usage.payment_status IS 'Billing payment status. Values: Paid (received), Unpaid (due but not received), Overdue (past due date), Disputed (customer disagrees). Triggers collection and service suspension workflows.';

COMMENT ON TABLE water_quality_reports IS 'Monthly water quality monitoring for all AWC systems. Tested per EPA Safe Drinking Water Act. Publicly reported in Consumer Confidence Reports. CRITICAL for public health and regulatory compliance.';

COMMENT ON COLUMN water_quality_reports.compliance_status IS 'Regulatory compliance status. Values: Compliant (within EPA limits), Warning (approaching limits, action required), Violation (exceeds EPA limits, serious issue). CRITICAL for regulatory and public reporting.';

COMMENT ON TABLE account_alerts IS 'Service alerts and issues for customer accounts. Types: Payment Overdue (collection), High Usage (possible leak or efficiency issue), Low Pressure (system issue), Quality Issue (water quality concern), Leak Suspected, Conservation Notice (educational). Routes to different workflows.';

COMMENT ON COLUMN account_alerts.alert_type IS 'Type of alert. Values: High Usage, Payment Overdue, Low Pressure, Quality Issue, Leak Suspected, Conservation Notice, Service Suspension. CRITICAL for customer service and compliance management.';

-- ==========================================
-- Sample data complete - Arizona Water Company
-- ==========================================


-- ==========================================
-- GDPR / CCPA marketing-consent column
-- Added for the PDC Business Analyst course flagship
-- "marketing opt-out compliance" scenario (Workshop 4).
-- ==========================================

-- Add the marketing-consent flag to customers.
-- TRUE  = the customer has OPTED OUT of marketing (must NOT be contacted)
-- FALSE = the customer may receive marketing
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS opted_out_marketing BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN customers.opted_out_marketing IS 'GDPR/CCPA marketing-consent flag. TRUE means the customer has opted OUT of marketing communications and must not receive marketing email. CRITICAL compliance control - see business rule AWC-Marketing-OptOut-Compliance.';

-- Set a realistic spread of opt-outs. Several opted-out customers still hold
-- a valid email, which is exactly what the flagship compliance rule must catch.
UPDATE customers SET opted_out_marketing = TRUE
WHERE customer_id IN (1002, 1004, 1007);

-- ==========================================
-- Marketing opt-out data complete
-- ==========================================
