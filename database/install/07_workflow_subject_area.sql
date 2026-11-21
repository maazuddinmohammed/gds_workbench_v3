-- 07_workflow_subject_area.sql
-- Schema workflow, part 2: subject areas.
-- A subject area is a business group of scope tables, like Sales. It decides which tables an operational or
-- dimensional Run works on. A table can be in several areas. A scope table in no area is unassigned: that is
-- worked out, not stored.
-- Patterns: see the top of 06_workflow_analysis.sql.

CREATE TABLE workflow.subject_area (
    subject_area_id         BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id              BIGINT NOT NULL,
    subject_area_name       VARCHAR(255) NOT NULL,
    subject_area_definition TEXT NOT NULL,
    is_locked               BOOLEAN NOT NULL DEFAULT FALSE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_subject_area PRIMARY KEY (subject_area_id),
    CONSTRAINT fk_subject_area_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT ck_subject_area_name CHECK (btrim(subject_area_name) <> ''),
    CONSTRAINT ck_subject_area_definition CHECK (btrim(subject_area_definition) <> '')
);
CREATE UNIQUE INDEX ux_subject_area_project_name ON workflow.subject_area (project_id, lower(btrim(subject_area_name)));

-- One scope table in one area. The project comes from the area; core/ checks the table is in that
-- project's scope (SUBJECT-AREA-001).
CREATE TABLE workflow.subject_area_table (
    subject_area_table_id BIGINT GENERATED ALWAYS AS IDENTITY,
    subject_area_id       BIGINT NOT NULL,
    object_id             BIGINT NOT NULL,
    is_locked             BOOLEAN NOT NULL DEFAULT FALSE,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_subject_area_table PRIMARY KEY (subject_area_table_id),
    CONSTRAINT fk_subject_area_table_subject_area FOREIGN KEY (subject_area_id)
        REFERENCES workflow.subject_area (subject_area_id),
    CONSTRAINT fk_subject_area_table_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT uq_subject_area_table_area_object UNIQUE (subject_area_id, object_id)
);
CREATE INDEX ix_subject_area_table_object_id ON workflow.subject_area_table (object_id);
