"""Tests for Silver mapping (core/mapping.py), code (core/code.py) and validation (core/validation.py), with the
MAPPING, CODE and VALIDATION rules.

The demo Silver model comes from replaying the real tool calls of tests/answers/operational.json (see test_models.py).
The answers for Account from SAP are real ones a model gave on that model (tests/answers/operational_*.json).
"""

import json
from pathlib import Path

from core import change_sets, runs
from test_models import apply, ledger_for, replay, s  # noqa: F401  (s is the fixture)

ANSWERS = Path(__file__).resolve().parent / "answers"
ACCOUNT = {"operational_entity_schema_name": "silver_sales", "operational_entity_name": "Account"}


def answer(workflow):
    return json.loads((ANSWERS / f"{workflow}.json").read_text())


def step_run(s, workflow, request):
    step = runs.steps()[workflow]
    run = {"project_id": s.sales, "project_workflow": workflow, "run_request_document": request, "extra_instructions": None}
    prepared, _ = step.prepare(s.cur, run, step.items(s.cur, s.sales, request))
    [(label, inputs)] = prepared.items()
    return step, run, label, inputs


def silver(s):
    ctx, _ = ledger_for(s, "Customer accounts")
    assert apply(s, replay(ctx)) == []


def mapped(s):
    silver(s)
    step, run, label, inputs = step_run(s, "operational_mapping", {"mappings": [ACCOUNT | {"system_code": "SAP_ERP"}]})
    documents, notes = step.records(s.cur, run, label, answer("operational_mapping"))
    assert apply(s, documents) == []
    return documents


def test_mapping_lists_only_this_systems_sources_with_aliases(s):
    silver(s)
    _, _, label, inputs = step_run(s, "operational_mapping", {"mappings": [ACCOUNT | {"system_code": "SAP_ERP"}]})
    assert label == "silver_sales.Account / SAP_ERP"
    assert 'table {"alias": "k", "role": "source", "object_schema": "sap", "object_name": "KNA1"' in inputs["mapping_tables"]
    assert "salesforce" not in inputs["mapping_tables"].split("\n")[0]
    assert "AccountID|BIGINT|true|false|false|[]|null|null|false|null|false" in inputs["target_entity"]


def test_a_real_mapping_answer_is_saved_with_its_table_list_and_every_line(s):
    documents = mapped(s)
    part = documents["operational_object_mapping"][0]
    assert part["operational_object_mapping_tables"][0] == {"alias": "k", "role": "source", "object_schema": "sap",
                                                            "object_name": "KNA1"}
    lines = change_sets.read_records(s.conn, s.ben, s.sales, "operational_attribute_mapping")
    assert len(lines) == len(answer("operational_mapping")["attributes"])
    found = change_sets.validate(s.conn, s.ben, change_sets.make_draft(s.conn, s.ben, s.sales, documents, "again"))
    assert [p.rule_id for p in found if p.rule_id.startswith("MAPPING")] == []  # every attribute has a line


def test_mapping_003_warns_about_an_attribute_without_a_line(s):
    documents = mapped(s)
    line = documents["operational_attribute_mapping"][0] | {"is_active": False}
    draft = change_sets.make_draft(s.conn, s.ben, s.sales, {"operational_attribute_mapping": [line]}, "drop a line")
    found = change_sets.validate(s.conn, s.ben, draft)
    assert [(p.rule_id, p.level) for p in found] == [("MAPPING-003", "warning")]


def test_the_starter_sql_carries_every_mapping_field(s):
    mapped(s)
    _, _, label, inputs = step_run(s, "operational_code", {"code_files": [ACCOUNT]})
    starter = inputs["starter_sql"]
    assert label == "account_sap_erp.sql"
    assert "CREATE OR REPLACE TEMPORARY VIEW temp_account_sap_erp AS (" in starter
    for line in answer("operational_mapping")["attributes"]:
        assert line["operational_attribute_mapping_transformation"] in starter
    assert starter.index("sys.SystemID AS SourceSystemID") > starter.index("AS UserID")
    assert " AS AccountID," not in starter  # the surrogate key: the load fills it


def test_a_real_code_answer_keeps_the_code_rules_and_a_writing_statement_is_refused(s):
    mapped(s)
    step, run, label, _ = step_run(s, "operational_code", {"code_files": [ACCOUNT]})
    documents, _ = step.records(s.cur, run, label, answer("operational_code"))
    assert documents["operational_code_system"] == [ACCOUNT | {"operational_file_name": label, "system_code": "SAP_ERP",
                                                               "is_active": True}]
    assert apply(s, documents) == []
    bad = documents["operational_code"][0] | {"operational_code_text": "DELETE FROM silver_sales.Account; SELECT 1"}
    found = change_sets.validate(s.conn, s.ben, change_sets.make_draft(s.conn, s.ben, s.sales, {"operational_code": [bad]}, "x"))
    assert [p.rule_id for p in found if p.level == "blocks_apply"] == ["CODE-002"]


def test_a_real_validation_answer_gets_the_fixed_pass_condition(s):
    mapped(s)
    step, run, label, inputs = step_run(s, "operational_validation", {"mappings": [ACCOUNT]})
    assert '"sql_name": "silver_sales.Account"' in inputs["target_entity"]
    documents, _ = step.records(s.cur, run, label, answer("operational_validation"))
    checks = documents["operational_validation_check"]
    assert len(checks) == len(answer("operational_validation")["checks"])
    assert {(c["validation_result_data_type"], c["validation_comparison_operator"], c["validation_comparison_value"])
            for c in checks} == {("integer", "equal", 0)}
    draft = change_sets.make_draft(s.conn, s.ben, s.sales, documents, "checks")
    assert [p.rule_id for p in change_sets.validate(s.conn, s.ben, draft) if p.level == "blocks_apply"] == []


def test_validation_001_a_pass_condition_that_does_not_fit(s):
    mapped(s)
    step, run, label, _ = step_run(s, "operational_validation", {"mappings": [ACCOUNT]})
    documents, _ = step.records(s.cur, run, label, answer("operational_validation"))
    documents["operational_validation_check"] = documents["operational_validation_check"][:1]
    documents["operational_validation_check"][0]["validation_comparison_operator"] = "in"
    found = change_sets.validate(s.conn, s.ben, change_sets.make_draft(s.conn, s.ben, s.sales, documents, "x"))
    assert [p.rule_id for p in found if p.level == "blocks_apply"] == ["VALIDATION-001"]
