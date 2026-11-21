-- 90_roles.sql
-- The database logins the apps use: gds_web_runtime (web app) and gds_mcp_runtime (MCP server), v2's names.
-- Each may read and write the rows of every GDS Workbench table, and nothing else: no new tables, no other databases.
--
-- Logins belong to the whole Postgres server, not to one database. If they already exist (for example from v2),
-- they are kept as they are, password included, so an app's connection setting only needs the new database name.
-- A new login has no password: set one by hand afterwards, never in a file:
--     ALTER ROLE gds_web_runtime PASSWORD '...';
--     ALTER ROLE gds_mcp_runtime PASSWORD '...';

DO $roles$
DECLARE
    login text;
BEGIN
    FOREACH login IN ARRAY ARRAY['gds_web_runtime', 'gds_mcp_runtime'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = login) THEN
            EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', login);
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), login);
    END LOOP;
END
$roles$;

GRANT USAGE ON SCHEMA reference, core, security, project, workflow, application TO gds_web_runtime, gds_mcp_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
   ON ALL TABLES IN SCHEMA reference, core, security, project, workflow, application
   TO gds_web_runtime, gds_mcp_runtime;
