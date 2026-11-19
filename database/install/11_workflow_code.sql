-- 11_workflow_code.sql
-- Schema workflow, part 6: code. A code file belongs to one entity and lists the source systems it
-- covers, so it can be one file for all systems or one file per system (as in v2). operational code and dimensional
-- code are stored apart, like the models and mappings.
-- Patterns: see the top of 06_workflow_analysis.sql.
--
-- Not carried over from v2: the type field (operational or dimensional), artifact type (it is always SQL), git storage
-- fields and digests. Validation checks are in 12_workflow_validation.sql.
-- There is no "how it is loaded" field: the orchestrator decides.

-- operational code ----------------------------------------------------------------------------------

-- A code file for one operational entity: the SQL the AI wrote from the applied mapping.
-- It gives the final data frame only; the orchestrator loads it.
CREATE TABLE workflow.operational_code (
    operational_code_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_entity_id BIGINT NOT NULL,
    operational_file_name VARCHAR(400) NOT NULL, -- for example user_device.sql (v2 artifact_name)
    operational_code_text TEXT NOT NULL,         -- the SQL (v2 generated_code_content)
    is_locked             BOOLEAN NOT NULL DEFAULT FALSE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_code PRIMARY KEY (operational_code_id),
    CONSTRAINT fk_operational_code_operational_entity FOREIGN KEY (operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT ck_operational_code_file_name CHECK (btrim(operational_file_name) <> ''),
    CONSTRAINT ck_operational_code_text CHECK (btrim(operational_code_text) <> '')
);
CREATE UNIQUE INDEX ux_operational_code_entity_file_name ON workflow.operational_code (operational_entity_id, lower(btrim(operational_file_name)));

-- A source system a code file covers (v2 generated_code_source_system).
-- Each system of an entity is in at most one of its code files: core/ checks this (CODE-001).
CREATE TABLE workflow.operational_code_system (
    operational_code_system_id BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_code_id        BIGINT NOT NULL,
    system_id                  BIGINT NOT NULL,
    created_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_code_system PRIMARY KEY (operational_code_system_id),
    CONSTRAINT fk_operational_code_system_operational_code FOREIGN KEY (operational_code_id)
        REFERENCES workflow.operational_code (operational_code_id),
    CONSTRAINT fk_operational_code_system_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT uq_operational_code_system_code_system UNIQUE (operational_code_id, system_id)
);
CREATE INDEX ix_operational_code_system_system_id ON workflow.operational_code_system (system_id);

-- dimensional code ------------------------------------------------------------------------------------

-- A code file for one dimensional entity: the SQL the AI wrote from the applied mapping.
-- It gives the final data frame only; the orchestrator loads it.
CREATE TABLE workflow.dimensional_code (
    dimensional_code_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_file_name VARCHAR(400) NOT NULL, -- for example user_device.sql (v2 artifact_name)
    dimensional_code_text TEXT NOT NULL,         -- the SQL (v2 generated_code_content)
    is_locked             BOOLEAN NOT NULL DEFAULT FALSE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_code PRIMARY KEY (dimensional_code_id),
    CONSTRAINT fk_dimensional_code_dimensional_entity FOREIGN KEY (dimensional_entity_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id),
    CONSTRAINT ck_dimensional_code_file_name CHECK (btrim(dimensional_file_name) <> ''),
    CONSTRAINT ck_dimensional_code_text CHECK (btrim(dimensional_code_text) <> '')
);
CREATE UNIQUE INDEX ux_dimensional_code_entity_file_name ON workflow.dimensional_code (dimensional_entity_id, lower(btrim(dimensional_file_name)));

-- A source system a code file covers (v2 generated_code_source_system).
-- Each system of an entity is in at most one of its code files: core/ checks this (CODE-001).
CREATE TABLE workflow.dimensional_code_system (
    dimensional_code_system_id BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_code_id        BIGINT NOT NULL,
    system_id                  BIGINT NOT NULL,
    created_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_code_system PRIMARY KEY (dimensional_code_system_id),
    CONSTRAINT fk_dimensional_code_system_dimensional_code FOREIGN KEY (dimensional_code_id)
        REFERENCES workflow.dimensional_code (dimensional_code_id),
    CONSTRAINT fk_dimensional_code_system_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT uq_dimensional_code_system_code_system UNIQUE (dimensional_code_id, system_id)
);
CREATE INDEX ix_dimensional_code_system_system_id ON workflow.dimensional_code_system (system_id);

