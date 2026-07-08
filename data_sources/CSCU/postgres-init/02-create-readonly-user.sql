-- ============================================================
--  Create the read-only user that Pentaho Data Catalog uses.
--  Runs automatically on first container init, after the schema
--  and data script (01-...) because init scripts run in order.
--  Credentials here must match PDC_DB_USER / PDC_DB_SECRET in .env.
-- ============================================================

-- Create the login role if it does not already exist.
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'pdc_user') THEN
      CREATE ROLE pdc_user LOGIN PASSWORD 'catalog123!';
   END IF;
END
$$;

-- Grant least-privilege read access to the cscu_core schema.
GRANT CONNECT ON DATABASE cscu_core TO pdc_user;
GRANT USAGE ON SCHEMA cscu_core TO pdc_user;
GRANT SELECT ON ALL TABLES IN SCHEMA cscu_core TO pdc_user;

-- Ensure any tables created later are also readable by pdc_user.
ALTER DEFAULT PRIVILEGES IN SCHEMA cscu_core
   GRANT SELECT ON TABLES TO pdc_user;
