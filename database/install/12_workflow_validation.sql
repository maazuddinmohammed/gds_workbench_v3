-- 12_workflow_validation.sql
-- Schema workflow, part 7: validation. Checks that test the loaded tables after the code runs, as in v2.
-- A validation group holds the checks for one source system; each check is a query and the result it must give.
-- Operational and dimensional checks are stored apart, like the models, mappings and code.
-- Patterns: see the top of 06_workflow_analysis.sql.
--
-- Not carried over from v2: the type field (operational or dimensional; the table says it), tenant id (the project
-- has it), run ids (runs come in step 1h), digests, is_active (remove a row by deleting it in an Apply), and the
-- long checks on which operator needs which value (that rule lives in core/).

-- operational validation ----------------------------------------------------------------------------------

-- A group of checks for the operational model of one source system (v2 validation_group, operational half).
-- The AI writes the checks from the applied mapping and code; a person reviews them in a change set.
CREATE TABLE workflow.operational_validation_group (
    operational_validation_group_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                               BIGINT NOT NULL,
    system_id                                BIGINT NOT NULL,
    operational_validation_group_name        VARCHAR(200) NOT NULL,
    operational_validation_group_description TEXT,
    is_locked                                BOOLEAN NOT NULL DEFAULT FALSE,
    created_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_validation_group PRIMARY KEY (operational_validation_group_id),
    CONSTRAINT fk_operational_validation_group_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_operational_validation_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT ck_operational_validation_group_name CHECK (btrim(operational_validation_group_name) <> ''),
    CONSTRAINT ck_operational_validation_group_description CHECK (operational_validation_group_description IS NULL OR btrim(operational_validation_group_description) <> '')
);
CREATE UNIQUE INDEX ux_operational_validation_group_system_name ON workflow.operational_validation_group (project_id, system_id, lower(btrim(operational_validation_group_name)));
CREATE INDEX ix_operational_validation_group_system_id ON workflow.operational_validation_group (system_id);

-- One check in a group (v2 validation_check, operational half): a query, and what its result must be.
-- Postgres only checks each value is from its list. Which operator needs which value (for example 'in' needs
-- a literal list) is checked in core/, not here.
CREATE TABLE workflow.operational_validation_check (
    operational_validation_check_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    operational_validation_group_id          BIGINT NOT NULL,
    operational_validation_check_name        VARCHAR(200) NOT NULL,
    operational_validation_check_description TEXT,
    validation_category_code                 VARCHAR(100) NOT NULL, -- for example row_count, uniqueness, referential
    validation_severity                      VARCHAR(20) NOT NULL,  -- blocking, warning or informational
    validation_query_sql                     TEXT NOT NULL,         -- the query that is run
    validation_comparison_query_sql          TEXT,                  -- a second query to compare with (value type 'query')
    validation_result_data_type              VARCHAR(20),           -- boolean, integer, decimal, text, date or timestamp
    validation_comparison_operator           VARCHAR(30) NOT NULL,  -- executes_successfully, equal, greater_than, in, ...
    validation_comparison_value_type         VARCHAR(20) NOT NULL,  -- none, literal, literal_list or query
    validation_comparison_value              JSONB,                 -- the expected value or list of values
    is_locked                                BOOLEAN NOT NULL DEFAULT FALSE,
    created_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_operational_validation_check PRIMARY KEY (operational_validation_check_id),
    CONSTRAINT fk_operational_validation_check_operational_validation_group FOREIGN KEY (operational_validation_group_id)
        REFERENCES workflow.operational_validation_group (operational_validation_group_id),
    CONSTRAINT ck_operational_validation_check_name CHECK (btrim(operational_validation_check_name) <> ''),
    CONSTRAINT ck_operational_validation_check_description CHECK (operational_validation_check_description IS NULL OR btrim(operational_validation_check_description) <> ''),
    CONSTRAINT ck_operational_validation_check_category CHECK (btrim(validation_category_code) <> ''),
    CONSTRAINT ck_operational_validation_check_severity CHECK (validation_severity IN ('blocking', 'warning', 'informational')),
    CONSTRAINT ck_operational_validation_check_query CHECK (btrim(validation_query_sql) <> ''),
    CONSTRAINT ck_operational_validation_check_comparison_query CHECK (validation_comparison_query_sql IS NULL OR btrim(validation_comparison_query_sql) <> ''),
    CONSTRAINT ck_operational_validation_check_result_type CHECK (validation_result_data_type IS NULL
        OR validation_result_data_type IN ('boolean', 'integer', 'decimal', 'text', 'date', 'timestamp')),
    CONSTRAINT ck_operational_validation_check_operator CHECK (validation_comparison_operator IN ('executes_successfully',
        'is_null', 'is_not_null', 'is_true', 'is_false', 'equal', 'not_equal', 'greater_than', 'greater_than_or_equal',
        'less_than', 'less_than_or_equal', 'in', 'not_in')),
    CONSTRAINT ck_operational_validation_check_value_type CHECK (validation_comparison_value_type IN ('none', 'literal', 'literal_list', 'query'))
);
CREATE UNIQUE INDEX ux_operational_validation_check_group_name ON workflow.operational_validation_check (operational_validation_group_id, lower(btrim(operational_validation_check_name)));

-- dimensional validation ----------------------------------------------------------------------------------

-- A group of checks for the dimensional model of one source system (v2 validation_group, dimensional half).
-- The AI writes the checks from the applied mapping and code; a person reviews them in a change set.
CREATE TABLE workflow.dimensional_validation_group (
    dimensional_validation_group_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    project_id                               BIGINT NOT NULL,
    system_id                                BIGINT NOT NULL,
    dimensional_validation_group_name        VARCHAR(200) NOT NULL,
    dimensional_validation_group_description TEXT,
    is_locked                                BOOLEAN NOT NULL DEFAULT FALSE,
    created_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_validation_group PRIMARY KEY (dimensional_validation_group_id),
    CONSTRAINT fk_dimensional_validation_group_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_dimensional_validation_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id),
    CONSTRAINT ck_dimensional_validation_group_name CHECK (btrim(dimensional_validation_group_name) <> ''),
    CONSTRAINT ck_dimensional_validation_group_description CHECK (dimensional_validation_group_description IS NULL OR btrim(dimensional_validation_group_description) <> '')
);
CREATE UNIQUE INDEX ux_dimensional_validation_group_system_name ON workflow.dimensional_validation_group (project_id, system_id, lower(btrim(dimensional_validation_group_name)));
CREATE INDEX ix_dimensional_validation_group_system_id ON workflow.dimensional_validation_group (system_id);

-- One check in a group (v2 validation_check, dimensional half): a query, and what its result must be.
-- Postgres only checks each value is from its list. Which operator needs which value (for example 'in' needs
-- a literal list) is checked in core/, not here.
CREATE TABLE workflow.dimensional_validation_check (
    dimensional_validation_check_id          BIGINT GENERATED ALWAYS AS IDENTITY,
    dimensional_validation_group_id          BIGINT NOT NULL,
    dimensional_validation_check_name        VARCHAR(200) NOT NULL,
    dimensional_validation_check_description TEXT,
    validation_category_code                 VARCHAR(100) NOT NULL, -- for example row_count, uniqueness, referential
    validation_severity                      VARCHAR(20) NOT NULL,  -- blocking, warning or informational
    validation_query_sql                     TEXT NOT NULL,         -- the query that is run
    validation_comparison_query_sql          TEXT,                  -- a second query to compare with (value type 'query')
    validation_result_data_type              VARCHAR(20),           -- boolean, integer, decimal, text, date or timestamp
    validation_comparison_operator           VARCHAR(30) NOT NULL,  -- executes_successfully, equal, greater_than, in, ...
    validation_comparison_value_type         VARCHAR(20) NOT NULL,  -- none, literal, literal_list or query
    validation_comparison_value              JSONB,                 -- the expected value or list of values
    is_locked                                BOOLEAN NOT NULL DEFAULT FALSE,
    created_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time                             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_dimensional_validation_check PRIMARY KEY (dimensional_validation_check_id),
    CONSTRAINT fk_dimensional_validation_check_dimensional_validation_group FOREIGN KEY (dimensional_validation_group_id)
        REFERENCES workflow.dimensional_validation_group (dimensional_validation_group_id),
    CONSTRAINT ck_dimensional_validation_check_name CHECK (btrim(dimensional_validation_check_name) <> ''),
    CONSTRAINT ck_dimensional_validation_check_description CHECK (dimensional_validation_check_description IS NULL OR btrim(dimensional_validation_check_description) <> ''),
    CONSTRAINT ck_dimensional_validation_check_category CHECK (btrim(validation_category_code) <> ''),
    CONSTRAINT ck_dimensional_validation_check_severity CHECK (validation_severity IN ('blocking', 'warning', 'informational')),
    CONSTRAINT ck_dimensional_validation_check_query CHECK (btrim(validation_query_sql) <> ''),
    CONSTRAINT ck_dimensional_validation_check_comparison_query CHECK (validation_comparison_query_sql IS NULL OR btrim(validation_comparison_query_sql) <> ''),
    CONSTRAINT ck_dimensional_validation_check_result_type CHECK (validation_result_data_type IS NULL
        OR validation_result_data_type IN ('boolean', 'integer', 'decimal', 'text', 'date', 'timestamp')),
    CONSTRAINT ck_dimensional_validation_check_operator CHECK (validation_comparison_operator IN ('executes_successfully',
        'is_null', 'is_not_null', 'is_true', 'is_false', 'equal', 'not_equal', 'greater_than', 'greater_than_or_equal',
        'less_than', 'less_than_or_equal', 'in', 'not_in')),
    CONSTRAINT ck_dimensional_validation_check_value_type CHECK (validation_comparison_value_type IN ('none', 'literal', 'literal_list', 'query'))
);
CREATE UNIQUE INDEX ux_dimensional_validation_check_group_name ON workflow.dimensional_validation_check (dimensional_validation_group_id, lower(btrim(dimensional_validation_check_name)));
