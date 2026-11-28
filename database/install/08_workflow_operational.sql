-- 08_workflow_operational.sql
-- Schema workflow, part 3: the operational model (builds the Silver zone). Five tables, same shape as v2.
-- The dimensional model (09) has the same five tables with dimensional_ names. Operational sources point at Bronze tables
-- and columns in the project's scope.
-- Patterns: see the top of 06_workflow_analysis.sql. Only the entity has project_id. Cross checks are rules in
-- core/ (OPERATIONAL-001 to 003 in docs/rules.md).
--
-- Not carried over from v2: the Note as a source
-- (sources are tables only; Notes reach a Run through the prompt builder), the link's cardinality and basis.

-- A modeled table. Definition and Grain are two fields.
CREATE TABLE workflow.operational_entity (
    operational_entity_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                          BIGINT NOT NULL,
    operational_entity_type_id          BIGINT,
    operational_entity_schema_name      VARCHAR(400) NOT NULL, -- one of the project's operational schemas (project_config)
    operational_entity_name             VARCHAR(255) NOT NULL,
    operational_entity_definition       TEXT,
    operational_entity_grain            TEXT,                  -- what one row means
    operational_entity_dependency_order INTEGER,               -- load order, parents first; worked out by a separate step without AI, a person may edit it
    is_merged                           BOOLEAN NOT NULL DEFAULT FALSE, -- one row per real thing across all systems, instead of one row per system
    is_locked                           BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                           BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_entity PRIMARY KEY (operational_entity_id),
    CONSTRAINT fk_operational_entity_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT uq_operational_entity_id_project UNIQUE (operational_entity_id, project_id), -- lets a validation group name the entity and its project together
    CONSTRAINT fk_operational_entity_operational_entity_type FOREIGN KEY (operational_entity_type_id)
        REFERENCES reference.operational_entity_type (operational_entity_type_id),
    CONSTRAINT ck_operational_entity_schema_name CHECK (btrim(operational_entity_schema_name) <> ''),
    CONSTRAINT ck_operational_entity_name CHECK (btrim(operational_entity_name) <> ''),
    CONSTRAINT ck_operational_entity_definition CHECK (btrim(operational_entity_definition) <> ''),
    CONSTRAINT ck_operational_entity_grain CHECK (btrim(operational_entity_grain) <> ''),
    CONSTRAINT ck_operational_entity_dependency_order CHECK (operational_entity_dependency_order > 0)
);
CREATE UNIQUE INDEX ux_operational_entity_project_schema_name ON workflow.operational_entity (project_id, lower(btrim(operational_entity_schema_name)), lower(btrim(operational_entity_name)));

-- A column of an entity. Every entity marks its operational key (is_surrogate_key, an identity column the load fills)
-- and its natural key (is_natural_key, the source's own identifier; several columns if it is composite).
CREATE TABLE workflow.operational_attribute (
    operational_attribute_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_entity_id                  BIGINT NOT NULL,
    operational_attribute_name             VARCHAR(255) NOT NULL,
    operational_attribute_definition       TEXT,
    operational_attribute_data_type        VARCHAR(100) NOT NULL,
    operational_attribute_ordinal_position INTEGER NOT NULL,
    is_nullable                            BOOLEAN NOT NULL DEFAULT TRUE,
    is_surrogate_key                       BOOLEAN NOT NULL DEFAULT FALSE,
    is_natural_key                         BOOLEAN NOT NULL DEFAULT FALSE,
    is_locked                              BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_attribute PRIMARY KEY (operational_attribute_id),
    CONSTRAINT fk_operational_attribute_operational_entity FOREIGN KEY (operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT ck_operational_attribute_name CHECK (btrim(operational_attribute_name) <> ''),
    CONSTRAINT ck_operational_attribute_definition CHECK (btrim(operational_attribute_definition) <> ''),
    CONSTRAINT ck_operational_attribute_data_type CHECK (btrim(operational_attribute_data_type) <> ''),
    CONSTRAINT ck_operational_attribute_ordinal_position CHECK (operational_attribute_ordinal_position > 0)
);
CREATE UNIQUE INDEX ux_operational_attribute_entity_name ON workflow.operational_attribute (operational_entity_id, lower(btrim(operational_attribute_name)));

-- Entity source: a Bronze table that feeds the entity, plus a note for mapping (how, not why; v2 rationale).
-- One source can feed several entities, and several sources can feed one entity.
-- The project comes from the entity. core/ checks the table is in the project's scope (OPERATIONAL-001).
CREATE TABLE workflow.operational_entity_source (
    operational_entity_source_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_entity_id          BIGINT NOT NULL,
    object_id                      BIGINT NOT NULL,
    operational_entity_source_note TEXT, -- note for mapping, for example "only active rows"
    is_locked                      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_entity_source PRIMARY KEY (operational_entity_source_id),
    CONSTRAINT fk_operational_entity_source_operational_entity FOREIGN KEY (operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT fk_operational_entity_source_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id),
    CONSTRAINT uq_operational_entity_source_entity_source UNIQUE (operational_entity_id, object_id),
    CONSTRAINT ck_operational_entity_source_note CHECK (btrim(operational_entity_source_note) <> '')
);
CREATE INDEX ix_operational_entity_source_object_id ON workflow.operational_entity_source (object_id);

-- Attribute source: a Bronze column that feeds the attribute, plus a note for mapping.
-- Only the two attributes are stored: the entity, the source table and the project all follow from them.
-- core/ checks the column belongs to one of the entity's source tables (OPERATIONAL-002).
CREATE TABLE workflow.operational_attribute_source (
    operational_attribute_source_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_attribute_id          BIGINT NOT NULL,
    attribute_id                      BIGINT NOT NULL,
    operational_attribute_source_note TEXT, -- note for mapping, for example "trim, then upper case"
    is_locked                         BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                         BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_attribute_source PRIMARY KEY (operational_attribute_source_id),
    CONSTRAINT fk_operational_attribute_source_operational_attribute FOREIGN KEY (operational_attribute_id)
        REFERENCES workflow.operational_attribute (operational_attribute_id),
    CONSTRAINT fk_operational_attribute_source_attribute FOREIGN KEY (attribute_id)
        REFERENCES core.attribute (attribute_id),
    CONSTRAINT uq_operational_attribute_source_attribute_source UNIQUE (operational_attribute_id, attribute_id),
    CONSTRAINT ck_operational_attribute_source_note CHECK (btrim(operational_attribute_source_note) <> '')
);
CREATE INDEX ix_operational_attribute_source_attribute_id ON workflow.operational_attribute_source (attribute_id);

-- Link: a child's foreign-key attribute pointing at a parent entity (v2 operational_relationship).
-- The child entity follows from the attribute. The parent's key and natural key are its marked attributes.
-- Any link is allowed, even to itself. core/ checks the parent is in the same project (OPERATIONAL-003).
CREATE TABLE workflow.operational_link (
    operational_link_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_attribute_id     BIGINT NOT NULL, -- the child's foreign-key attribute
    parent_operational_entity_id BIGINT NOT NULL,
    is_locked                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_link PRIMARY KEY (operational_link_id),
    CONSTRAINT fk_operational_link_operational_attribute FOREIGN KEY (operational_attribute_id)
        REFERENCES workflow.operational_attribute (operational_attribute_id),
    CONSTRAINT fk_operational_link_parent_operational_entity FOREIGN KEY (parent_operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT uq_operational_link_operational_attribute UNIQUE (operational_attribute_id)
);
CREATE INDEX ix_operational_link_parent_operational_entity_id ON workflow.operational_link (parent_operational_entity_id);
