-- 14_application_prompts.sql
-- Schema application: prompts and prompt versions (v2 prompt_template and prompt_template_version).
-- A prompt is the instructions for one step, for example "Operational model - standard". Every save makes a new
-- prompt version; versions never change. A Run uses the latest version unless the person picks another.
-- A prompt is global (tenant_id empty) or belongs to one tenant. A Run uses the tenant's default prompt for the
-- step if there is one, otherwise the global default. That choice is made in core/, not here.
-- Prompts are app settings, not project data: saving one writes a new version directly, without a change set.
-- Tables, keys and simple checks only. Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.
--
-- Not carried over from v2: prompt_template_code (the name is enough), workflow_stage_id and the workflow stage
-- tables (the step is a value), the ownership scope column (empty tenant_id means global), publish and retire
-- status and who did them (the latest version is used), the digest, agent_tool_names (the tools come from the
-- code for each step), tool_instruction_prompt_template (a tool_assisted prompt explains its tools in its system
-- prompt; prompts are already split by kind of Run), and prompt_assignment (one default per step instead).
-- Renamed: "template" is dropped from the names (prompt, prompt_version, system_prompt, ...).

-- A prompt for one step and one kind of Run.
CREATE TABLE application.prompt (
    prompt_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id               BIGINT,                         -- empty: a global prompt, for every tenant
    project_workflow        VARCHAR(50) NOT NULL,           -- the step this prompt is for
    workflow_execution_mode VARCHAR(20) NOT NULL,           -- one_shot or tool_assisted; the two kinds of Run have different prompts
    prompt_name             VARCHAR(200) NOT NULL,
    prompt_description      TEXT,
    is_default              BOOLEAN NOT NULL DEFAULT FALSE, -- the prompt a Run uses unless the person picks another
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_prompt PRIMARY KEY (prompt_id),
    CONSTRAINT fk_prompt_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT ck_prompt_project_workflow CHECK (project_workflow IN (
        'object_enrichment', 'attribute_enrichment', 'analysis', 'subject_area',
        'operational', 'dimensional', 'operational_mapping', 'dimensional_mapping',
        'operational_code', 'dimensional_code', 'operational_validation', 'dimensional_validation')),
    CONSTRAINT ck_prompt_workflow_execution_mode CHECK (workflow_execution_mode IN ('one_shot', 'tool_assisted')),
    CONSTRAINT ck_prompt_name CHECK (btrim(prompt_name) <> ''),
    CONSTRAINT ck_prompt_default_active CHECK (is_active OR NOT is_default) -- a default prompt is active
);
CREATE INDEX ix_prompt_tenant_id ON application.prompt (tenant_id);
-- Names are unique among the global prompts, and within each tenant.
CREATE UNIQUE INDEX ux_prompt_global_name ON application.prompt (lower(btrim(prompt_name)))
    WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX ux_prompt_tenant_name ON application.prompt (tenant_id, lower(btrim(prompt_name)))
    WHERE tenant_id IS NOT NULL;
-- At most one global default per step and kind of Run, and at most one per tenant, step and kind of Run.
CREATE UNIQUE INDEX ux_prompt_global_default ON application.prompt (project_workflow, workflow_execution_mode)
    WHERE is_default AND tenant_id IS NULL;
CREATE UNIQUE INDEX ux_prompt_tenant_default ON application.prompt (tenant_id, project_workflow, workflow_execution_mode)
    WHERE is_default AND tenant_id IS NOT NULL;

-- One saved text of a prompt. Every save adds a row with the next number; rows are never changed.
CREATE TABLE application.prompt_version (
    prompt_version_id       BIGINT GENERATED ALWAYS AS IDENTITY,
    prompt_id               BIGINT NOT NULL,
    prompt_version_number   INTEGER NOT NULL, -- 1, 2, 3, ... per prompt
    system_prompt           TEXT NOT NULL,    -- v2 system_prompt_template; a tool_assisted prompt explains its tools here
    instruction_prompt      TEXT NOT NULL,    -- v2 instruction_prompt_template
    created_by_principal_id BIGINT NOT NULL,  -- who saved this version
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_prompt_version PRIMARY KEY (prompt_version_id),
    CONSTRAINT fk_prompt_version_prompt FOREIGN KEY (prompt_id)
        REFERENCES application.prompt (prompt_id),
    CONSTRAINT fk_prompt_version_created_by_principal FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT uq_prompt_version_number UNIQUE (prompt_id, prompt_version_number),
    CONSTRAINT ck_prompt_version_number CHECK (prompt_version_number > 0),
    CONSTRAINT ck_prompt_version_system_prompt CHECK (btrim(system_prompt) <> ''),
    CONSTRAINT ck_prompt_version_instruction_prompt CHECK (btrim(instruction_prompt) <> '')
);
CREATE INDEX ix_prompt_version_created_by_principal_id ON application.prompt_version (created_by_principal_id);
