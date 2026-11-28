"""Tests for the Silver and Gold model Runs (core/models.py): the ledger, its tools and the draft it becomes, and the
model rules (OPERATIONAL-*, PROJECT-001).

tests/answers/operational.json holds the real write tool calls a model made building the demo area "Customer
accounts". They are replayed through the same tool code a Run uses; the AI's own part is not faked.
"""

import json
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from core import change_sets, models
from core.tenant_lock import take_lock

ANSWERS = Path(__file__).resolve().parent / "answers"
AREA_TABLES = {"Customer accounts": ("Account", "Contact", "KNA1", "KNVV"), "Workforce": ("Worker", "Position")}


@pytest.fixture
def s(demo_data):
    """Sales with every ACME Source table in scope and two subject areas; Ben holds the lock."""
    d = demo_data
    take_lock(d.conn, d.ben, d.acme)
    rows = d.conn.execute(
        """SELECT ct.tenant_code, sy.system_code, c.connection_code, o.object_schema, o.object_name
             FROM core.object AS o JOIN core.connection AS c USING (connection_id)
             JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id JOIN core.system AS sy ON sy.system_id = c.system_id
             JOIN reference.zone AS z ON z.zone_id = o.zone_id
            WHERE ct.tenant_code = 'ACME' AND lower(z.zone_code) = 'source' AND o.is_active""").fetchall()
    scope = [dict(zip(("tenant_code", "system_code", "connection_code", "object_schema", "object_name"), r)) for r in rows]
    schemas = {r["object_name"]: r["object_schema"] for r in scope}
    areas = [{"subject_area_name": name, "subject_area_definition": name} for name in AREA_TABLES]
    tables = [{"subject_area_name": name, "object_schema": schemas[t], "object_name": t}
              for name, ts in AREA_TABLES.items() for t in ts]
    assert apply(d, {"project_input_scope": scope, "subject_area": areas, "subject_area_table": tables}) == []
    d.cur = d.conn.cursor(row_factory=dict_row)
    return d


def apply(d, documents):
    draft = change_sets.make_draft(d.conn, d.ben, d.sales, documents, "x")
    return [str(p) for p in change_sets.apply(d.conn, d.ben, draft) if p.level == "blocks_apply"]


def ledger_for(s, area, workflow="operational"):
    run = {"project_id": s.sales, "project_workflow": workflow, "run_request_document": {"subject_area_name": area}}
    step = models.STEPS[workflow]
    prepared, _ = step.prepare(s.cur, run, step.items(s.cur, s.sales, run["run_request_document"]))
    return run["ctx"], prepared[area]


def tool(ctx, name, arguments):
    """A tool call as the AI makes it: arguments as JSON text (a string is sent as it is, like a cut-off reply)."""
    return json.loads(models.call_tool(ctx, name, arguments if isinstance(arguments, str) else json.dumps(arguments)))


def replay(ctx):
    answers = [tool(ctx, c["name"], c["arguments"]) for c in json.loads((ANSWERS / "operational.json").read_text())]
    assert not [a for a in answers if "error" in a], answers
    return models.to_documents(ctx["ledger"])


def test_real_tool_calls_become_a_draft_that_keeps_every_model_rule(s):
    ctx, inputs = ledger_for(s, "Customer accounts")
    assert inputs["existing_operational_entities"] == "none"
    documents = replay(ctx)
    assert {part: len(records) for part, records in documents.items()} == {
        "operational_entity": 5, "operational_attribute": 33, "operational_entity_source": 7,
        "operational_attribute_source": 31, "operational_link": 4}
    assert apply(s, documents) == []
    saved = change_sets.read_records(s.conn, s.ben, s.sales, "operational_attribute")
    account = [a["operational_attribute_name"] for a in saved if a["operational_entity_name"] == "Account"]
    assert account[:3] == ["AccountID", "CustomerNumber", "SourceAccountID"]  # in the order saved, from 1
    assert [a["operational_attribute_ordinal_position"] for a in saved if a["operational_entity_name"] == "Account"][:3] == [1, 2, 3]


def test_a_rerun_shows_the_saved_entities_in_full_and_drafts_only_what_changes(s):
    ctx, _ = ledger_for(s, "Customer accounts")
    assert apply(s, replay(ctx)) == []
    ctx, inputs = ledger_for(s, "Customer accounts")
    assert '"operational_entity_name": "Account"' in inputs["existing_operational_entities"]
    answer = tool(ctx, "save_attributes", {
        "operational_entity_schema_name": "silver_sales", "operational_entity_name": "Account", "attributes": [
            {"operational_attribute_name": "AccountName", "operational_attribute_definition": "The company's name.",
             "operational_attribute_data_type": "STRING", "is_nullable": True, "is_surrogate_key": False,
             "is_natural_key": False, "link_to": None,
             "sources": [{"object_schema": "salesforce", "object_name": "Account", "attribute_name": "Name",
                          "operational_attribute_source_note": "As is."}]}]})
    assert answer == {"saved": ["AccountName"]}
    documents = models.to_documents(ctx["ledger"])
    changed = documents["operational_attribute"]
    assert [(a["operational_attribute_name"], a.get("operational_attribute_definition")) for a in changed] == [
        ("AccountName", "The company's name.")]
    assert "operational_entity" not in documents


def test_writes_are_refused_for_a_locked_entity_or_one_not_read_in_full(s):
    ctx, _ = ledger_for(s, "Customer accounts")
    assert apply(s, replay(ctx)) == []
    s.conn.execute("UPDATE workflow.operational_entity SET is_locked = TRUE WHERE operational_entity_name = 'Contact'")
    ctx, _ = ledger_for(s, "Workforce")  # Account and Contact are not in this area, so not shown in full
    remove = {"operational_entity_schema_name": "silver_sales", "operational_entity_name": "Account"}
    assert "get_entity_details first" in tool(ctx, "remove_entity", remove)["error"]
    tool(ctx, "get_entity_details", {"model": "operational", "entity_schema_name": "silver_sales", "entity_name": "Account"})
    assert tool(ctx, "remove_entity", remove) == {"switched_off": "silver_sales.Account"}
    contact = {"operational_entity_schema_name": "silver_people", "operational_entity_name": "Contact"}
    tool(ctx, "get_entity_details", {"model": "operational", "entity_schema_name": "silver_people", "entity_name": "Contact"})
    assert tool(ctx, "remove_entity", contact) == {"error": "Contact is locked"}


def test_tool_errors_name_what_is_wrong_and_change_nothing(s):
    ctx, _ = ledger_for(s, "Workforce")
    entity = {"operational_entity_schema_name": "silver_people", "operational_entity_name": "Worker",
              "operational_entity_type_code": "core", "operational_entity_definition": "A worker.",
              "operational_entity_grain": "One row per worker.", "is_merged": False,
              "sources": [{"object_schema": "workday", "object_name": "Wrker", "operational_entity_source_note": None}]}
    assert tool(ctx, "save_entity", entity) == {"error": "No scope table workday.wrker"}
    assert tool(ctx, "save_entity", entity | {"operational_entity_schema_name": "gold_sales"})["error"].startswith(
        "gold_sales is not one of the project's Silver model schemas")
    assert tool(ctx, "save_attributes", "{not json") == {"error": "Cut off: save fewer attributes per call"}
    assert models.to_documents(ctx["ledger"]) == {}


def test_operational_005_and_006_an_entity_without_one_surrogate_key_or_a_natural_key(s):
    problems = apply(s, {
        "operational_entity": [{"operational_entity_schema_name": "silver_people", "operational_entity_name": "Worker",
                                "operational_entity_type_code": "core"}],
        "operational_attribute": [{"operational_entity_schema_name": "silver_people", "operational_entity_name": "Worker",
                                   "operational_attribute_name": "WorkerName", "operational_attribute_data_type": "TEXT",
                                   "operational_attribute_ordinal_position": 1}]})
    assert sorted(p.split(":")[0] for p in problems) == ["OPERATIONAL-005", "OPERATIONAL-006"]


def test_real_gold_tool_calls_build_on_the_silver_model(s):
    ctx, _ = ledger_for(s, "Customer accounts")
    assert apply(s, replay(ctx)) == []
    ctx, inputs = ledger_for(s, "Customer accounts", "dimensional")
    assert inputs["operational_entities"].startswith("entity {")  # Silver entities as blocks
    calls = json.loads((ANSWERS / "dimensional.json").read_text())
    answers = [tool(ctx, c["name"], c["arguments"]) for c in calls]
    assert not [a for a in answers if "error" in a], answers
    documents = models.to_documents(ctx["ledger"])
    assert apply(s, documents) == []
    saved = change_sets.read_records(s.conn, s.ben, s.sales, "dimensional_entity")
    assert all(e["dimensional_entity_type"] in ("fact", "dimension") for e in saved) and saved


def test_load_order_puts_parents_first(s):
    from core import load_order
    ctx, _ = ledger_for(s, "Customer accounts")
    assert apply(s, replay(ctx)) == []
    change_set_id, loop = load_order.make_draft(s.conn, s.ben, s.sales, "operational")
    assert loop == [] and change_sets.apply(s.conn, s.ben, change_set_id) == []
    order = {e["operational_entity_name"]: e["operational_entity_dependency_order"]
             for e in change_sets.read_records(s.conn, s.ben, s.sales, "operational_entity")}
    assert order["User"] < order["Account"] < order["Contact"] and order["Account"] < order["CustomerSalesArea"]
    assert load_order.make_draft(s.conn, s.ben, s.sales, "operational") == (None, [])  # nothing changes now
