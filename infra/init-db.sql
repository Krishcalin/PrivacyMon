-- Provisions the non-superuser application role for row-level security (SRS 8.5).
--
-- A PostgreSQL SUPERUSER (the `privacymon` owner the container creates) BYPASSES RLS
-- even with FORCE, so the API must query as THIS restricted role for the
-- application-isolation policies to take effect. The worker stays the owner — it is
-- the trusted writer and is deliberately not subject to RLS. Runs once, on a fresh
-- data volume, before the Alembic migration creates the tables; the DEFAULT PRIVILEGES
-- grants below then apply automatically to those owner-created tables and sequences.
--
-- The dev password here is non-secret; production provisions the role and its secret
-- out of band.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'privacymon_app') THEN
        CREATE ROLE privacymon_app LOGIN PASSWORD 'privacymon_app' NOSUPERUSER;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO privacymon_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO privacymon_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO privacymon_app;

ALTER DEFAULT PRIVILEGES FOR ROLE privacymon IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO privacymon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE privacymon IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO privacymon_app;
