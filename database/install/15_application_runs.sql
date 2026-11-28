-- 15_application_runs.sql
-- Schema application: Runs, the Run log and AI usage (v2 workflow_run, project_event_log and workflow_run_model_request).
-- A Run is one press of Run on a step. It prepares the context, calls the AI (except profiling) and ends in a draft
-- change set; the Run records which one (project_change_set_id). Change sets know nothing about Runs, so VS Code
-- pushes and hand edits are unaffected. Only one Run at a time per tenant: Runs in different tenants can run
-- at the same time. core/ marks a Run whose Run log has not moved for 30 minutes as failed before starting the next
-- (Nov 28, Maaz). A tool based Run that reaches its turn limit, or whose model call fails, ends as stopped: it keeps
-- the draft it made so far and says why.
-- Tables, keys and simple checks only. Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.
--
-- Not carried over from v2: the queue and claim columns (claim token, heartbeat, expiry, recovery count; no worker
-- queue in v3), digests, correlation id, receipts, the no-op columns, usage tracking version and flags, mapping
-- template ids, failure_code, the Entra identity id, agent_sdk_code and agent_provider_code (the model's provider is
-- its calling code), and the per-workflow option columns (modeled entity type, code
-- layout and coverage, mapping operation and coverage, batch ids, profiling counts), which go into run_request_document.
-- v2's six selection tables (object, entity, system, subject area, mapping target, prompt snapshot) are replaced by
-- run_request_document and prompt_version_id (a prompt version never changes, so no snapshot is needed).
-- Statuses queued, completed_with_repair and cancelled are gone (no queue, no repair loops, no cancel yet), and so is
-- validation_retry_count (v2's repair loop).

-- One Run.
CREATE TABLE application.run (
    run_id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id               BIGINT NOT NULL,                   -- the project's tenant (RUN-001); kept here so Postgres allows one running Run per tenant
    project_id              BIGINT NOT NULL,
    project_workflow        VARCHAR(50) NOT NULL,              -- the step: the prompt steps plus profiling
    workflow_execution_mode VARCHAR(20),                       -- one_shot or tool_assisted; empty for profiling (no AI)
    base_project_version    BIGINT NOT NULL,                   -- v2 project_revision: the project version the Run started from
    prompt_version_id       BIGINT,                            -- the prompt text used; empty for profiling
    extra_instructions      TEXT,                              -- text added for this Run only
    agent_model_id          BIGINT,                            -- AI settings for this Run, copied from project_config or changed by the person;
                                                               -- the provider comes from the model. Empty for profiling
    reasoning_effort_code   VARCHAR(50),                       -- one of the model's reasoning_effort_codes (RUN-002)
    max_turns               INTEGER,                           -- tool based Runs: the turn limit, at which the Run stops
    run_request_document    JSONB NOT NULL DEFAULT '{}',       -- what the person picked: subject areas, entities, systems, tables, options
    run_status              VARCHAR(20) NOT NULL DEFAULT 'running', -- running, completed, stopped or failed (v2 workflow_run_state)
    started_by_principal_id BIGINT NOT NULL,                   -- v2 actor_principal_id
    started_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_time          TIMESTAMPTZ,                       -- when it completed, stopped or failed
    failure_message         TEXT,                              -- why it failed, or why a tool based Run stopped
    project_change_set_id   BIGINT,                            -- the draft this Run made; empty while running or if it failed
    created_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by              VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_run PRIMARY KEY (run_id),
    CONSTRAINT fk_run_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_run_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id),
    CONSTRAINT fk_run_prompt_version FOREIGN KEY (prompt_version_id)
        REFERENCES application.prompt_version (prompt_version_id),
    CONSTRAINT fk_run_agent_model FOREIGN KEY (agent_model_id)
        REFERENCES reference.agent_model (agent_model_id),
    CONSTRAINT fk_run_project_change_set FOREIGN KEY (project_change_set_id)
        REFERENCES application.project_change_set (project_change_set_id),
    CONSTRAINT fk_run_started_by_principal FOREIGN KEY (started_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT ck_run_project_workflow CHECK (project_workflow IN (
        'profiling', 'object_enrichment', 'attribute_enrichment', 'analysis', 'subject_area',
        'operational', 'dimensional', 'operational_mapping', 'dimensional_mapping',
        'operational_code', 'dimensional_code', 'operational_validation', 'dimensional_validation')),
    CONSTRAINT ck_run_workflow_execution_mode CHECK (workflow_execution_mode IN ('one_shot', 'tool_assisted')),
    -- Profiling has no AI: no kind of Run and no prompt. Every other step has both.
    CONSTRAINT ck_run_ai_mode CHECK ((project_workflow = 'profiling') = (workflow_execution_mode IS NULL)),
    CONSTRAINT ck_run_ai_prompt CHECK ((project_workflow = 'profiling') = (prompt_version_id IS NULL)),
    CONSTRAINT ck_run_ai_model CHECK ((project_workflow = 'profiling') = (agent_model_id IS NULL)),
    CONSTRAINT ck_run_base_project_version CHECK (base_project_version > 0),
    CONSTRAINT ck_run_extra_instructions CHECK (btrim(extra_instructions) <> ''),
    CONSTRAINT ck_run_max_turns CHECK (max_turns > 0),
    CONSTRAINT ck_run_request_document CHECK (jsonb_typeof(run_request_document) = 'object'),
    CONSTRAINT ck_run_status CHECK (run_status IN ('running', 'completed', 'stopped', 'failed')),
    CONSTRAINT ck_run_completed CHECK ((run_status = 'running') = (completed_time IS NULL)),
    CONSTRAINT ck_run_failure_message CHECK ((run_status IN ('stopped', 'failed')) = (failure_message IS NOT NULL)),
    -- A completed Run may have a draft; a stopped Run always has the draft it made so far; the others have none.
    CONSTRAINT ck_run_change_set CHECK (run_status IN ('completed', 'stopped') OR project_change_set_id IS NULL),
    CONSTRAINT ck_run_stopped_change_set CHECK (run_status <> 'stopped' OR project_change_set_id IS NOT NULL),
    CONSTRAINT ck_run_failure_message_text CHECK (btrim(failure_message) <> '')
);
CREATE INDEX ix_run_tenant_id ON application.run (tenant_id);
CREATE INDEX ix_run_project_id ON application.run (project_id);
CREATE INDEX ix_run_agent_model_id ON application.run (agent_model_id);
CREATE INDEX ix_run_prompt_version_id ON application.run (prompt_version_id);
CREATE INDEX ix_run_started_by_principal_id ON application.run (started_by_principal_id);
CREATE UNIQUE INDEX ux_run_project_change_set_id ON application.run (project_change_set_id); -- a draft comes from at most one Run
-- One running Run per tenant.
CREATE UNIQUE INDEX ux_run_tenant_running ON application.run (tenant_id) WHERE run_status = 'running';

-- The Run log: one row per stage of a Run, shown to the person while it runs (v2 project.project_event_log).
CREATE TABLE application.run_event (
    run_event_id      BIGINT GENERATED ALWAYS AS IDENTITY,
    run_id            BIGINT NOT NULL,
    run_event_stage   VARCHAR(50) NOT NULL,  -- for example prepare_context, fetch_samples, ai_call, draft
    run_event_status  VARCHAR(20) NOT NULL,  -- started, completed or failed
    run_event_message TEXT,                  -- for example "Profiled 3 of 20 tables"
    created_time      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- when it happened
    created_by        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by        VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_run_event PRIMARY KEY (run_event_id),
    CONSTRAINT fk_run_event_run FOREIGN KEY (run_id)
        REFERENCES application.run (run_id),
    CONSTRAINT ck_run_event_stage CHECK (btrim(run_event_stage) <> ''),
    CONSTRAINT ck_run_event_status CHECK (run_event_status IN ('started', 'completed', 'failed')),
    CONSTRAINT ck_run_event_message CHECK (btrim(run_event_message) <> '')
);
CREATE INDEX ix_run_event_run_id ON application.run_event (run_id);

-- AI usage: one row per AI call in a Run (v2 workflow_run_model_request). The tenant and project come through the Run.
CREATE TABLE application.run_model_request (
    run_model_request_id     BIGINT GENERATED ALWAYS AS IDENTITY,
    run_id                   BIGINT NOT NULL,
    started_time             TIMESTAMPTZ NOT NULL,
    completed_time           TIMESTAMPTZ,
    input_tokens             BIGINT NOT NULL DEFAULT 0,
    cached_input_tokens      BIGINT NOT NULL DEFAULT 0,
    cache_write_input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens            BIGINT NOT NULL DEFAULT 0,
    reasoning_output_tokens  BIGINT NOT NULL DEFAULT 0,
    cost_usd                 NUMERIC(12, 6),          -- worked out by core/ from its price list when the call is made
    created_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by               VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_run_model_request PRIMARY KEY (run_model_request_id),
    CONSTRAINT fk_run_model_request_run FOREIGN KEY (run_id)
        REFERENCES application.run (run_id),
    CONSTRAINT ck_run_model_request_times CHECK (completed_time >= started_time),
    CONSTRAINT ck_run_model_request_tokens CHECK (input_tokens >= 0 AND cached_input_tokens >= 0 AND cache_write_input_tokens >= 0
        AND output_tokens >= 0 AND reasoning_output_tokens >= 0),
    CONSTRAINT ck_run_model_request_cost CHECK (cost_usd >= 0)
);
CREATE INDEX ix_run_model_request_run_id ON application.run_model_request (run_id);
