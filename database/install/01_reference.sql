-- 01_reference.sql
-- Schema reference: short fixed lists that other tables point at (system types, zones, ...).
-- Every list has the same shape: <list>_id, <list>_code, <list>_name, <list>_description, is_active, and the
-- audit columns (for example zone_id, zone_code, zone_name, zone_description). As in v2, the pipeline lists
-- and location type have no code: their name is unique instead.
-- The rows themselves are seed data (database/seed/), not here.
-- Tables, keys and simple checks only. All logic lives in the core/ Python folder.
--
-- Patterns used in every install file (they are the source of truth for the database):
--   Table names are singular (core.tenant, not core.tenants), as in v2.
--   Column names are the v2 names: every table has <table>_id (BIGINT identity) as its primary key,
--   and its own fields carry the table name: core.lane has lane_id, lane_code, lane_name, lane_description.
--   A foreign key column has the same name as the key it points at, for example tenant.lane_id or object.zone_id.
--   Audit columns on every table, as in v2: created_time, created_by, updated_time, updated_by.
--   *_by defaults to the database login; core/ sets updated_time and updated_by on every update (no triggers).
--   Constraint names: pk_<table>, fk_<table>_<column>, uq_<table>_<columns>, ck_<table>_<rule>.
--   ux_<table>_<columns>: unique index that ignores upper/lower case and outer spaces (codes and names).
--   ix_<table>_<column>: index on a foreign key to another core or security table.

CREATE SCHEMA reference;

-- Catalog lists (step 1b) ---------------------------------------------------------------------

-- Kind of source system, for example erp or hr.
CREATE TABLE reference.system_type (
    system_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    system_type_code        VARCHAR(100) NOT NULL,
    system_type_name        VARCHAR(200) NOT NULL,
    system_type_description TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_system_type PRIMARY KEY (system_type_id),
    CONSTRAINT ck_system_type_code CHECK (btrim(system_type_code) <> ''),
    CONSTRAINT ck_system_type_name CHECK (btrim(system_type_name) <> '')
);
CREATE UNIQUE INDEX ux_system_type_code ON reference.system_type (lower(btrim(system_type_code)));

-- How a connection reaches its data, for example databricks or sql_server.
CREATE TABLE reference.connection_type (
    connection_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_type_code        VARCHAR(100) NOT NULL,
    connection_type_name        VARCHAR(200) NOT NULL,
    connection_type_description TEXT,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_connection_type PRIMARY KEY (connection_type_id),
    CONSTRAINT ck_connection_type_code CHECK (btrim(connection_type_code) <> ''),
    CONSTRAINT ck_connection_type_name CHECK (btrim(connection_type_name) <> '')
);
CREATE UNIQUE INDEX ux_connection_type_code ON reference.connection_type (lower(btrim(connection_type_code)));

-- Kind of registered object, for example table, view or file.
CREATE TABLE reference.object_type (
    object_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    object_type_code        VARCHAR(100) NOT NULL,
    object_type_name        VARCHAR(200) NOT NULL,
    object_type_description TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_object_type PRIMARY KEY (object_type_id),
    CONSTRAINT ck_object_type_code CHECK (btrim(object_type_code) <> ''),
    CONSTRAINT ck_object_type_name CHECK (btrim(object_type_name) <> '')
);
CREATE UNIQUE INDEX ux_object_type_code ON reference.object_type (lower(btrim(object_type_code)));

-- Where an object sits: source, bronze, silver or gold.
CREATE TABLE reference.zone (
    zone_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    zone_code        VARCHAR(100) NOT NULL,
    zone_name        VARCHAR(200) NOT NULL,
    zone_description TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_time     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_zone PRIMARY KEY (zone_id),
    CONSTRAINT ck_zone_code CHECK (btrim(zone_code) <> ''),
    CONSTRAINT ck_zone_name CHECK (btrim(zone_name) <> '')
);
CREATE UNIQUE INDEX ux_zone_code ON reference.zone (lower(btrim(zone_code)));

-- dev, test, prod. Connection values and locations are kept per environment.
CREATE TABLE reference.environment (
    environment_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    environment_code        VARCHAR(100) NOT NULL,
    environment_name        VARCHAR(200) NOT NULL,
    environment_description TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_environment PRIMARY KEY (environment_id),
    CONSTRAINT ck_environment_code CHECK (btrim(environment_code) <> ''),
    CONSTRAINT ck_environment_name CHECK (btrim(environment_name) <> '')
);
CREATE UNIQUE INDEX ux_environment_code ON reference.environment (lower(btrim(environment_code)));

-- Kind of storage location for a connection, for example landing or archive.
CREATE TABLE reference.location_type (
    location_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    location_type_name        VARCHAR(200) NOT NULL,
    location_type_description TEXT,
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_location_type PRIMARY KEY (location_type_id),
    CONSTRAINT ck_location_type_name CHECK (btrim(location_type_name) <> '')
);
CREATE UNIQUE INDEX ux_location_type_name ON reference.location_type (lower(btrim(location_type_name)));

-- One setting a connection can have, for example databricks_host_name.
-- is_key_vault: the stored value is the name of a Key Vault secret, never the secret itself.
CREATE TABLE reference.connection_parameter (
    connection_parameter_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    connection_parameter_code        VARCHAR(100) NOT NULL,
    connection_parameter_name        VARCHAR(200) NOT NULL,
    connection_parameter_description TEXT,
    is_key_vault                     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                        BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                       VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_connection_parameter PRIMARY KEY (connection_parameter_id),
    CONSTRAINT ck_connection_parameter_code CHECK (btrim(connection_parameter_code) <> ''),
    CONSTRAINT ck_connection_parameter_name CHECK (btrim(connection_parameter_name) <> '')
);
CREATE UNIQUE INDEX ux_connection_parameter_code ON reference.connection_parameter (lower(btrim(connection_parameter_code)));

-- Pipeline lists (step 1c) --------------------------------------------------------------------

-- A standard notebook each system can point at with its own path.
CREATE TABLE reference.system_notebook (
    system_notebook_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    system_notebook_name        VARCHAR(200) NOT NULL,
    system_notebook_description TEXT,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                  VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_system_notebook PRIMARY KEY (system_notebook_id),
    CONSTRAINT ck_system_notebook_name CHECK (btrim(system_notebook_name) <> '')
);
CREATE UNIQUE INDEX ux_system_notebook_name ON reference.system_notebook (lower(btrim(system_notebook_name)));

-- How a big copy is split into pieces, for example by date or by row count.
CREATE TABLE reference.chunk_type (
    chunk_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    chunk_type_name        VARCHAR(200) NOT NULL,
    chunk_type_description TEXT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_chunk_type PRIMARY KEY (chunk_type_id),
    CONSTRAINT ck_chunk_type_name CHECK (btrim(chunk_type_name) <> '')
);
CREATE UNIQUE INDEX ux_chunk_type_name ON reference.chunk_type (lower(btrim(chunk_type_name)));

-- File format for file sources, for example csv or parquet.
CREATE TABLE reference.file_type (
    file_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    file_type_name        VARCHAR(200) NOT NULL,
    file_type_description TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by            VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_file_type PRIMARY KEY (file_type_id),
    CONSTRAINT ck_file_type_name CHECK (btrim(file_type_name) <> '')
);
CREATE UNIQUE INDEX ux_file_type_name ON reference.file_type (lower(btrim(file_type_name)));

-- How a copy reads or writes data, for example full, incremental or merge.
CREATE TABLE reference.data_operation (
    data_operation_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    data_operation_name        VARCHAR(200) NOT NULL,
    data_operation_description TEXT,
    is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_data_operation PRIMARY KEY (data_operation_id),
    CONSTRAINT ck_data_operation_name CHECK (btrim(data_operation_name) <> '')
);
CREATE UNIQUE INDEX ux_data_operation_name ON reference.data_operation (lower(btrim(data_operation_name)));

-- Kind of processing step, for example notebook or sql.
CREATE TABLE reference.process_type (
    process_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    process_type_name        VARCHAR(200) NOT NULL,
    process_type_description TEXT,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_process_type PRIMARY KEY (process_type_id),
    CONSTRAINT ck_process_type_name CHECK (btrim(process_type_name) <> '')
);
CREATE UNIQUE INDEX ux_process_type_name ON reference.process_type (lower(btrim(process_type_name)));

-- Project lists (step 1d) ---------------------------------------------------------------------

-- What a Note is for, for example operational_model_requirement or agent. The prompt builder in core/
-- decides which steps read which type. The rows come from the seed (database/seed/).
CREATE TABLE reference.context_type (
    context_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    context_type_code        VARCHAR(100) NOT NULL,
    context_type_name        VARCHAR(200) NOT NULL,
    context_type_description TEXT,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_context_type PRIMARY KEY (context_type_id),
    CONSTRAINT ck_context_type_code CHECK (btrim(context_type_code) <> ''),
    CONSTRAINT ck_context_type_name CHECK (btrim(context_type_name) <> '')
);
CREATE UNIQUE INDEX ux_context_type_code ON reference.context_type (lower(btrim(context_type_code)));

-- Model lists (step 1e) -----------------------------------------------------------------------

-- Kind of operational entity, for example core, reference or association (same as v2).
CREATE TABLE reference.operational_entity_type (
    operational_entity_type_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_entity_type_code        VARCHAR(100) NOT NULL,
    operational_entity_type_name        VARCHAR(200) NOT NULL,
    operational_entity_type_description TEXT,
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_entity_type PRIMARY KEY (operational_entity_type_id),
    CONSTRAINT ck_operational_entity_type_code CHECK (btrim(operational_entity_type_code) <> ''),
    CONSTRAINT ck_operational_entity_type_name CHECK (btrim(operational_entity_type_name) <> '')
);
CREATE UNIQUE INDEX ux_operational_entity_type_code ON reference.operational_entity_type (lower(btrim(operational_entity_type_code)));
