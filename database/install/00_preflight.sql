-- 00_preflight.sql
-- Run first. Stops the install unless the database is clean (no GDS Workbench schemas left).
--
-- FRESH INSTALL: to wipe an old install, uncomment the drops below and run them by hand first.
-- This deletes every GDS Workbench table and all of its data. Take a backup before you do it.
-- They are in reverse order of the install files. Add a line here whenever a new schema is added.
--
-- DROP SCHEMA IF EXISTS application CASCADE;
-- DROP SCHEMA IF EXISTS workflow CASCADE;
-- DROP SCHEMA IF EXISTS project CASCADE;
-- DROP SCHEMA IF EXISTS security CASCADE;
-- DROP SCHEMA IF EXISTS core CASCADE;
-- DROP SCHEMA IF EXISTS reference CASCADE;
--
-- The app logins (90_roles.sql) are not dropped: they belong to the whole server and may be in use by another
-- database. The install keeps them if they exist. To remove them for good, after the drops above:
-- DROP OWNED BY gds_web_runtime, gds_mcp_runtime; DROP ROLE IF EXISTS gds_web_runtime, gds_mcp_runtime;

DO $preflight$
DECLARE
    leftover text;
BEGIN
    IF current_setting('server_version_num')::int < 160000 THEN
        RAISE EXCEPTION 'PostgreSQL 16 or newer is needed. This server is %.', current_setting('server_version');
    END IF;

    SELECT string_agg(nspname, ', ' ORDER BY nspname)
      INTO leftover
      FROM pg_namespace
     WHERE nspname IN ('reference', 'core', 'security', 'project', 'workflow', 'application');

    IF leftover IS NOT NULL THEN
        RAISE EXCEPTION 'Not a clean database. These schemas still exist: %. Run the drops at the top of this file first.', leftover;
    END IF;
END
$preflight$;

SELECT 'passed' AS preflight_status;
