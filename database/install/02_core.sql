-- 02_core.sql
-- Schema core: lanes, tenants, the catalog and the pipeline setup.
-- Tables, keys and simple checks only. All logic lives in the core/ Python folder.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.

CREATE SCHEMA core;

-- Access (step 1a) -----------------------------------------------------------------------------

-- A group of tenants.
CREATE TABLE core.lane (
    lane_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    lane_code        VARCHAR(100) NOT NULL,
    lane_name        VARCHAR(200) NOT NULL,
    lane_description TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_time     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_lane PRIMARY KEY (lane_id),
    CONSTRAINT ck_lane_code CHECK (btrim(lane_code) <> ''),
    CONSTRAINT ck_lane_name CHECK (btrim(lane_name) <> '')
);
CREATE UNIQUE INDEX ux_lane_code ON core.lane (lower(btrim(lane_code)));

-- Owns metadata and projects. Access is given per tenant.
CREATE TABLE core.tenant (
    tenant_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    lane_id            BIGINT NOT NULL,
    tenant_code        VARCHAR(100) NOT NULL,
    tenant_name        VARCHAR(200) NOT NULL,
    tenant_description TEXT,
    tenant_catalog     VARCHAR(255) NOT NULL,                -- Databricks catalog for this tenant
    gds_admin_catalog  VARCHAR(255) NOT NULL,                -- Databricks catalog for GDS admin tables
    tenant_visibility  VARCHAR(20) NOT NULL DEFAULT 'private', -- global: every signed-in user can read it
    is_data_lake       BOOLEAN NOT NULL DEFAULT FALSE,       -- this tenant is a data lake; every connection in it is a lake instance (for example GDS US)
    tenant_metadata_version BIGINT NOT NULL DEFAULT 1,       -- goes up on every metadata Apply (CHANGE-SET-007)
    is_metadata_locked BOOLEAN NOT NULL DEFAULT FALSE,       -- catalog lock: the tenant's catalog is read-only (CHANGE-SET-011)
    value              JSONB,                                -- free-form extra settings, as in v2
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_time       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_tenant PRIMARY KEY (tenant_id),
    CONSTRAINT fk_tenant_lane FOREIGN KEY (lane_id)
        REFERENCES core.lane (lane_id),
    CONSTRAINT ck_tenant_code CHECK (btrim(tenant_code) <> ''),
    CONSTRAINT ck_tenant_name CHECK (btrim(tenant_name) <> ''),
    CONSTRAINT ck_tenant_visibility CHECK (tenant_visibility IN ('global', 'private')),
    CONSTRAINT ck_tenant_tenant_catalog CHECK (btrim(tenant_catalog) <> ''),
    CONSTRAINT ck_tenant_gds_admin_catalog CHECK (btrim(gds_admin_catalog) <> ''),
    CONSTRAINT ck_tenant_metadata_version CHECK (tenant_metadata_version > 0)
);
CREATE UNIQUE INDEX ux_tenant_code ON core.tenant (lower(btrim(tenant_code)));
CREATE INDEX ix_tenant_lane_id ON core.tenant (lane_id);

-- Catalog (step 1b) ----------------------------------------------------------------------------

-- Where data comes from, for example SAP or Workday. Shared by all tenants.
CREATE TABLE core.system (
    system_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    system_type_id     BIGINT NOT NULL,
    system_code        VARCHAR(100) NOT NULL,
    system_name        VARCHAR(200) NOT NULL,
    system_description TEXT,
    value              JSONB,                                -- free-form extra settings, as in v2
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_time       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_system PRIMARY KEY (system_id),
    CONSTRAINT fk_system_system_type FOREIGN KEY (system_type_id)
        REFERENCES reference.system_type (system_type_id),
    CONSTRAINT ck_system_code CHECK (btrim(system_code) <> ''),
    CONSTRAINT ck_system_name CHECK (btrim(system_name) <> '')
);
CREATE UNIQUE INDEX ux_system_code ON core.system (lower(btrim(system_code)));

-- A system's own path for each standard notebook.
CREATE TABLE core.system_notebook_path (
    system_notebook_path_id BIGINT GENERATED ALWAYS AS IDENTITY,
    system_id               BIGINT NOT NULL,
    system_notebook_id      BIGINT NOT NULL,
    system_notebook_path    TEXT NOT NULL,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_system_notebook_path PRIMARY KEY (system_notebook_path_id),
    CONSTRAINT fk_system_notebook_path_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT fk_system_notebook_path_system_notebook FOREIGN KEY (system_notebook_id)
        REFERENCES reference.system_notebook (system_notebook_id),
    CONSTRAINT uq_system_notebook_path_system_notebook UNIQUE (system_id, system_notebook_id),
    CONSTRAINT ck_system_notebook_path_path CHECK (btrim(system_notebook_path) <> '')
);

-- How one tenant reaches one system's data.
CREATE TABLE core.connection (
    connection_id              BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                  BIGINT NOT NULL,
    system_id                  BIGINT NOT NULL,
    connection_type_id         BIGINT NOT NULL,
    connection_code            VARCHAR(100) NOT NULL,
    connection_name            VARCHAR(200) NOT NULL,
    connection_description     TEXT,
    has_foreign_catalog        BOOLEAN NOT NULL DEFAULT FALSE,
    foreign_catalog            VARCHAR(255),
    test_initial_batch_id      BIGINT,
    test_incremental_batch_ids BIGINT[],
    value                      JSONB,                        -- free-form extra settings, as in v2
    is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_connection PRIMARY KEY (connection_id),
    CONSTRAINT fk_connection_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_connection_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT fk_connection_connection_type FOREIGN KEY (connection_type_id)
        REFERENCES reference.connection_type (connection_type_id),
    CONSTRAINT ck_connection_code CHECK (btrim(connection_code) <> ''),
    CONSTRAINT ck_connection_name CHECK (btrim(connection_name) <> ''),
    CONSTRAINT ck_connection_foreign_catalog CHECK (NOT has_foreign_catalog OR btrim(foreign_catalog) <> '')
);
CREATE UNIQUE INDEX ux_connection_tenant_system_code ON core.connection (tenant_id, system_id, lower(btrim(connection_code)));
CREATE INDEX ix_connection_system_id ON core.connection (system_id);

-- Which data lake connection this tenant's Bronze, Silver and Gold tables land in. Must be a connection of a data
-- lake tenant (CATALOG-001). Added here because connections are created after tenants.
ALTER TABLE core.tenant ADD COLUMN data_lake_connection_id BIGINT
    CONSTRAINT fk_tenant_data_lake_connection REFERENCES core.connection (connection_id);
CREATE INDEX ix_tenant_data_lake_connection_id ON core.tenant (data_lake_connection_id);

-- Storage location of a connection, per location type and environment.
CREATE TABLE core.connection_location (
    connection_location_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_id                        BIGINT NOT NULL,
    location_type_id                     BIGINT NOT NULL,
    environment_id                       BIGINT NOT NULL,
    connection_location_storage_account  VARCHAR(255) NOT NULL,
    connection_location_secret_reference TEXT NOT NULL,      -- name of the secret, never the secret
    connection_location_container        VARCHAR(255) NOT NULL,
    connection_location_path             TEXT NOT NULL,
    value                                JSONB,              -- free-form extra settings, as in v2
    created_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                           VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_connection_location PRIMARY KEY (connection_location_id),
    CONSTRAINT fk_connection_location_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id),
    CONSTRAINT fk_connection_location_location_type FOREIGN KEY (location_type_id)
        REFERENCES reference.location_type (location_type_id),
    CONSTRAINT fk_connection_location_environment FOREIGN KEY (environment_id)
        REFERENCES reference.environment (environment_id),
    CONSTRAINT uq_connection_location_type_environment UNIQUE (connection_id, location_type_id, environment_id),
    CONSTRAINT ck_connection_location_storage_account CHECK (btrim(connection_location_storage_account) <> ''),
    CONSTRAINT ck_connection_location_secret_reference CHECK (btrim(connection_location_secret_reference) <> ''),
    CONSTRAINT ck_connection_location_container CHECK (btrim(connection_location_container) <> ''),
    CONSTRAINT ck_connection_location_path CHECK (btrim(connection_location_path) <> '')
);

-- One setting of a connection (host, http path, ...) in one environment.
-- For Key Vault parameters the value is the secret's name, never the secret.
CREATE TABLE core.connection_value (
    connection_value_id     BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_id           BIGINT NOT NULL,
    environment_id          BIGINT NOT NULL,
    connection_parameter_id BIGINT NOT NULL,
    connection_value        TEXT,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_connection_value PRIMARY KEY (connection_value_id),
    CONSTRAINT fk_connection_value_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id),
    CONSTRAINT fk_connection_value_environment FOREIGN KEY (environment_id)
        REFERENCES reference.environment (environment_id),
    CONSTRAINT fk_connection_value_connection_parameter FOREIGN KEY (connection_parameter_id)
        REFERENCES reference.connection_parameter (connection_parameter_id),
    CONSTRAINT uq_connection_value_parameter_environment UNIQUE (connection_id, connection_parameter_id, environment_id),
    CONSTRAINT ck_connection_value_value CHECK (btrim(connection_value) <> '')
);

-- A registered physical table, view or file.
CREATE TABLE core.object (
    object_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_id         BIGINT NOT NULL,
    source_tenant_id      BIGINT NOT NULL,
    object_type_id        BIGINT NOT NULL,
    zone_id               BIGINT NOT NULL,
    object_schema         VARCHAR(400) NOT NULL,
    object_name           VARCHAR(400) NOT NULL,
    fc_object_schema      VARCHAR(400),                      -- schema in the foreign catalog
    fc_object_name        VARCHAR(400),                      -- name in the foreign catalog
    object_transformation TEXT,
    object_description    TEXT,
    batch_attribute_name  VARCHAR(400),
    value                 JSONB,                             -- free-form extra settings, as in v2
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_object PRIMARY KEY (object_id),
    CONSTRAINT fk_object_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id),
    CONSTRAINT fk_object_source_tenant FOREIGN KEY (source_tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_object_object_type FOREIGN KEY (object_type_id)
        REFERENCES reference.object_type (object_type_id),
    CONSTRAINT fk_object_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id),
    CONSTRAINT uq_object_id_connection UNIQUE (object_id, connection_id),
    CONSTRAINT ck_object_schema_name CHECK (btrim(object_schema) <> ''),
    CONSTRAINT ck_object_name CHECK (btrim(object_name) <> '')
);
CREATE UNIQUE INDEX ux_object_connection_schema_name ON core.object (connection_id, lower(btrim(object_schema)), lower(btrim(object_name)));
CREATE INDEX ix_object_source_tenant_id ON core.object (source_tenant_id);

-- A column of a registered object.
CREATE TABLE core.attribute (
    attribute_id                 BIGINT GENERATED ALWAYS AS IDENTITY,
    object_id                    BIGINT NOT NULL,
    attribute_name               VARCHAR(400) NOT NULL,
    fc_attribute_name            VARCHAR(400),               -- name in the foreign catalog
    attribute_ordinal_position   INTEGER NOT NULL,
    attribute_description        TEXT,
    attribute_data_type          VARCHAR(100) NOT NULL,
    attribute_inferred_data_type VARCHAR(100),
    attribute_nullability        BOOLEAN NOT NULL DEFAULT TRUE,
    attribute_custom_code        TEXT,
    is_surrogate_key             BOOLEAN NOT NULL DEFAULT FALSE,
    is_natural_key               BOOLEAN NOT NULL DEFAULT FALSE,
    is_meta_data                 BOOLEAN NOT NULL DEFAULT FALSE,
    is_masking_required          BOOLEAN NOT NULL DEFAULT FALSE,
    value                        JSONB,                      -- free-form extra settings, as in v2
    is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_attribute PRIMARY KEY (attribute_id),
    CONSTRAINT fk_attribute_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT uq_attribute_object_ordinal UNIQUE (object_id, attribute_ordinal_position),
    CONSTRAINT uq_attribute_id_object UNIQUE (attribute_id, object_id),
    CONSTRAINT ck_attribute_name CHECK (btrim(attribute_name) <> ''),
    CONSTRAINT ck_attribute_ordinal_position CHECK (attribute_ordinal_position > 0),
    CONSTRAINT ck_attribute_data_type CHECK (btrim(attribute_data_type) <> ''),
    CONSTRAINT ck_attribute_inferred_data_type CHECK (btrim(attribute_inferred_data_type) <> '')
);
CREATE UNIQUE INDEX ux_attribute_object_name ON core.attribute (object_id, lower(btrim(attribute_name)));

-- Ingestion lineage: which object was copied into which.
CREATE TABLE core.ingestion_object_mapping (
    ingestion_object_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY,
    source_object_id            BIGINT NOT NULL,
    target_object_id            BIGINT NOT NULL,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_ingestion_object_mapping PRIMARY KEY (ingestion_object_mapping_id),
    CONSTRAINT fk_ingestion_object_mapping_source_object FOREIGN KEY (source_object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT fk_ingestion_object_mapping_target_object FOREIGN KEY (target_object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT uq_ingestion_object_mapping_source_target UNIQUE (source_object_id, target_object_id),
    CONSTRAINT uq_ingestion_object_mapping_id_source_target UNIQUE (ingestion_object_mapping_id, source_object_id, target_object_id),
    CONSTRAINT ck_ingestion_object_mapping_different CHECK (source_object_id <> target_object_id)
);
CREATE INDEX ix_ingestion_object_mapping_target_object_id ON core.ingestion_object_mapping (target_object_id);

-- Ingestion lineage per attribute. The extra keys make sure each attribute belongs to the
-- source or target object of its object mapping, as in v2.
CREATE TABLE core.ingestion_attribute_mapping (
    ingestion_attribute_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY,
    ingestion_object_mapping_id    BIGINT NOT NULL,
    source_object_id               BIGINT NOT NULL,
    target_object_id               BIGINT NOT NULL,
    source_attribute_id            BIGINT NOT NULL,
    target_attribute_id            BIGINT NOT NULL,
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_ingestion_attribute_mapping PRIMARY KEY (ingestion_attribute_mapping_id),
    CONSTRAINT fk_ingestion_attribute_mapping_ingestion_object_mapping FOREIGN KEY (ingestion_object_mapping_id, source_object_id, target_object_id)
        REFERENCES core.ingestion_object_mapping (ingestion_object_mapping_id, source_object_id, target_object_id),
    CONSTRAINT fk_ingestion_attribute_mapping_source_attribute FOREIGN KEY (source_attribute_id, source_object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT fk_ingestion_attribute_mapping_target_attribute FOREIGN KEY (target_attribute_id, target_object_id)
        REFERENCES core.attribute (attribute_id, object_id),
    CONSTRAINT uq_ingestion_attribute_mapping_source_target UNIQUE (ingestion_object_mapping_id, source_attribute_id, target_attribute_id),
    CONSTRAINT ck_ingestion_attribute_mapping_different CHECK (source_attribute_id <> target_attribute_id)
);
CREATE INDEX ix_ingestion_attribute_mapping_source_attribute_id ON core.ingestion_attribute_mapping (source_attribute_id);
CREATE INDEX ix_ingestion_attribute_mapping_target_attribute_id ON core.ingestion_attribute_mapping (target_attribute_id);

-- Pipelines (step 1c) --------------------------------------------------------------------------
-- Setup only. Run state (v2 copy_group_control: last run time) is not kept here.

-- A set of copies that run together for one tenant and system.
CREATE TABLE core.copy_group (
    copy_group_id            BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                BIGINT NOT NULL,
    system_id                BIGINT NOT NULL,
    copy_group_name          VARCHAR(200) NOT NULL,
    copy_group_description   TEXT,
    is_member_group_required BOOLEAN NOT NULL DEFAULT FALSE,
    value                    JSONB,                          -- free-form extra settings, as in v2
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_copy_group PRIMARY KEY (copy_group_id),
    CONSTRAINT fk_copy_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_copy_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT uq_copy_group_id_tenant_system UNIQUE (copy_group_id, tenant_id, system_id),
    CONSTRAINT ck_copy_group_name CHECK (btrim(copy_group_name) <> '')
);
CREATE UNIQUE INDEX ux_copy_group_tenant_system_name ON core.copy_group (tenant_id, system_id, lower(btrim(copy_group_name)));
CREATE INDEX ix_copy_group_system_id ON core.copy_group (system_id);

-- A named group of members (for example company codes) for one tenant and system.
CREATE TABLE core.member_group (
    member_group_id                BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                      BIGINT NOT NULL,
    system_id                      BIGINT NOT NULL,
    member_group_name              VARCHAR(200) NOT NULL,
    member_group_description       TEXT,
    member_group_initial_load_date DATE,
    value                          JSONB,                    -- free-form extra settings, as in v2
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_member_group PRIMARY KEY (member_group_id),
    CONSTRAINT fk_member_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_member_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT ck_member_group_name CHECK (btrim(member_group_name) <> '')
);
CREATE UNIQUE INDEX ux_member_group_tenant_system_name ON core.member_group (tenant_id, system_id, lower(btrim(member_group_name)));
CREATE INDEX ix_member_group_system_id ON core.member_group (system_id);

-- One member of a member group.
CREATE TABLE core.member (
    member_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    member_group_id       BIGINT NOT NULL,
    member_code           VARCHAR(100) NOT NULL,
    member_name           VARCHAR(200) NOT NULL,
    member_description    TEXT,
    member_attribute_name VARCHAR(400),                      -- the attribute that holds the member's value
    value                 JSONB,                             -- free-form extra settings, as in v2
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_member PRIMARY KEY (member_id),
    CONSTRAINT fk_member_member_group FOREIGN KEY (member_group_id)
        REFERENCES core.member_group (member_group_id),
    CONSTRAINT ck_member_code CHECK (btrim(member_code) <> ''),
    CONSTRAINT ck_member_name CHECK (btrim(member_name) <> '')
);
CREATE UNIQUE INDEX ux_member_group_code ON core.member (member_group_id, lower(btrim(member_code)));

-- One copy of a source object into its target, inside a copy group.
CREATE TABLE core.copy (
    copy_id                            BIGINT GENERATED ALWAYS AS IDENTITY,
    copy_group_id                      BIGINT NOT NULL,
    ingestion_object_mapping_id        BIGINT NOT NULL,
    copy_source_record_limit           BIGINT,
    copy_source_record_limit_attribute VARCHAR(400),
    chunk_type_id                      BIGINT,
    copy_source_initial_sql_script     TEXT,
    copy_source_incremental_sql_script TEXT,
    copy_source_file_name              TEXT,
    copy_source_file_pattern           TEXT,
    copy_source_file_delimiter         VARCHAR(20),
    source_file_type_id                BIGINT,
    copy_source_order                  INTEGER NOT NULL DEFAULT 1,
    source_data_operation_id           BIGINT NOT NULL,
    target_data_operation_id           BIGINT NOT NULL,
    value                              JSONB,                -- free-form extra settings, as in v2
    is_active                          BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                         VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_copy PRIMARY KEY (copy_id),
    CONSTRAINT fk_copy_copy_group FOREIGN KEY (copy_group_id)
        REFERENCES core.copy_group (copy_group_id),
    CONSTRAINT fk_copy_ingestion_object_mapping FOREIGN KEY (ingestion_object_mapping_id)
        REFERENCES core.ingestion_object_mapping (ingestion_object_mapping_id),
    CONSTRAINT fk_copy_chunk_type FOREIGN KEY (chunk_type_id)
        REFERENCES reference.chunk_type (chunk_type_id),
    CONSTRAINT fk_copy_source_file_type FOREIGN KEY (source_file_type_id)
        REFERENCES reference.file_type (file_type_id),
    CONSTRAINT fk_copy_source_data_operation FOREIGN KEY (source_data_operation_id)
        REFERENCES reference.data_operation (data_operation_id),
    CONSTRAINT fk_copy_target_data_operation FOREIGN KEY (target_data_operation_id)
        REFERENCES reference.data_operation (data_operation_id),
    CONSTRAINT uq_copy_group_mapping UNIQUE (copy_group_id, ingestion_object_mapping_id),
    CONSTRAINT ck_copy_source_order CHECK (copy_source_order > 0),
    CONSTRAINT ck_copy_source_record_limit CHECK (copy_source_record_limit > 0)
);
CREATE INDEX ix_copy_ingestion_object_mapping_id ON core.copy (ingestion_object_mapping_id);

-- A set of processing steps for one tenant, system and zone, run after a copy group.
-- The copy group must belong to the same tenant and system.
CREATE TABLE core.process_group (
    process_group_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                      BIGINT NOT NULL,
    system_id                      BIGINT NOT NULL,
    zone_id                        BIGINT NOT NULL,
    copy_group_id                  BIGINT NOT NULL,
    process_group_name             VARCHAR(200) NOT NULL,
    process_group_description      TEXT,
    process_group_dependency_order INTEGER NOT NULL DEFAULT 1,
    value                          JSONB,                    -- free-form extra settings, as in v2
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_process_group PRIMARY KEY (process_group_id),
    CONSTRAINT fk_process_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_process_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT fk_process_group_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id),
    CONSTRAINT fk_process_group_copy_group FOREIGN KEY (copy_group_id, tenant_id, system_id)
        REFERENCES core.copy_group (copy_group_id, tenant_id, system_id),
    CONSTRAINT ck_process_group_name CHECK (btrim(process_group_name) <> ''),
    CONSTRAINT ck_process_group_dependency_order CHECK (process_group_dependency_order > 0)
);
CREATE UNIQUE INDEX ux_process_group_tenant_system_zone_name ON core.process_group (tenant_id, system_id, zone_id, lower(btrim(process_group_name)));
CREATE INDEX ix_process_group_system_id ON core.process_group (system_id);
CREATE INDEX ix_process_group_copy_group_id ON core.process_group (copy_group_id);

-- One processing step (for example a notebook) that builds one object.
-- The object must belong to the process's connection.
CREATE TABLE core.process (
    process_id              BIGINT GENERATED ALWAYS AS IDENTITY,
    process_group_id        BIGINT NOT NULL,
    connection_id           BIGINT NOT NULL,
    object_id               BIGINT NOT NULL,
    process_type_id         BIGINT NOT NULL,
    process_execution_order INTEGER NOT NULL,
    process_location        TEXT NOT NULL,
    process_executable      TEXT NOT NULL,
    value                   JSONB,                           -- free-form extra settings, as in v2
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_process PRIMARY KEY (process_id),
    CONSTRAINT fk_process_process_group FOREIGN KEY (process_group_id)
        REFERENCES core.process_group (process_group_id),
    CONSTRAINT fk_process_object FOREIGN KEY (object_id, connection_id)
        REFERENCES core.object (object_id, connection_id),
    CONSTRAINT fk_process_process_type FOREIGN KEY (process_type_id)
        REFERENCES reference.process_type (process_type_id),
    CONSTRAINT uq_process_group_order_location_executable UNIQUE (process_group_id, process_execution_order, process_location, process_executable),
    CONSTRAINT ck_process_execution_order CHECK (process_execution_order > 0),
    CONSTRAINT ck_process_location CHECK (btrim(process_location) <> ''),
    CONSTRAINT ck_process_executable CHECK (btrim(process_executable) <> '')
);
CREATE INDEX ix_process_connection_id ON core.process (connection_id);
CREATE INDEX ix_process_object_id ON core.process (object_id);
