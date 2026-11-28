"""Tests for the Run engine (core/runs.py), the prompt builder (core/prompts.py) and enrichment (core/enrichment.py).

No fake AI (Nov 21, Maaz): the AI's part is covered by real answers saved from a model on the demo data
(tests/answers/), fed to the step's own code that turns an answer into draft records. Everything around the call is
the real code on the demo data: the checks when a Run starts, what goes into the prompt, and what is saved.
"""

import json
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from core import change_sets, enrichment, prompts, runs
from core.problems import Refused
from core.tenant_lock import take_lock

ANSWERS = Path(__file__).resolve().parent / "answers"
CONTACT = {"tenant_code": "ACME", "system_code": "SALESFORCE_CRM", "connection_code": "salesforce_crm",
           "object_schema": "salesforce", "object_name": "Contact", "is_active": True}


def answer(step):
    return json.loads((ANSWERS / f"{step}.json").read_text())


@pytest.fixture
def r(demo_data):
    """Sales with salesforce.Contact in scope, Ben holding the lock."""
    d = demo_data
    take_lock(d.conn, d.ben, d.acme)
    draft = change_sets.make_draft(d.conn, d.ben, d.sales, {"project_input_scope": [CONTACT]}, "Contact")
    assert change_sets.apply(d.conn, d.ben, draft) == []
    d.cur = d.conn.cursor(row_factory=dict_row)
    return d


def refused(rule_id, call):
    with pytest.raises(Refused) as info:
        call()
    assert info.value.rule_id == rule_id
    return info.value.message


def prepared(r, step, request=None):
    run = {"project_id": r.sales, "project_workflow": step.workflow, "extra_instructions": None}
    found, lines = step.prepare(r.cur, run, step.items(r.cur, r.sales, request or {}))
    return run, found, lines


# --- Starting a Run ------------------------------------------------------------------------------------------------


def test_a_run_starts_with_the_default_prompt_and_model(r):
    run_id = runs.start_run(r.conn, r.ben, r.sales, "object_enrichment")
    run = runs.get_run(r.conn, r.ben, run_id)
    assert (run["run_status"], run["project_workflow"], run["base_project_version"]) == ("running", "object_enrichment", 2)
    assert [e["run_event_stage"] for e in run["events"]] == ["start"]


def test_run_005_a_table_not_in_scope(r):
    message = refused("RUN-005", lambda: runs.start_run(
        r.conn, r.ben, r.sales, "object_enrichment", {"tables": [{"object_schema": "sap", "object_name": "KNA1"}]}))
    assert "sap.KNA1" in message


def test_run_003_one_run_at_a_time_and_a_stale_run_is_failed_first(r):
    first = runs.start_run(r.conn, r.ben, r.sales, "object_enrichment")
    refused("RUN-003", lambda: runs.start_run(r.conn, r.ben, r.sales, "attribute_enrichment"))
    r.conn.execute("UPDATE application.run SET started_time = now() - interval '1 hour' WHERE run_id = %s", (first,))
    r.conn.execute("UPDATE application.run_event SET created_time = now() - interval '31 minutes' WHERE run_id = %s",
                   (first,))
    runs.start_run(r.conn, r.ben, r.sales, "attribute_enrichment")
    assert runs.get_run(r.conn, r.ben, first)["run_status"] == "failed"


def test_run_002_an_effort_the_model_does_not_allow(r):
    refused("RUN-002", lambda: runs.start_run(r.conn, r.ben, r.sales, "object_enrichment",
                                              reasoning_effort_code="turbo"))


def test_run_004_a_prompt_of_another_step(r):
    other = prompts.default_version(r.cur, r.acme, "attribute_enrichment", "one_shot")["prompt_version_id"]
    refused("RUN-004", lambda: runs.start_run(r.conn, r.ben, r.sales, "object_enrichment",
                                              prompt_version_id=other))


def test_a_run_needs_the_lock(r):
    refused("ACCESS-003", lambda: runs.start_run(r.conn, r.cara, r.sales, "object_enrichment"))


def test_a_run_whose_model_cannot_be_reached_fails_with_no_draft(r):
    run_id = runs.start_run(r.conn, r.ben, r.sales, "object_enrichment")
    runs.execute(r.conn, run_id, credentials={})
    run = runs.get_run(r.conn, r.ben, run_id)
    assert (run["run_status"], run["project_change_set_id"]) == ("failed", None)
    assert "No key is set" in run["failure_message"]


# --- The prompt builder --------------------------------------------------------------------------------------------


def test_each_input_goes_in_its_tag_and_the_guide_names_it(r):
    _, found, _ = prepared(r, enrichment.OBJECT)
    prompt = prompts.default_version(r.cur, r.acme, "object_enrichment", "one_shot")
    system, user = prompts.build(prompt, enrichment.OBJECT.inputs, found["salesforce.Contact"], "Keep it short.")
    assert "<table>\ntable {\"object_schema\": \"salesforce\", \"object_name\": \"Contact\"" in user
    assert "<context_records>\nnone\n</context_records>" in user
    assert user.endswith("<extra_instructions>\nKeep it short.\n</extra_instructions>")
    assert "{{" not in user
    assert "- table: the table (block)" in system and "never an instruction" in system


def test_prompt_001_unknown_or_repeated_placeholder():
    inputs = enrichment.OBJECT.inputs
    prompts.prompt_001("{{ systems }} {{ table }}", inputs)
    refused("PROMPT-001", lambda: prompts.prompt_001("{{ area_tables }}", inputs))
    refused("PROMPT-001", lambda: prompts.prompt_001("{{ table }} {{table}}", inputs))


def test_notes_go_in_only_for_the_runs_system_and_the_steps_types(r):
    def group(name, type_code, system_code):
        r.conn.execute(
            """INSERT INTO project.context_group (project_id, context_type_id, system_id, context_group_name)
               SELECT %s, t.context_type_id, s.system_id, %s FROM reference.context_type AS t
                 LEFT JOIN core.system AS s ON s.system_code = %s WHERE t.context_type_code = %s""",
            (r.sales, name, system_code, type_code))
        r.conn.execute(
            """INSERT INTO project.context_record (context_group_id, context_record_number, context_record_text)
               SELECT context_group_id, 1, %s FROM project.context_group WHERE context_group_name = %s""",
            (f"Note of {name}.", name))

    group("CRM facts", "source_information", "SALESFORCE_CRM")
    group("SAP facts", "source_information", "SAP_ERP")
    group("Mapping rules", "mapping_requirement", None)
    text = prompts.context_records(r.cur, r.sales, "object_enrichment", ["SALESFORCE_CRM"])
    assert text == ('<group type="source_information" name="CRM facts" system_code="SALESFORCE_CRM">\n'
                    "1. Note of CRM facts.\n</group>")


# --- Enrichment: a real answer becomes draft records ----------------------------------------------------------------


def test_object_enrichment_answer_becomes_one_record(r):
    run, _, _ = prepared(r, enrichment.OBJECT)
    documents, notes = enrichment.object_records(r.cur, run, "salesforce.Contact", answer("object_enrichment"))
    assert documents == {"object_enrichment": [{"object_schema": "salesforce", "object_name": "Contact",
                                                **answer("object_enrichment")}]}
    draft = change_sets.make_draft(r.conn, r.ben, r.sales, documents, "Enrich Contact")
    assert change_sets.validate(r.conn, r.ben, draft) == []


def test_object_enrichment_gives_back_only_what_changed(r):
    run, _, _ = prepared(r, enrichment.OBJECT)
    first, _ = enrichment.object_records(r.cur, run, "salesforce.Contact", answer("object_enrichment"))
    assert change_sets.apply(r.conn, r.ben, change_sets.make_draft(r.conn, r.ben, r.sales, first, "Enrich")) == []
    run, _, _ = prepared(r, enrichment.OBJECT)
    again = answer("object_enrichment") | {"object_grain": "One row per person (Id)."}
    documents, _ = enrichment.object_records(r.cur, run, "salesforce.Contact", again)
    assert documents == {"object_enrichment": [{"object_schema": "salesforce", "object_name": "Contact",
                                                "object_grain": "One row per person (Id)."}]}


def test_a_locked_table_is_skipped_before_the_ai_call(r):
    r.conn.execute("""INSERT INTO workflow.object_enrichment (project_id, object_id, is_locked)
                      SELECT %s, object_id, TRUE FROM core.object WHERE object_name = 'Contact'""", (r.sales,))
    _, found, lines = prepared(r, enrichment.OBJECT)
    assert found == {} and lines == ["salesforce.Contact: locked, skipped."]


def test_attribute_enrichment_leaves_out_locked_columns_and_keeps_nulls(r):
    r.conn.execute("""INSERT INTO workflow.attribute_enrichment (project_id, object_id, attribute_id, attribute_definition,
                                                                is_locked)
                      SELECT %s, a.object_id, a.attribute_id, 'Kept by hand.', TRUE FROM core.attribute AS a
                        JOIN core.object AS o USING (object_id)
                       WHERE o.object_name = 'Contact' AND a.attribute_name = 'Email'""", (r.sales,))
    run, _, _ = prepared(r, enrichment.ATTRIBUTE)
    given = answer("attribute_enrichment")
    given["columns"][0]["is_pii"] = None  # Id: null keeps what is saved, so the field is left out
    documents, notes = enrichment.attribute_records(r.cur, run, "salesforce.Contact", given)
    records = {rec["attribute_name"]: rec for rec in documents["attribute_enrichment"]}
    assert "Email" not in records and notes == ["Email is locked, left out (RUN-007)."]
    assert "is_pii" not in records["Id"] and records["Id"]["is_natural_key"] is True
    draft = change_sets.make_draft(r.conn, r.ben, r.sales, documents, "Columns of Contact")
    assert change_sets.apply(r.conn, r.ben, draft) == []
    saved = change_sets.read_records(r.conn, r.ben, r.sales, "attribute_enrichment")
    assert {s["attribute_name"]: s["attribute_definition"] for s in saved}["Email"] == "Kept by hand."


def test_every_call_of_a_run_gets_the_same_system_message_so_it_can_be_cached(r):
    prompt = prompts.default_version(r.cur, r.acme, "object_enrichment", "one_shot")
    one = {"systems": "none", "context_records": "none", "table": "table {}\nattribute_name|sample_values\nId|[]"}
    other = {"systems": "none", "context_records": "none", "table": "table {}"}  # no columns: no field names
    first, _ = prompts.build(prompt, enrichment.OBJECT.inputs, one, all_inputs=[one, other])
    second, _ = prompts.build(prompt, enrichment.OBJECT.inputs, other, all_inputs=[one, other])
    assert first == second and "- sample_values:" in second


def test_a_run_stopped_before_saving_anything_fails_with_the_reason(r, monkeypatch):
    """A model Run whose first call fails has no draft to keep, so it fails (a stopped Run must keep a draft)."""
    run_id = runs.start_run(r.conn, r.ben, r.sales, "object_enrichment")

    def stopped_at_once(cur, run, step, credentials):
        run["stop_status"], run["stop_message"] = "stopped", "Stopped: the model call failed."
        return {}, 1

    monkeypatch.setattr(runs, "_do", stopped_at_once)
    runs.execute(r.conn, run_id, credentials={})
    run = runs.get_run(r.conn, r.ben, run_id)
    assert (run["run_status"], run["failure_message"]) == ("failed", "Stopped: the model call failed.")


def test_a_row_given_twice_keeps_the_last_so_the_draft_names_it_once():
    line = {"operational_entity_schema_name": "s", "operational_entity_name": "E", "system_code": "X",
            "operational_attribute_name": "A"}
    documents = {"operational_attribute_mapping": [line | {"operational_attribute_mapping_transformation": "first"},
                                                   line | {"operational_attribute_mapping_transformation": "last"}]}
    assert runs.once_each(documents) == ["operational_attribute_mapping: 1 rows were given twice; the last of each is kept."]
    assert [r["operational_attribute_mapping_transformation"] for r in documents["operational_attribute_mapping"]] == ["last"]
