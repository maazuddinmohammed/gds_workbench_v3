-- 99_verify_install.sql
-- Run last. Checks that the install created exactly what it should.
-- Fails with a list of every problem it finds; prints 'passed' when all is well.
-- Add each new schema and table to the two lists below in the same step that creates it.

DO $verify$
DECLARE
    our_schemas text[] := ARRAY['reference', 'core', 'security', 'project', 'workflow', 'application'];

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
        'reference.context_type',
        'reference.operational_entity_type',
        'reference.agent_provider',
        'reference.agent_model',
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
        'security.tenant_lock',
        -- 04_project.sql
        'project.project',
        'project.project_input_scope',
        'project.project_config',
        -- 05_project_context.sql
        'project.context_group',
        'project.context_record',
        -- 06_workflow_analysis.sql
        'workflow.attribute_profile',
        'workflow.object_enrichment',
        'workflow.attribute_enrichment',
        'workflow.analysis_result',
        -- 07_workflow_subject_area.sql
        'workflow.subject_area',
        'workflow.subject_area_table',
        -- 08_workflow_operational.sql
        'workflow.operational_entity',
        'workflow.operational_attribute',
        'workflow.operational_entity_source',
        'workflow.operational_attribute_source',
        'workflow.operational_link',
        -- 09_workflow_dimensional.sql
        'workflow.dimensional_entity',
        'workflow.dimensional_attribute',
        'workflow.dimensional_entity_source',
        'workflow.dimensional_attribute_source',
        'workflow.dimensional_link',
        -- 10_workflow_mapping.sql
        'workflow.operational_object_mapping',
        'workflow.operational_attribute_mapping',
        'workflow.dimensional_object_mapping',
        'workflow.dimensional_attribute_mapping',
        -- 11_workflow_code.sql
        'workflow.operational_code',
        'workflow.operational_code_system',
        'workflow.dimensional_code',
        'workflow.dimensional_code_system',
        -- 12_workflow_validation.sql
        'workflow.operational_validation_group',
        'workflow.operational_validation_check',
        'workflow.dimensional_validation_group',
        'workflow.dimensional_validation_check',
        -- 13_application_change_sets.sql
        'application.project_change_set',
        'application.project_stage_chunk',
        'application.metadata_change_set',
        'application.metadata_stage_chunk',
        -- 14_application_prompts.sql
        'application.prompt',
        'application.prompt_version',
        -- 15_application_runs.sql
        'application.run',
        'application.run_event',
        'application.run_model_request'
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
