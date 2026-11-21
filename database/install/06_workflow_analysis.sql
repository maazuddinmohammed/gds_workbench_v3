-- 06_workflow_analysis.sql
-- Schema workflow, part 1: profiling (with sample values), enrichment and relationships.
-- Tables, keys and simple checks only. All logic lives in the core/ Python folder.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.
--
-- Patterns for every workflow table (this file and 07 to 11):
--   Only top rows have project_id (an entity, a subject area, a validation group, and the rows in this file,
--   which are about a scope table, so project_id is part of what they mean). They point at their scope row
--   (project_id, object_id), so they can only be about a table in the project's scope.
--   A child row points at its parent by the parent's id alone; its project follows from the parent (Nov 18,
--   Maaz). Cross checks this gives up (same project, in scope, belongs to the right entity) are rules in core/,
--   listed in docs/rules.md.
--   is_locked: a Run never changes or removes a locked row. Only a person can.
--   is_active on every workflow table (Nov 21, Maaz): a push, a Run or a hand edit never deletes a row, it
--   switches it off. A switched-off row keeps its row key, so switching it on again brings the same row back
--   (no v2 "unique only while active" indexes). Deleting for good is a separate job on the management screen.
--   No workflow_run_id or digests yet: runs come in step 1h and change sets record which Run made them.

CREATE SCHEMA workflow;

-- Measurements of one column (profiling, no AI). Counts and percentages, as in v2, plus sample values.
-- Profiling also fetches the samples. They are stored only when the project allows it
-- (project_config.is_sample_storage_allowed); core/ checks that and cuts long values.
CREATE TABLE workflow.attribute_profile (
    attribute_profile_id BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id           BIGINT NOT NULL,
    object_id            BIGINT NOT NULL,
    attribute_id         BIGINT NOT NULL,
    row_count            BIGINT NOT NULL,
    non_null_count       BIGINT NOT NULL,
    null_count           BIGINT NOT NULL,
    blank_count          BIGINT,
    distinct_count       BIGINT,
    min_data_length      INTEGER,
    max_data_length      INTEGER,
    avg_data_length      NUMERIC(20, 6),
    percent_populated    NUMERIC(7, 4),
    percent_duplicates   NUMERIC(7, 4),
    percent_null         NUMERIC(7, 4),
    percent_blank        NUMERIC(7, 4),
    percent_distinct     NUMERIC(7, 4),
    sample_values        JSONB,          -- JSON list of text, most common first; NULL when samples may not be stored
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_time         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_attribute_profile PRIMARY KEY (attribute_profile_id),
    CONSTRAINT fk_attribute_profile_scope FOREIGN KEY (project_id, object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    CONSTRAINT fk_attribute_profile_attribute FOREIGN KEY (attribute_id, object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT uq_attribute_profile_project_attribute UNIQUE (project_id, attribute_id),
    CONSTRAINT ck_attribute_profile_counts CHECK (
        row_count >= 0 AND non_null_count >= 0 AND null_count >= 0
        AND non_null_count + null_count = row_count
        AND (blank_count IS NULL OR blank_count BETWEEN 0 AND non_null_count)
        AND (distinct_count IS NULL OR distinct_count BETWEEN 0 AND non_null_count)),
    CONSTRAINT ck_attribute_profile_lengths CHECK (
        (min_data_length IS NULL OR min_data_length >= 0)
        AND (max_data_length IS NULL OR max_data_length >= 0)
        AND (min_data_length IS NULL OR max_data_length IS NULL OR min_data_length <= max_data_length)
        AND (avg_data_length IS NULL OR avg_data_length >= 0)),
    CONSTRAINT ck_attribute_profile_percentages CHECK (
        percent_populated BETWEEN 0 AND 100 AND percent_duplicates BETWEEN 0 AND 100 AND percent_null BETWEEN 0 AND 100
        AND percent_blank BETWEEN 0 AND 100 AND percent_distinct BETWEEN 0 AND 100),
    CONSTRAINT ck_attribute_profile_sample_values CHECK (jsonb_typeof(sample_values) = 'array')
);
CREATE INDEX ix_attribute_profile_object ON workflow.attribute_profile (project_id, object_id);
CREATE INDEX ix_attribute_profile_attribute_id ON workflow.attribute_profile (attribute_id);

-- Enrichment of one source table, owned by the project. Definition and Grain are two fields.
CREATE TABLE workflow.object_enrichment (
    object_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id           BIGINT NOT NULL,
    object_id            BIGINT NOT NULL,
    object_definition    TEXT, -- data dictionary definition (v2 object_description)
    object_grain         TEXT, -- what one row means
    is_locked            BOOLEAN NOT NULL DEFAULT FALSE,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_time         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_object_enrichment PRIMARY KEY (object_enrichment_id),
    CONSTRAINT fk_object_enrichment_scope FOREIGN KEY (project_id, object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    CONSTRAINT uq_object_enrichment_project_object UNIQUE (project_id, object_id),
    CONSTRAINT ck_object_enrichment_definition CHECK (btrim(object_definition) <> ''),
    CONSTRAINT ck_object_enrichment_grain CHECK (btrim(object_grain) <> '')
);

-- Enrichment of one source column, owned by the project.
-- The key and PII marks may be empty: empty means unknown, false means "checked, it is not".
CREATE TABLE workflow.attribute_enrichment (
    attribute_enrichment_id      BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                   BIGINT NOT NULL,
    object_id                    BIGINT NOT NULL,
    attribute_id                 BIGINT NOT NULL,
    attribute_definition         TEXT, -- v2 attribute_description
    attribute_inferred_data_type VARCHAR(100),
    is_natural_key               BOOLEAN,
    is_primary_key               BOOLEAN,
    is_nullable                  BOOLEAN,
    is_pii                       BOOLEAN,
    is_locked                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_attribute_enrichment PRIMARY KEY (attribute_enrichment_id),
    CONSTRAINT fk_attribute_enrichment_scope FOREIGN KEY (project_id, object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    CONSTRAINT fk_attribute_enrichment_attribute FOREIGN KEY (attribute_id, object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT uq_attribute_enrichment_project_attribute UNIQUE (project_id, attribute_id),
    CONSTRAINT ck_attribute_enrichment_definition CHECK (btrim(attribute_definition) <> ''),
    CONSTRAINT ck_attribute_enrichment_inferred_data_type CHECK (btrim(attribute_inferred_data_type) <> '')
);
CREATE INDEX ix_attribute_enrichment_object ON workflow.attribute_enrichment (project_id, object_id);
CREATE INDEX ix_attribute_enrichment_attribute_id ON workflow.attribute_enrichment (attribute_id);

-- Relationship: a link between two source columns, found by the relationships step (v2 name kept).
-- Both tables must be in the project's scope. The validation fields hold the counts from the check query.
CREATE TABLE workflow.analysis_result (
    analysis_result_id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                             BIGINT NOT NULL,
    from_object_id                         BIGINT NOT NULL,
    from_attribute_id                      BIGINT NOT NULL,
    to_object_id                           BIGINT NOT NULL,
    to_attribute_id                        BIGINT NOT NULL,
    relationship_kind                      VARCHAR(100) NOT NULL, -- for example foreign_key or same_business_key
    inferred_cardinality                   VARCHAR(20) NOT NULL DEFAULT 'unknown',
    validation_result                      VARCHAR(30),           -- empty until the check query has run
    validation_source_non_null_count       BIGINT,
    validation_source_distinct_count       BIGINT,
    validation_target_non_null_count       BIGINT,
    validation_target_distinct_count       BIGINT,
    validation_source_missing_target_count BIGINT,
    validation_unused_target_count         BIGINT,
    validation_duplicate_target_key_count  BIGINT,
    is_locked                              BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_analysis_result PRIMARY KEY (analysis_result_id),
    CONSTRAINT fk_analysis_result_from_scope FOREIGN KEY (project_id, from_object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    CONSTRAINT fk_analysis_result_to_scope FOREIGN KEY (project_id, to_object_id)
        REFERENCES project.project_input_scope (project_id, object_id),
    CONSTRAINT fk_analysis_result_from_attribute FOREIGN KEY (from_attribute_id, from_object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT fk_analysis_result_to_attribute FOREIGN KEY (to_attribute_id, to_object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT uq_analysis_result_project_from_to UNIQUE (project_id, from_attribute_id, to_attribute_id),
    CONSTRAINT ck_analysis_result_different CHECK (from_attribute_id <> to_attribute_id),
    CONSTRAINT ck_analysis_result_relationship_kind CHECK (btrim(relationship_kind) <> ''),
    CONSTRAINT ck_analysis_result_inferred_cardinality CHECK (
        inferred_cardinality IN ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many', 'unknown')),
    CONSTRAINT ck_analysis_result_validation_result CHECK (
        validation_result IN ('supported', 'inconclusive', 'unsupported'))
);
CREATE INDEX ix_analysis_result_from_object ON workflow.analysis_result (project_id, from_object_id);
CREATE INDEX ix_analysis_result_to_object ON workflow.analysis_result (project_id, to_object_id);
CREATE INDEX ix_analysis_result_from_attribute_id ON workflow.analysis_result (from_attribute_id);
CREATE INDEX ix_analysis_result_to_attribute_id ON workflow.analysis_result (to_attribute_id);
