-- 13_application_change_sets.sql
-- Schema application: change sets, as in v2 (metadata change sets and project change sets).
-- Every change (a Run, a Bridge push, a hand edit) first becomes a change set. Each change set has one JSON
-- document per section. A person reviews it and presses Apply or Reject. Apply saves every section in one
-- transaction, in a fixed order (parents first), or nothing at all.
-- Large pushes from VS Code arrive in pieces in the stage chunk tables while the change set is 'receiving';
-- Apply refuses a change set that is still receiving.
-- Tables, keys and simple checks only. All logic (checks, joining pieces, Apply, version check) lives in core/.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.
--
-- Not carried over from v2: digests, draft revision, validation outcome, expiry, correlation ids, the event
-- tables, and the stage batch table (its piece count is on each chunk row). Statuses are receiving, draft,
-- applied and rejected. Ids are numbers instead of UUIDs.
-- Changed from v2: one document per table, so each document matches one table one to one (v2 grouped some
-- tables into one section). Metadata has one object and one attribute document, because v3 keeps all layers
-- in core.object and core.attribute.

CREATE SCHEMA application;

-- A project change set: changes to one project. One document (a list of records) per project or workflow table,
-- plus the project settings as one record.
CREATE TABLE application.project_change_set (
    project_change_set_id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                             BIGINT NOT NULL,
    project_change_set_status              VARCHAR(20) NOT NULL DEFAULT 'receiving', -- receiving, draft, applied or rejected
    project_change_set_title               VARCHAR(500) NOT NULL,                    -- for example "Operational model: Sales"
    project_change_set_source              VARCHAR(20) NOT NULL,                     -- ai_run, vscode_push or web_app_edit
    base_project_version                   BIGINT NOT NULL,                          -- project version the change set was built on; Apply refuses an older one
    project_config_document                JSONB NOT NULL DEFAULT '{}',              -- the project's settings (one record)
    project_input_scope_document           JSONB NOT NULL DEFAULT '[]',
    attribute_profile_document             JSONB NOT NULL DEFAULT '[]',
    object_enrichment_document             JSONB NOT NULL DEFAULT '[]',
    attribute_enrichment_document          JSONB NOT NULL DEFAULT '[]',
    context_group_document                 JSONB NOT NULL DEFAULT '[]',
    context_record_document                JSONB NOT NULL DEFAULT '[]',
    analysis_result_document               JSONB NOT NULL DEFAULT '[]',
    subject_area_document                  JSONB NOT NULL DEFAULT '[]',
    subject_area_table_document            JSONB NOT NULL DEFAULT '[]',
    operational_entity_document            JSONB NOT NULL DEFAULT '[]',
    operational_attribute_document         JSONB NOT NULL DEFAULT '[]',
    operational_entity_source_document     JSONB NOT NULL DEFAULT '[]',
    operational_attribute_source_document  JSONB NOT NULL DEFAULT '[]',
    operational_link_document              JSONB NOT NULL DEFAULT '[]',
    dimensional_entity_document            JSONB NOT NULL DEFAULT '[]',
    dimensional_attribute_document         JSONB NOT NULL DEFAULT '[]',
    dimensional_entity_source_document     JSONB NOT NULL DEFAULT '[]',
    dimensional_attribute_source_document  JSONB NOT NULL DEFAULT '[]',
    dimensional_link_document              JSONB NOT NULL DEFAULT '[]',
    operational_object_mapping_document    JSONB NOT NULL DEFAULT '[]',
    operational_attribute_mapping_document JSONB NOT NULL DEFAULT '[]',
    dimensional_object_mapping_document    JSONB NOT NULL DEFAULT '[]',
    dimensional_attribute_mapping_document JSONB NOT NULL DEFAULT '[]',
    operational_code_document              JSONB NOT NULL DEFAULT '[]',
    operational_code_system_document       JSONB NOT NULL DEFAULT '[]',
    dimensional_code_document              JSONB NOT NULL DEFAULT '[]',
    dimensional_code_system_document       JSONB NOT NULL DEFAULT '[]',
    operational_validation_group_document  JSONB NOT NULL DEFAULT '[]',
    operational_validation_check_document  JSONB NOT NULL DEFAULT '[]',
    dimensional_validation_group_document  JSONB NOT NULL DEFAULT '[]',
    dimensional_validation_check_document  JSONB NOT NULL DEFAULT '[]',
    created_by_principal_id                BIGINT NOT NULL,
    decided_by_principal_id                BIGINT,                                   -- who pressed Apply or Reject
    decided_time                           TIMESTAMPTZ,
    created_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_project_change_set PRIMARY KEY (project_change_set_id),
    CONSTRAINT fk_project_change_set_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_project_change_set_created_by_principal FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT fk_project_change_set_decided_by_principal FOREIGN KEY (decided_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT ck_project_change_set_status CHECK (project_change_set_status IN ('receiving', 'draft', 'applied', 'rejected')),
    CONSTRAINT ck_project_change_set_title CHECK (btrim(project_change_set_title) <> ''),
    CONSTRAINT ck_project_change_set_decided CHECK ((project_change_set_status IN ('applied', 'rejected')) = (decided_by_principal_id IS NOT NULL AND decided_time IS NOT NULL)),
    CONSTRAINT ck_project_change_set_source CHECK (project_change_set_source IN ('ai_run', 'vscode_push', 'web_app_edit')),
    CONSTRAINT ck_project_change_set_base_project_version CHECK (base_project_version > 0),
    CONSTRAINT ck_project_change_set_documents CHECK (
        jsonb_typeof(project_config_document) = 'object'
        AND jsonb_typeof(project_input_scope_document) = 'array'
        AND jsonb_typeof(attribute_profile_document) = 'array'
        AND jsonb_typeof(object_enrichment_document) = 'array'
        AND jsonb_typeof(attribute_enrichment_document) = 'array'
        AND jsonb_typeof(context_group_document) = 'array'
        AND jsonb_typeof(context_record_document) = 'array'
        AND jsonb_typeof(analysis_result_document) = 'array'
        AND jsonb_typeof(subject_area_document) = 'array'
        AND jsonb_typeof(subject_area_table_document) = 'array'
        AND jsonb_typeof(operational_entity_document) = 'array'
        AND jsonb_typeof(operational_attribute_document) = 'array'
        AND jsonb_typeof(operational_entity_source_document) = 'array'
        AND jsonb_typeof(operational_attribute_source_document) = 'array'
        AND jsonb_typeof(operational_link_document) = 'array'
        AND jsonb_typeof(dimensional_entity_document) = 'array'
        AND jsonb_typeof(dimensional_attribute_document) = 'array'
        AND jsonb_typeof(dimensional_entity_source_document) = 'array'
        AND jsonb_typeof(dimensional_attribute_source_document) = 'array'
        AND jsonb_typeof(dimensional_link_document) = 'array'
        AND jsonb_typeof(operational_object_mapping_document) = 'array'
        AND jsonb_typeof(operational_attribute_mapping_document) = 'array'
        AND jsonb_typeof(dimensional_object_mapping_document) = 'array'
        AND jsonb_typeof(dimensional_attribute_mapping_document) = 'array'
        AND jsonb_typeof(operational_code_document) = 'array'
        AND jsonb_typeof(operational_code_system_document) = 'array'
        AND jsonb_typeof(dimensional_code_document) = 'array'
        AND jsonb_typeof(dimensional_code_system_document) = 'array'
        AND jsonb_typeof(operational_validation_group_document) = 'array'
        AND jsonb_typeof(operational_validation_check_document) = 'array'
        AND jsonb_typeof(dimensional_validation_group_document) = 'array'
        AND jsonb_typeof(dimensional_validation_check_document) = 'array')
);
CREATE INDEX ix_project_change_set_project_id ON application.project_change_set (project_id);
CREATE INDEX ix_project_change_set_created_by_principal_id ON application.project_change_set (created_by_principal_id);
CREATE INDEX ix_project_change_set_decided_by_principal_id ON application.project_change_set (decided_by_principal_id);

-- One piece of a large push for one section of a project change set (v2 stage batch and chunk, as one table).
-- While the change set is 'receiving', the Bridge sends each section in numbered pieces. When every piece of a
-- section is in, core/ joins them into the section document and deletes the pieces. Then the status becomes 'draft'.
CREATE TABLE application.project_stage_chunk (
    project_stage_chunk_id BIGINT GENERATED ALWAYS AS IDENTITY,
    project_change_set_id  BIGINT NOT NULL,
    section_name           VARCHAR(50) NOT NULL, -- which document this piece belongs to
    chunk_index            INTEGER NOT NULL,     -- 1, 2, 3, ...
    chunk_count            INTEGER NOT NULL,     -- how many pieces the section has in total
    records_document       JSONB NOT NULL,       -- the records in this piece
    created_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_project_stage_chunk PRIMARY KEY (project_stage_chunk_id),
    CONSTRAINT fk_project_stage_chunk_project_change_set FOREIGN KEY (project_change_set_id)
        REFERENCES application.project_change_set (project_change_set_id),
    CONSTRAINT uq_project_stage_chunk_section_index UNIQUE (project_change_set_id, section_name, chunk_index),
    CONSTRAINT ck_project_stage_chunk_section_name CHECK (section_name IN (
        'project_config', 'project_input_scope', 'attribute_profile',
        'object_enrichment', 'attribute_enrichment', 'context_group', 'context_record', 'analysis_result',
        'subject_area', 'subject_area_table', 'operational_entity', 'operational_attribute',
        'operational_entity_source', 'operational_attribute_source', 'operational_link',
        'dimensional_entity', 'dimensional_attribute', 'dimensional_entity_source',
        'dimensional_attribute_source', 'dimensional_link', 'operational_object_mapping',
        'operational_attribute_mapping', 'dimensional_object_mapping', 'dimensional_attribute_mapping',
        'operational_code', 'operational_code_system', 'dimensional_code', 'dimensional_code_system',
        'operational_validation_group', 'operational_validation_check', 'dimensional_validation_group',
        'dimensional_validation_check')),
    CONSTRAINT ck_project_stage_chunk_index CHECK (chunk_index BETWEEN 1 AND chunk_count),
    CONSTRAINT ck_project_stage_chunk_records CHECK (jsonb_typeof(records_document) = 'array')
);

-- A metadata change set: changes to one tenant's catalog and pipelines, one document (a list of records) per table.
CREATE TABLE application.metadata_change_set (
    metadata_change_set_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                            BIGINT NOT NULL,
    metadata_change_set_status           VARCHAR(20) NOT NULL DEFAULT 'receiving', -- receiving, draft, applied or rejected
    metadata_change_set_title            VARCHAR(500) NOT NULL,                    -- for example "Operational model: Sales"
    metadata_change_set_source           VARCHAR(20) NOT NULL,                     -- ai_run, vscode_push or web_app_edit
    object_document                      JSONB NOT NULL DEFAULT '[]',
    attribute_document                   JSONB NOT NULL DEFAULT '[]',
    ingestion_object_mapping_document    JSONB NOT NULL DEFAULT '[]',
    ingestion_attribute_mapping_document JSONB NOT NULL DEFAULT '[]',
    copy_group_document                  JSONB NOT NULL DEFAULT '[]',
    copy_document                        JSONB NOT NULL DEFAULT '[]',
    member_group_document                JSONB NOT NULL DEFAULT '[]',
    member_document                      JSONB NOT NULL DEFAULT '[]',
    process_group_document               JSONB NOT NULL DEFAULT '[]',
    process_document                     JSONB NOT NULL DEFAULT '[]',
    created_by_principal_id              BIGINT NOT NULL,
    decided_by_principal_id              BIGINT,                                   -- who pressed Apply or Reject
    decided_time                         TIMESTAMPTZ,
    created_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_metadata_change_set PRIMARY KEY (metadata_change_set_id),
    CONSTRAINT fk_metadata_change_set_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_metadata_change_set_created_by_principal FOREIGN KEY (created_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT fk_metadata_change_set_decided_by_principal FOREIGN KEY (decided_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT ck_metadata_change_set_status CHECK (metadata_change_set_status IN ('receiving', 'draft', 'applied', 'rejected')),
    CONSTRAINT ck_metadata_change_set_title CHECK (btrim(metadata_change_set_title) <> ''),
    CONSTRAINT ck_metadata_change_set_decided CHECK ((metadata_change_set_status IN ('applied', 'rejected')) = (decided_by_principal_id IS NOT NULL AND decided_time IS NOT NULL)),
    CONSTRAINT ck_metadata_change_set_source CHECK (metadata_change_set_source IN ('ai_run', 'vscode_push', 'web_app_edit')),
    CONSTRAINT ck_metadata_change_set_documents CHECK (
        jsonb_typeof(object_document) = 'array'
        AND jsonb_typeof(attribute_document) = 'array'
        AND jsonb_typeof(ingestion_object_mapping_document) = 'array'
        AND jsonb_typeof(ingestion_attribute_mapping_document) = 'array'
        AND jsonb_typeof(copy_group_document) = 'array'
        AND jsonb_typeof(copy_document) = 'array'
        AND jsonb_typeof(member_group_document) = 'array'
        AND jsonb_typeof(member_document) = 'array'
        AND jsonb_typeof(process_group_document) = 'array'
        AND jsonb_typeof(process_document) = 'array')
);
CREATE INDEX ix_metadata_change_set_tenant_id ON application.metadata_change_set (tenant_id);
CREATE INDEX ix_metadata_change_set_created_by_principal_id ON application.metadata_change_set (created_by_principal_id);
CREATE INDEX ix_metadata_change_set_decided_by_principal_id ON application.metadata_change_set (decided_by_principal_id);

-- One piece of a large push for one section of a metadata change set (v2 stage batch and chunk, as one table).
-- While the change set is 'receiving', the Bridge sends each section in numbered pieces. When every piece of a
-- section is in, core/ joins them into the section document and deletes the pieces. Then the status becomes 'draft'.
CREATE TABLE application.metadata_stage_chunk (
    metadata_stage_chunk_id BIGINT GENERATED ALWAYS AS IDENTITY,
    metadata_change_set_id  BIGINT NOT NULL,
    section_name            VARCHAR(50) NOT NULL, -- which document this piece belongs to
    chunk_index             INTEGER NOT NULL,     -- 1, 2, 3, ...
    chunk_count             INTEGER NOT NULL,     -- how many pieces the section has in total
    records_document        JSONB NOT NULL,       -- the records in this piece
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_metadata_stage_chunk PRIMARY KEY (metadata_stage_chunk_id),
    CONSTRAINT fk_metadata_stage_chunk_metadata_change_set FOREIGN KEY (metadata_change_set_id)
        REFERENCES application.metadata_change_set (metadata_change_set_id),
    CONSTRAINT uq_metadata_stage_chunk_section_index UNIQUE (metadata_change_set_id, section_name, chunk_index),
    CONSTRAINT ck_metadata_stage_chunk_section_name CHECK (section_name IN (
        'object', 'attribute', 'ingestion_object_mapping', 'ingestion_attribute_mapping', 'copy_group',
        'copy', 'member_group', 'member', 'process_group', 'process')),
    CONSTRAINT ck_metadata_stage_chunk_index CHECK (chunk_index BETWEEN 1 AND chunk_count),
    CONSTRAINT ck_metadata_stage_chunk_records CHECK (jsonb_typeof(records_document) = 'array')
);
