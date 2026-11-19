-- 05_project_context.sql
-- Schema project, part 2: Notes (v2 context groups and context records).
-- Tables, keys and simple checks only. All logic (which Notes go into which prompt) lives in the core/ Python folder.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.

-- Note group: a named set of Notes with one type, for one system or (system_id empty) the whole project.
CREATE TABLE project.context_group (
    context_group_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                BIGINT NOT NULL,
    context_type_id           BIGINT NOT NULL,
    system_id                 BIGINT, -- empty: for the whole project (v2 source_system_id)
    context_group_name        VARCHAR(255) NOT NULL,
    context_group_description TEXT,
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_context_group PRIMARY KEY (context_group_id),
    CONSTRAINT fk_context_group_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_context_group_context_type FOREIGN KEY (context_type_id)
        REFERENCES reference.context_type (context_type_id),
    CONSTRAINT fk_context_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT ck_context_group_name CHECK (btrim(context_group_name) <> '')
);
CREATE UNIQUE INDEX ux_context_group_project_name ON project.context_group (project_id, lower(btrim(context_group_name)));
CREATE INDEX ix_context_group_system_id ON project.context_group (system_id);

-- Note: one requirement, rule or decision, in a group. The project comes from the group.
-- is_active = false switches a Note off without deleting it (v2 status inactive or deprecated).
CREATE TABLE project.context_record (
    context_record_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    context_group_id                BIGINT NOT NULL,
    context_record_text             TEXT NOT NULL,
    context_record_source_reference TEXT, -- where it came from, for example a document
    is_locked                       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                       BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                      VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                      VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_context_record PRIMARY KEY (context_record_id),
    CONSTRAINT fk_context_record_context_group FOREIGN KEY (context_group_id)
        REFERENCES project.context_group (context_group_id),
    CONSTRAINT ck_context_record_text CHECK (btrim(context_record_text) <> '')
);
CREATE INDEX ix_context_record_context_group_id ON project.context_record (context_group_id);
