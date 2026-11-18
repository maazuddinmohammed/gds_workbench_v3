-- 99_verify_install.sql
-- Run last. Checks that the install created exactly what it should.
-- Fails with a list of every problem it finds; prints 'passed' when all is well.
-- Add each new schema and table to the two lists below in the same step that creates it.

DO $verify$
DECLARE
    our_schemas text[] := ARRAY['reference', 'core', 'security'];

    expected_tables text[] := ARRAY[
        -- 01_reference.sql
        'reference.system_type',
        'reference.connection_type',
        'reference.object_type',
        'reference.zone',
        'reference.environment',
        'reference.location_type',
        'reference.connection_parameter',
        'reference.system_notebook',
        'reference.chunk_type',
        'reference.file_type',
        'reference.data_operation',
        'reference.process_type',
        -- 02_core.sql
        'core.lane',
        'core.tenant',
        'core.system',
        'core.system_notebook_path',
        'core.connection',
        'core.connection_location',
        'core.connection_value',
        'core.object',
        'core.attribute',
        'core.ingestion_object_mapping',
        'core.ingestion_attribute_mapping',
        'core.copy_group',
        'core.member_group',
        'core.member',
        'core.copy',
        'core.process_group',
        'core.process',
        -- 03_security.sql
        'security.principal',
        'security.tenant_principal_access',
        'security.tenant_lock'
    ];

    problems text[] := '{}';
    t text;
BEGIN
    -- 1. Every expected table exists.
    FOREACH t IN ARRAY expected_tables LOOP
        IF to_regclass(t) IS NULL THEN
            problems := problems || ('missing table: ' || t);
        END IF;
    END LOOP;

    -- 2. No tables that nobody planned.
    problems := problems || ARRAY(
        SELECT 'unexpected table: ' || schemaname || '.' || tablename
          FROM pg_tables
         WHERE schemaname = ANY (our_schemas)
           AND schemaname || '.' || tablename <> ALL (expected_tables)
         ORDER BY 1
    );

    -- 3. Every table has a primary key.
    problems := problems || ARRAY(
        SELECT 'no primary key: ' || c.oid::regclass::text
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = ANY (our_schemas)
           AND c.relkind = 'r'
           AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p')
         ORDER BY 1
    );

    -- 4. No functions, procedures or triggers. Logic lives in the core/ Python folder.
    problems := problems || ARRAY(
        SELECT 'function not allowed: ' || p.oid::regprocedure::text
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = ANY (our_schemas)
         ORDER BY 1
    );
    problems := problems || ARRAY(
        SELECT 'trigger not allowed: ' || tg.tgname || ' on ' || tg.tgrelid::regclass::text
          FROM pg_trigger tg
          JOIN pg_class c ON c.oid = tg.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = ANY (our_schemas)
           AND NOT tg.tgisinternal
         ORDER BY 1
    );

    -- 5. Every table has the four audit columns.
    problems := problems || ARRAY(
        SELECT 'missing audit column: ' || c.oid::regclass::text || '.' || a.col
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         CROSS JOIN unnest(ARRAY['created_time', 'created_by', 'updated_time', 'updated_by']) AS a (col)
         WHERE n.nspname = ANY (our_schemas)
           AND c.relkind = 'r'
           AND NOT EXISTS (SELECT 1 FROM pg_attribute x
                            WHERE x.attrelid = c.oid AND x.attname = a.col AND NOT x.attisdropped)
         ORDER BY 1
    );

    IF cardinality(problems) > 0 THEN
        RAISE EXCEPTION 'Install check failed (% problems):%', cardinality(problems),
            E'\n  ' || array_to_string(problems, E'\n  ');
    END IF;
END
$verify$;

SELECT 'passed' AS verify_status;
