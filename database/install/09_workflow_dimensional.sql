-- 09_workflow_dimensional.sql
-- Schema workflow, part 4: the dimensional model (builds the Gold zone). The same five tables as the operational
-- model (08), with dimensional_ names. It reads the operational model only: its sources point at operational entities and
-- attributes of the same project, never at Bronze.
-- Patterns: see the top of 06_workflow_analysis.sql. Only the entity has project_id. Cross checks are rules in
-- core/ (DIMENSIONAL-001 to 003 in docs/rules.md).
--
-- Not carried over from v2: the bridge kind (an entity is a fact or a dimension), the fact type, the
-- Note as a source, the link's role name and basis, and the checks on which entity may point at which.

-- A modeled table: a Fact or a Dimension. Definition and Grain are two fields.
CREATE TABLE workflow.dimensional_entity (
    dimensional_entity_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                          BIGINT NOT NULL,
    dimensional_entity_type             VARCHAR(20) NOT NULL,  -- fact or dimension
    dimensional_entity_schema_name      VARCHAR(400) NOT NULL, -- one of the project's dimensional schemas (project_config)
    dimensional_entity_name             VARCHAR(255) NOT NULL,
    dimensional_entity_definition       TEXT,
    dimensional_entity_grain            TEXT,                  -- what one row means
    dimensional_entity_dependency_order INTEGER,               -- load order, parents first; worked out by Python and stored, empty until worked out
    is_locked                           BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                           BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                          VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_entity PRIMARY KEY (dimensional_entity_id),
    CONSTRAINT fk_dimensional_entity_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT ck_dimensional_entity_schema_name CHECK (btrim(dimensional_entity_schema_name) <> ''),
    CONSTRAINT ck_dimensional_entity_name CHECK (btrim(dimensional_entity_name) <> ''),
    CONSTRAINT ck_dimensional_entity_type CHECK (dimensional_entity_type IN ('fact', 'dimension')),
    CONSTRAINT ck_dimensional_entity_definition CHECK (btrim(dimensional_entity_definition) <> ''),
    CONSTRAINT ck_dimensional_entity_grain CHECK (btrim(dimensional_entity_grain) <> ''),
    CONSTRAINT ck_dimensional_entity_dependency_order CHECK (dimensional_entity_dependency_order > 0)
);
CREATE UNIQUE INDEX ux_dimensional_entity_project_schema_name ON workflow.dimensional_entity (project_id, lower(btrim(dimensional_entity_schema_name)), lower(btrim(dimensional_entity_name)));

-- A column of an entity. Every entity marks its dimensional key (is_surrogate_key, the key Python generates)
-- and its natural key (is_natural_key, the source's own identifier; several columns if it is composite).
CREATE TABLE workflow.dimensional_attribute (
    dimensional_attribute_id               BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_entity_id                  BIGINT NOT NULL,
    dimensional_attribute_name             VARCHAR(255) NOT NULL,
    dimensional_attribute_definition       TEXT,
    dimensional_attribute_data_type        VARCHAR(100) NOT NULL,
    dimensional_attribute_ordinal_position INTEGER NOT NULL,
    is_nullable                            BOOLEAN NOT NULL DEFAULT TRUE,
    is_surrogate_key                       BOOLEAN NOT NULL DEFAULT FALSE,
    is_natural_key                         BOOLEAN NOT NULL DEFAULT FALSE,
    is_audit_column                        BOOLEAN NOT NULL DEFAULT FALSE, -- added by Python, for example CreatedDate
    is_locked                              BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_attribute PRIMARY KEY (dimensional_attribute_id),
    CONSTRAINT fk_dimensional_attribute_dimensional_entity FOREIGN KEY (dimensional_entity_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id),
    CONSTRAINT ck_dimensional_attribute_name CHECK (btrim(dimensional_attribute_name) <> ''),
    CONSTRAINT ck_dimensional_attribute_definition CHECK (btrim(dimensional_attribute_definition) <> ''),
    CONSTRAINT ck_dimensional_attribute_data_type CHECK (btrim(dimensional_attribute_data_type) <> ''),
    CONSTRAINT ck_dimensional_attribute_ordinal_position CHECK (dimensional_attribute_ordinal_position > 0)
);
CREATE UNIQUE INDEX ux_dimensional_attribute_entity_name ON workflow.dimensional_attribute (dimensional_entity_id, lower(btrim(dimensional_attribute_name)));

-- Entity source: an operational entity that feeds the entity, plus a note for mapping (how, not why; v2 rationale).
-- One source can feed several entities, and several sources can feed one entity.
-- The project comes from the entity. core/ checks the operational entity is in the same project (DIMENSIONAL-001).
CREATE TABLE workflow.dimensional_entity_source (
    dimensional_entity_source_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_entity_id          BIGINT NOT NULL,
    operational_entity_id          BIGINT NOT NULL,
    dimensional_entity_source_note TEXT, -- note for mapping, for example "only active rows"
    is_locked                      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                      BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                     VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_entity_source PRIMARY KEY (dimensional_entity_source_id),
    CONSTRAINT fk_dimensional_entity_source_dimensional_entity FOREIGN KEY (dimensional_entity_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id),
    CONSTRAINT fk_dimensional_entity_source_operational_entity FOREIGN KEY (operational_entity_id)
        REFERENCES workflow.operational_entity (operational_entity_id),
    CONSTRAINT uq_dimensional_entity_source_entity_source UNIQUE (dimensional_entity_id, operational_entity_id),
    CONSTRAINT ck_dimensional_entity_source_note CHECK (btrim(dimensional_entity_source_note) <> '')
);
CREATE INDEX ix_dimensional_entity_source_operational_entity_id ON workflow.dimensional_entity_source (operational_entity_id);

-- Attribute source: an operational attribute that feeds the attribute, plus a note for mapping.
-- Only the two attributes are stored: the entity, the source entity and the project all follow from them.
-- core/ checks the operational attribute belongs to one of the entity's source entities (DIMENSIONAL-002).
CREATE TABLE workflow.dimensional_attribute_source (
    dimensional_attribute_source_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_attribute_id          BIGINT NOT NULL,
    operational_attribute_id          BIGINT NOT NULL,
    dimensional_attribute_source_note TEXT, -- note for mapping, for example "trim, then upper case"
    is_locked                         BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                         BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_attribute_source PRIMARY KEY (dimensional_attribute_source_id),
    CONSTRAINT fk_dimensional_attribute_source_dimensional_attribute FOREIGN KEY (dimensional_attribute_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id),
    CONSTRAINT fk_dimensional_attribute_source_operational_attribute FOREIGN KEY (operational_attribute_id)
        REFERENCES workflow.operational_attribute (operational_attribute_id),
    CONSTRAINT uq_dimensional_attribute_source_attribute_source UNIQUE (dimensional_attribute_id, operational_attribute_id),
    CONSTRAINT ck_dimensional_attribute_source_note CHECK (btrim(dimensional_attribute_source_note) <> '')
);
CREATE INDEX ix_dimensional_attribute_source_operational_attribute_id ON workflow.dimensional_attribute_source (operational_attribute_id);

-- Link: a child's foreign-key attribute pointing at a parent entity (v2 dimensional_relationship).
-- The child entity follows from the attribute. The parent's key and natural key are its marked attributes.
-- Any link is allowed: a Fact or a Dimension can point at any dimensional entity, even itself. core/ checks the parent is in the same project (DIMENSIONAL-003).
CREATE TABLE workflow.dimensional_link (
    dimensional_link_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_attribute_id     BIGINT NOT NULL, -- the child's foreign-key attribute
    parent_dimensional_entity_id BIGINT NOT NULL,
    is_locked                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                   VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_link PRIMARY KEY (dimensional_link_id),
    CONSTRAINT fk_dimensional_link_dimensional_attribute FOREIGN KEY (dimensional_attribute_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id),
    CONSTRAINT fk_dimensional_link_parent_dimensional_entity FOREIGN KEY (parent_dimensional_entity_id)
        REFERENCES workflow.dimensional_entity (dimensional_entity_id),
    CONSTRAINT uq_dimensional_link_dimensional_attribute UNIQUE (dimensional_attribute_id)
);
CREATE INDEX ix_dimensional_link_parent_dimensional_entity_id ON workflow.dimensional_link (parent_dimensional_entity_id);
