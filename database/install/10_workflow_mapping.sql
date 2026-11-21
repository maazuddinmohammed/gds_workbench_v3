-- 10_workflow_mapping.sql
-- Schema workflow, part 5: operational mapping (reads Bronze) and dimensional mapping (reads the operational model), stored apart
-- with the same two parts. One mapping per target entity and source system.
-- Patterns: see the top of 06_workflow_analysis.sql.
--
-- The entity part has four text fields: tables, row filter, sample query and transformation (Nov 18,
-- Maaz). Tables is text, not ids: the ids are already in the entity sources and links, and the text can
-- name lookups and other entities in one place.
--
-- Not carried over from v2: the one shared pair of tables with a type field, the JSON transformation
-- document, output templates, dependency order, and the rule that a parent needs its own saved mapping
-- (a lookup's facts about the parent come from the model).

-- Operational mapping -------------------------------------------------------------------------------

-- Mapping for one operational entity and one source system: the entity part.
-- Text fields, each plain words, SQL, or both. The mapping document is printed from these rows.
CREATE TABLE workflow.operational_object_mapping (
    operational_object_mapping_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_entity_id                     BIGINT NOT NULL,
    system_id                                 BIGINT NOT NULL, -- the source system this mapping reads
    operational_object_mapping_tables         TEXT,            -- which tables and entities it reads, including lookups
    operational_object_mapping_row_filter     TEXT,            -- which rows to keep
    operational_object_mapping_sample_query   TEXT,            -- an example query for the entity part (shows the joins)
    operational_object_mapping_transformation TEXT,            -- entity level transformation logic
    is_locked                                 BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_object_mapping PRIMARY KEY (operational_object_mapping_id),
    CONSTRAINT fk_operational_object_mapping_operational_entity FOREIGN KEY (operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT fk_operational_object_mapping_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT uq_operational_object_mapping_entity_system UNIQUE (operational_entity_id, system_id),
    CONSTRAINT ck_operational_object_mapping_tables CHECK (btrim(operational_object_mapping_tables) <> ''),
    CONSTRAINT ck_operational_object_mapping_row_filter CHECK (btrim(operational_object_mapping_row_filter) <> ''),
    CONSTRAINT ck_operational_object_mapping_sample_query CHECK (btrim(operational_object_mapping_sample_query) <> ''),
    CONSTRAINT ck_operational_object_mapping_transformation CHECK (btrim(operational_object_mapping_transformation) <> '')
);
CREATE INDEX ix_operational_object_mapping_system_id ON workflow.operational_object_mapping (system_id);

-- Mapping, the attribute part: one line per attribute of the mapping's own entity, with one free field.
-- Only the mapping and the attribute are stored; core/ checks the attribute is the mapping entity's (MAPPING-001).
CREATE TABLE workflow.operational_attribute_mapping (
    operational_attribute_mapping_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_object_mapping_id                BIGINT NOT NULL,
    operational_attribute_id                     BIGINT NOT NULL,
    operational_attribute_mapping_transformation TEXT, -- plain words, SQL, or both
    is_locked                                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_attribute_mapping PRIMARY KEY (operational_attribute_mapping_id),
    CONSTRAINT fk_operational_attribute_mapping_operational_object_mapping FOREIGN KEY (operational_object_mapping_id)
        REFERENCES workflow.operational_object_mapping (operational_object_mapping_id),
    CONSTRAINT fk_operational_attribute_mapping_operational_attribute FOREIGN KEY (operational_attribute_id)
        REFERENCES workflow.operational_attribute (operational_attribute_id),
    CONSTRAINT uq_operational_attribute_mapping_mapping_attribute UNIQUE (operational_object_mapping_id, operational_attribute_id),
    CONSTRAINT ck_operational_attribute_mapping_transformation CHECK (btrim(operational_attribute_mapping_transformation) <> '')
);
CREATE INDEX ix_operational_attribute_mapping_operational_attribute_id ON workflow.operational_attribute_mapping (operational_attribute_id);

-- Dimensional mapping ---------------------------------------------------------------------------------

-- Mapping for one dimensional entity and one source system: the entity part.
-- Text fields, each plain words, SQL, or both. The mapping document is printed from these rows.
CREATE TABLE workflow.dimensional_object_mapping (
    dimensional_object_mapping_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_entity_id                     BIGINT NOT NULL,
    system_id                                 BIGINT NOT NULL, -- the source system this mapping reads
    dimensional_object_mapping_tables         TEXT,            -- which tables and entities it reads, including lookups
    dimensional_object_mapping_row_filter     TEXT,            -- which rows to keep
    dimensional_object_mapping_sample_query   TEXT,            -- an example query for the entity part (shows the joins)
    dimensional_object_mapping_transformation TEXT,            -- entity level transformation logic
    is_locked                                 BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_object_mapping PRIMARY KEY (dimensional_object_mapping_id),
    CONSTRAINT fk_dimensional_object_mapping_dimensional_entity FOREIGN KEY (dimensional_entity_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id),
    CONSTRAINT fk_dimensional_object_mapping_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT uq_dimensional_object_mapping_entity_system UNIQUE (dimensional_entity_id, system_id),
    CONSTRAINT ck_dimensional_object_mapping_tables CHECK (btrim(dimensional_object_mapping_tables) <> ''),
    CONSTRAINT ck_dimensional_object_mapping_row_filter CHECK (btrim(dimensional_object_mapping_row_filter) <> ''),
    CONSTRAINT ck_dimensional_object_mapping_sample_query CHECK (btrim(dimensional_object_mapping_sample_query) <> ''),
    CONSTRAINT ck_dimensional_object_mapping_transformation CHECK (btrim(dimensional_object_mapping_transformation) <> '')
);
CREATE INDEX ix_dimensional_object_mapping_system_id ON workflow.dimensional_object_mapping (system_id);

-- Mapping, the attribute part: one line per attribute of the mapping's own entity, with one free field.
-- Only the mapping and the attribute are stored; core/ checks the attribute is the mapping entity's (MAPPING-001).
CREATE TABLE workflow.dimensional_attribute_mapping (
    dimensional_attribute_mapping_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_object_mapping_id                BIGINT NOT NULL,
    dimensional_attribute_id                     BIGINT NOT NULL,
    dimensional_attribute_mapping_transformation TEXT, -- plain words, SQL, or both
    is_locked                                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_attribute_mapping PRIMARY KEY (dimensional_attribute_mapping_id),
    CONSTRAINT fk_dimensional_attribute_mapping_dimensional_object_mapping FOREIGN KEY (dimensional_object_mapping_id)
        REFERENCES workflow.dimensional_object_mapping (dimensional_object_mapping_id),
    CONSTRAINT fk_dimensional_attribute_mapping_dimensional_attribute FOREIGN KEY (dimensional_attribute_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id),
    CONSTRAINT uq_dimensional_attribute_mapping_mapping_attribute UNIQUE (dimensional_object_mapping_id, dimensional_attribute_id),
    CONSTRAINT ck_dimensional_attribute_mapping_transformation CHECK (btrim(dimensional_attribute_mapping_transformation) <> '')
);
CREATE INDEX ix_dimensional_attribute_mapping_dimensional_attribute_id ON workflow.dimensional_attribute_mapping (dimensional_attribute_id);

