-- 04_project.sql
-- Schema project: projects and their scope. Notes are in 05_project_context.sql.
-- Tables, keys and simple checks only. All logic lives in the core/ Python folder.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.
--
-- Not carried over from v2: project_lock_event (no lock history), project_event_log (the Run log comes
-- with runs in step 1h), project_revision_transaction (it needed triggers), and the project fields that
-- were dropped (coverage thresholds wait until a check uses them).
-- v2's settings on the project row, including the schema lists, are in project_config.

CREATE SCHEMA project;

-- One modeling effort inside a tenant.
CREATE TABLE project.project (
    project_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id           BIGINT NOT NULL,
    project_name        VARCHAR(255) NOT NULL,
    project_description TEXT,
    project_version     BIGINT NOT NULL DEFAULT 1,      -- goes up on every Apply (v2 project_revision)
    is_locked           BOOLEAN NOT NULL DEFAULT FALSE, -- project lock: the whole project is read-only
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_time        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_project PRIMARY KEY (project_id),
    CONSTRAINT fk_project_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT ck_project_name CHECK (btrim(project_name) <> ''),
    CONSTRAINT ck_project_version CHECK (project_version > 0)
);
CREATE UNIQUE INDEX ux_project_tenant_name ON project.project (tenant_id, lower(btrim(project_name)));

-- Scope: the tables a project works on (v2 name kept).
-- is_active = false takes a table out of scope but keeps its profile and enrichment.
CREATE TABLE project.project_input_scope (
    project_input_scope_id BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id             BIGINT NOT NULL,
    object_id              BIGINT NOT NULL,
    is_locked              BOOLEAN NOT NULL DEFAULT FALSE,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_project_input_scope PRIMARY KEY (project_input_scope_id),
    CONSTRAINT fk_project_input_scope_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_project_input_scope_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT uq_project_input_scope_project_object UNIQUE (project_id, object_id)
);
CREATE INDEX ix_project_input_scope_object_id ON project.project_input_scope (object_id);

-- Settings of one project, one row per project (v2 kept these on the project row).
-- Empty naming instructions or audit columns mean "use the defaults in core/" (the same defaults as v2).
-- Audit columns hold everything Python adds to an entity, so the type 2 history columns (RecordStartTime,
-- RecordEndTime, IsCurrentRecord) are part of them when the SCD type is type_2. Key names come from the
-- naming instructions. v2's separate technical columns template is folded into these two.
CREATE TABLE project.project_config (
    project_config_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                      BIGINT NOT NULL,
    operational_schemas             JSONB NOT NULL DEFAULT '[]',    -- schemas the operational entities live in: [{schema_name, description}]
    dimensional_schemas             JSONB NOT NULL DEFAULT '[]',    -- same, for dimensional entities
    operational_entity_scd_type     VARCHAR(10),                    -- type_1 or type_2; empty: not set
    dimensional_entity_scd_type     VARCHAR(10),                    -- type_1 or type_2, for dimensions
    operational_naming_instructions TEXT,                           -- how operational entities, attributes and keys are named; empty: core/ defaults
    dimensional_naming_instructions TEXT,                           -- same for dimensional, including key names like {Entity}Key
    operational_audit_columns       JSONB,                          -- columns Python adds to every operational entity: [{name, data_type, nullable, definition}]
    dimensional_audit_columns       JSONB,                          -- same for dimensional; with type_2 this includes the history columns
    is_sample_storage_allowed       BOOLEAN NOT NULL DEFAULT FALSE, -- may sample values be stored
    sample_size                     INTEGER NOT NULL DEFAULT 5,     -- values per column; the maximum (10) is in core/
    default_agent_model_id          BIGINT,                         -- default AI settings for a Run; empty: use the app's defaults. The provider comes from the model
    default_reasoning_effort_code   VARCHAR(50),
    default_max_turns               INTEGER,
    default_validation_retry_count  INTEGER,
    created_time                    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                      VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                      VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_project_config PRIMARY KEY (project_config_id),
    CONSTRAINT fk_project_config_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_project_config_default_agent_model FOREIGN KEY (default_agent_model_id)
        REFERENCES reference.agent_model (agent_model_id),
    CONSTRAINT uq_project_config_project UNIQUE (project_id),
    CONSTRAINT ck_project_config_operational_entity_scd_type CHECK (operational_entity_scd_type IN ('type_1', 'type_2')),
    CONSTRAINT ck_project_config_dimensional_entity_scd_type CHECK (dimensional_entity_scd_type IN ('type_1', 'type_2')),
    CONSTRAINT ck_project_config_schemas CHECK (jsonb_typeof(operational_schemas) = 'array' AND jsonb_typeof(dimensional_schemas) = 'array'),
    CONSTRAINT ck_project_config_naming_instructions CHECK (btrim(operational_naming_instructions) <> '' AND btrim(dimensional_naming_instructions) <> ''),
    CONSTRAINT ck_project_config_audit_columns CHECK (jsonb_typeof(operational_audit_columns) = 'array' AND jsonb_typeof(dimensional_audit_columns) = 'array'),
    CONSTRAINT ck_project_config_sample_size CHECK (sample_size > 0),
    CONSTRAINT ck_project_config_default_max_turns CHECK (default_max_turns > 0),
    CONSTRAINT ck_project_config_default_validation_retry_count CHECK (default_validation_retry_count >= 0)
);
CREATE INDEX ix_project_config_default_agent_model_id ON project.project_config (default_agent_model_id);
