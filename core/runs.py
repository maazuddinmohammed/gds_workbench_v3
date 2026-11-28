"""Runs: what happens when a person presses Run on a step (design/overview/run.md). One engine for every AI step.

`start_run` checks the request (RUN-001 to 005) and saves the Run. `execute` then does it, in the background: it
prepares the context, calls the AI, turns the answers into one draft change set and checks it, writing one line per
stage to the Run log. Nothing is saved to the project until a person applies the draft.

Each step adds only what is its own, as a `Step` (core/enrichment.py and the other step modules): its inputs, how it
picks its items, what it gives the AI for each item, its answer shape and how an answer becomes draft records.

A one shot Run makes one AI call per item. The calls run eight at a time (decided Nov 28 by Claude, for Maaz to
check: one after another took over an hour for a scope of 93 tables); everything else stays in order. An answer
that is cut off or does not fit is skipped and the log names its item (RUN-006); there are no retries.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core import ai, change_sets, prompts
from core.access import CHANGE, READ, require
from core.problems import NotFound, Refused

STALE_MINUTES = 30  # a Run whose log has not moved for this long has stopped (RUN-003)
PARALLEL_CALLS = 8
DEFAULT_MAX_TURNS = 100


@dataclass(frozen=True)
class Step:
    workflow: str  # application.run.project_workflow
    title: str  # for the draft's title, such as "Object enrichment"
    inputs: dict  # input name -> what it holds, for the guide to the inputs and PROMPT-001
    answer: dict  # the answer's strict JSON schema: {"name": ..., "schema": ...}
    items: Callable  # (cur, project_id, request) -> list of items; raises Refused("RUN-005") when one is missing
    prepare: Callable  # (cur, run, items) -> {item label: inputs}, a label None to skip, plus log lines
    records: Callable  # (cur, run, label, answer) -> ({part: [records]}, log lines)
    mode: str = "one_shot"
    run_tools: Callable = None  # tool based Runs: (cur, run, call, log) -> {part: [records]}
    label: Callable = field(default=lambda item: str(item))


def steps():
    from core import code, enrichment, mapping, models, relationships, subject_areas, validation

    return {s.workflow: s for s in (*enrichment.STEPS, relationships.STEP, subject_areas.STEP, *models.STEPS.values(),
                                    *mapping.STEPS, *code.STEPS, *validation.STEPS)}


def start_run(conn, principal_id, project_id, workflow, request=None, prompt_version_id=None, agent_model_id=None,
              reasoning_effort_code=None, max_turns=None, extra_instructions=None, via_mcp=False):
    """Check a Run and save it as running; returns its id. `execute` does the work.

    Needs CHANGE, the tenant lock and an unlocked project. The AI settings come from the project's defaults unless
    the person changes them for this Run.
    """
    step = steps().get(workflow)
    if step is None:
        raise ValueError(f"unknown step {workflow!r}")
    request = request or {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM project.project WHERE project_id = %s AND is_active", (project_id,))
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        tenant_id = project["tenant_id"]
        require(conn, principal_id, tenant_id, CHANGE, project_id=project_id, via_mcp=via_mcp)
        with conn.transaction():
            run_003(cur, tenant_id)
            step.items(cur, project_id, request)  # RUN-005
            prompt = (prompts.version(cur, prompt_version_id) if prompt_version_id
                      else prompts.default_version(cur, tenant_id, workflow, step.mode))
            run_004(prompt, workflow)
            cur.execute(
                """SELECT default_agent_model_id, default_reasoning_effort_code, default_max_turns
                     FROM project.project_config WHERE project_id = %s""",
                (project_id,),
            )
            defaults = cur.fetchone() or {}
            model = _model(cur, agent_model_id or defaults.get("default_agent_model_id"))
            effort = reasoning_effort_code or defaults.get("default_reasoning_effort_code")
            run_002(model, effort)
            if step.mode == "tool_assisted":
                max_turns = max_turns or defaults.get("default_max_turns") or DEFAULT_MAX_TURNS
            cur.execute(
                """INSERT INTO application.run
                       (tenant_id, project_id, project_workflow, workflow_execution_mode, base_project_version,
                        prompt_version_id, extra_instructions, agent_model_id, reasoning_effort_code, max_turns,
                        run_request_document, started_by_principal_id)
                   SELECT %s, %s, %s, %s, project_version, %s, %s, %s, %s, %s, %s, %s
                     FROM project.project WHERE project_id = %s
                   RETURNING run_id""",
                (tenant_id, project_id, workflow, step.mode, prompt["prompt_version_id"],
                 (extra_instructions or "").strip() or None, model["agent_model_id"], effort,
                 max_turns if step.mode == "tool_assisted" else None, Jsonb(request), principal_id, project_id),
            )
            run_id = cur.fetchone()["run_id"]
            log(cur, run_id, "start", "completed", f"{step.title} with {model['agent_model_display_name']}"
                + (f", effort {effort}" if effort else "") + ".")
    return run_id


def execute(conn, run_id, credentials):
    """Do a saved Run, start to end. Called once, in the background, with a connection of its own."""
    with conn.cursor(row_factory=dict_row) as cur:
        run = _load(cur, run_id)
        step = steps()[run["project_workflow"]]
        try:
            documents, answered = _do(cur, run, step, credentials)
        except Exception as error:  # the Run fails with the reason; nothing is saved to the project
            finish(cur, run_id, "failed", message=str(error) or type(error).__name__)
            return
        if not answered:
            finish(cur, run_id, "failed", message="No item got an answer, so there is no draft.")
            return
        change_set_id = None
        if documents:
            log(cur, run_id, "save_draft", "started")
            change_set_id = change_sets.save_draft(
                conn, run["project_id"], run["started_by_principal_id"], documents,
                f"{step.title}: run {run_id}", "ai_run", run["base_project_version"])
            counts = ", ".join(f"{len(records)} {part}" for part, records in documents.items())
            log(cur, run_id, "save_draft", "completed", f"Draft {change_set_id}: {counts}.")
            found = change_sets.validate(conn, run["started_by_principal_id"], change_set_id)
            blocking = sum(p.level == "blocks_apply" for p in found)
            log(cur, run_id, "check_draft", "completed",
                f"{blocking} problems block Apply, {len(found) - blocking} warnings." if found else "No problems.")
        else:
            log(cur, run_id, "save_draft", "completed", "Nothing to change: no draft.")
        finish(cur, run_id, run.get("stop_status") or "completed", change_set_id, run.get("stop_message"))


def _do(cur, run, step, credentials):
    """Prepare, call the AI, and turn the answers into draft documents. Returns (documents, items answered)."""
    run_id = run["run_id"]
    model = _model(cur, run["agent_model_id"])
    ai_model = ai.Model(model["agent_model_id"], model["agent_provider_code"], model["agent_model_name"],
                        model["input_usd_per_million"], model["cached_input_usd_per_million"],
                        model["output_usd_per_million"])
    client = ai.client(credentials, ai_model)
    prompt = prompts.version(cur, run["prompt_version_id"])

    log(cur, run_id, "prepare_context", "started")
    items = step.items(cur, run["project_id"], run["run_request_document"])
    prepared, lines = step.prepare(cur, run, items)
    for line in lines:
        log(cur, run_id, "prepare_context", "completed", line)
    log(cur, run_id, "prepare_context", "completed", f"{len(prepared)} of {len(items)} items to run.")

    def call(input_items, **kwargs):
        response, used = ai.call(client, ai_model, run["reasoning_effort_code"], input_items, **kwargs)
        _save_usage(cur, run_id, used)
        return response

    if step.mode == "tool_assisted":
        documents, stop = step.run_tools(cur, run, prompt, prepared, call, lambda *a: log(cur, run_id, *a))
        if stop:
            run["stop_status"], run["stop_message"] = "stopped", stop
        return documents, 1

    log(cur, run_id, "build_prompt", "completed", f"Prompt version {prompt['prompt_version_id']}.")
    messages = {label: prompts.build(prompt, step.inputs, inputs, run["extra_instructions"])
                for label, inputs in prepared.items()}
    log(cur, run_id, "ai_call", "started", f"{len(messages)} calls.")

    def one(label):
        system, user = messages[label]
        try:
            response, used = ai.call(client, ai_model, run["reasoning_effort_code"],
                                     [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                     schema=step.answer)
            return label, used, ai.answer_json(response), None
        except ai.AIError as error:
            return label, None, None, str(error)

    documents, answered = {}, 0
    with ThreadPoolExecutor(PARALLEL_CALLS) as pool:
        for label, used, answer, error in pool.map(one, messages):
            if used:
                _save_usage(cur, run_id, used)
            if error:
                log(cur, run_id, "ai_call", "failed", f"{label}: skipped. {error}")  # RUN-006
                continue
            answered += 1
            found, notes = step.records(cur, run, label, answer)
            for note in notes:
                log(cur, run_id, "ai_call", "completed", f"{label}: {note}")
            for part, records in found.items():
                documents.setdefault(part, []).extend(records)
    log(cur, run_id, "ai_call", "completed", f"{answered} of {len(messages)} answered.")
    return documents, answered


def get_run(conn, principal_id, run_id, via_mcp=False):
    """One Run: its status, settings, the draft it made, its log and what its AI calls cost."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT r.run_id, r.project_id, r.tenant_id, r.project_workflow, r.workflow_execution_mode, r.run_status,
                      r.base_project_version, r.prompt_version_id, r.extra_instructions, m.agent_model_display_name,
                      r.reasoning_effort_code, r.max_turns, r.run_request_document, r.started_time,
                      r.completed_time, r.failure_message, r.project_change_set_id, cs.project_change_set_status,
                      p.principal_display_name AS started_by_display_name
                 FROM application.run AS r
                 LEFT JOIN reference.agent_model AS m USING (agent_model_id)
                 LEFT JOIN application.project_change_set AS cs USING (project_change_set_id)
                 JOIN security.principal AS p ON p.principal_id = r.started_by_principal_id
                WHERE r.run_id = %s""",
            (run_id,),
        )
        run = cur.fetchone()
        if run is None:
            raise NotFound("ACCESS-001", "Run not found.")
        require(conn, principal_id, run.pop("tenant_id"), READ, project_id=run["project_id"], via_mcp=via_mcp)
        cur.execute(
            """SELECT run_event_stage, run_event_status, run_event_message, created_time
                 FROM application.run_event WHERE run_id = %s ORDER BY run_event_id""",
            (run_id,),
        )
        run["events"] = cur.fetchall()
        cur.execute(
            """SELECT count(*) AS calls, coalesce(sum(input_tokens), 0) AS input_tokens,
                      coalesce(sum(cached_input_tokens), 0) AS cached_input_tokens,
                      coalesce(sum(output_tokens), 0) AS output_tokens, sum(cost_usd) AS cost_usd
                 FROM application.run_model_request WHERE run_id = %s""",
            (run_id,),
        )
        run["usage"] = cur.fetchone()
    return run


def list_runs(conn, principal_id, project_id, limit=20, via_mcp=False):
    """The project's latest Runs, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM project.project WHERE project_id = %s", (project_id,))
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        require(conn, principal_id, project["tenant_id"], READ, project_id=project_id, via_mcp=via_mcp)
        cur.execute(
            """SELECT r.run_id, r.project_workflow, r.run_status, r.started_time, r.completed_time, r.failure_message,
                      r.project_change_set_id, cs.project_change_set_status, m.agent_model_display_name,
                      (SELECT sum(cost_usd) FROM application.run_model_request AS q WHERE q.run_id = r.run_id) AS cost_usd
                 FROM application.run AS r
                 LEFT JOIN reference.agent_model AS m USING (agent_model_id)
                 LEFT JOIN application.project_change_set AS cs USING (project_change_set_id)
                WHERE r.project_id = %s ORDER BY r.run_id DESC LIMIT %s""",
            (project_id, limit),
        )
        return cur.fetchall()


def list_models(conn):
    """The active models and the reasoning efforts each allows, for the Run page."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT m.agent_model_id, m.agent_model_display_name, p.agent_provider_code, m.reasoning_effort_codes
                 FROM reference.agent_model AS m JOIN reference.agent_provider AS p USING (agent_provider_id)
                WHERE m.is_active ORDER BY p.agent_provider_code, m.agent_model_display_name""")
        return cur.fetchall()


# --- The checks, one per rule ----------------------------------------------------------------------------------------
# RUN-001 (the Run's tenant is its project's) holds by construction: start_run takes the tenant from the project.


def run_002(model, effort):
    """RUN-002: a Run's reasoning effort is one its model allows, or none."""
    if effort and effort not in (model["reasoning_effort_codes"] or []):
        allowed = ", ".join(model["reasoning_effort_codes"]) or "none"
        raise Refused("RUN-002", f"{model['agent_model_display_name']} allows these efforts: {allowed}. "
                                 f"You asked for {effort}.")


def run_003(cur, tenant_id):
    """RUN-003: one Run at a time in a tenant. A Run whose log has not moved for 30 minutes is marked failed first."""
    cur.execute(
        """UPDATE application.run AS r
              SET run_status = 'failed', completed_time = CURRENT_TIMESTAMP,
                  failure_message = 'Its log did not move for 30 minutes, so its process has stopped.'
            WHERE r.tenant_id = %s AND r.run_status = 'running'
              AND greatest(r.started_time, (SELECT max(e.created_time) FROM application.run_event AS e
                                             WHERE e.run_id = r.run_id))
                  < CURRENT_TIMESTAMP - make_interval(mins => %s)""",
        (tenant_id, STALE_MINUTES),
    )
    cur.execute(
        """SELECT r.project_workflow, p.principal_display_name FROM application.run AS r
             JOIN security.principal AS p ON p.principal_id = r.started_by_principal_id
            WHERE r.tenant_id = %s AND r.run_status = 'running'""",
        (tenant_id,),
    )
    running = cur.fetchone()
    if running:
        raise Refused("RUN-003", f"{running['principal_display_name']}'s {running['project_workflow']} Run is running "
                                 "in this tenant. Wait for it to end.")


def run_004(prompt, workflow):
    """RUN-004: a Run's prompt version belongs to its step."""
    if prompt is None:
        raise Refused("RUN-004", f"There is no prompt for {workflow}.")
    if prompt["project_workflow"] != workflow:
        raise Refused("RUN-004", f"That prompt is for {prompt['project_workflow']}, not {workflow}.")


def run_005(missing):
    """RUN-005: a Run's picks exist, are switched on and have what the step needs. `missing` says what is not."""
    if missing:
        raise Refused("RUN-005", missing)


# --- Helpers ---------------------------------------------------------------------------------------------------------


def log(cur, run_id, stage, status, message=None):
    cur.execute(
        """INSERT INTO application.run_event (run_id, run_event_stage, run_event_status, run_event_message)
           VALUES (%s, %s, %s, %s)""",
        (run_id, stage, status, message),
    )


def finish(cur, run_id, status, change_set_id=None, message=None):
    cur.execute(
        """UPDATE application.run SET run_status = %s, completed_time = CURRENT_TIMESTAMP, failure_message = %s,
                  project_change_set_id = %s, updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
            WHERE run_id = %s""",
        (status, message, change_set_id, run_id),
    )
    log(cur, run_id, "end", "failed" if status == "failed" else "completed", message or status.capitalize() + ".")


def _save_usage(cur, run_id, used):
    cur.execute(
        """INSERT INTO application.run_model_request
               (run_id, started_time, completed_time, input_tokens, cached_input_tokens, output_tokens,
                reasoning_output_tokens, cost_usd)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (run_id, used.started_time, used.completed_time, used.input_tokens, used.cached_input_tokens,
         used.output_tokens, used.reasoning_output_tokens, used.cost_usd),
    )


def _load(cur, run_id):
    cur.execute("SELECT * FROM application.run WHERE run_id = %s", (run_id,))
    return cur.fetchone()


def _model(cur, agent_model_id):
    """The model asked for, or with none asked for, the first active model core/ can call (core/ai.py)."""
    cur.execute(
        """SELECT m.*, p.agent_provider_code FROM reference.agent_model AS m
             JOIN reference.agent_provider AS p USING (agent_provider_id)
            WHERE m.is_active AND (m.agent_model_id = %(id)s OR (%(id)s::bigint IS NULL
                                                               AND p.agent_provider_code = ANY(%(callable)s)))
            ORDER BY array_position(%(callable)s, p.agent_provider_code::text), m.agent_model_id LIMIT 1""",
        {"id": agent_model_id, "callable": list(ai.PROVIDERS)},
    )
    model = cur.fetchone()
    if model is None:
        raise Refused("RUN-002", "No active AI model is set up.")
    return model

