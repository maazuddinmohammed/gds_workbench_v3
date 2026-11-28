"""Tests for relationships (core/relationships.py) and subject areas (core/subject_areas.py), with their rules
(RELATIONSHIP-001 and 002, SUBJECT-AREA-001 and 002, ENRICHMENT-001).

The answers in tests/answers/ are real ones a model gave on the demo data. Each test checks the draft records an
answer becomes, or what the rules find on the project after Apply.
"""

import json
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from core import change_sets, relationships, subject_areas
from core.problems import Refused
from core.tenant_lock import take_lock

ANSWERS = Path(__file__).resolve().parent / "answers"


def answer(step):
    return json.loads((ANSWERS / f"{step}.json").read_text())


@pytest.fixture
def a(demo_data):
    """Sales with every ACME Source table in scope, the Salesforce ids marked as keys, Ben holding the lock."""
    d = demo_data
    take_lock(d.conn, d.ben, d.acme)
    rows = d.conn.execute(
        """SELECT ct.tenant_code, sy.system_code, c.connection_code, o.object_schema, o.object_name
             FROM core.object AS o JOIN core.connection AS c USING (connection_id)
             JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id JOIN core.system AS sy ON sy.system_id = c.system_id
             JOIN reference.zone AS z ON z.zone_id = o.zone_id
            WHERE ct.tenant_code = 'ACME' AND lower(z.zone_code) = 'source' AND o.is_active""").fetchall()
    scope = [dict(zip(("tenant_code", "system_code", "connection_code", "object_schema", "object_name"), r)) for r in rows]
    assert apply(d, {"project_input_scope": scope}) == []
    keys = [{"object_schema": "salesforce", "object_name": t, "attribute_name": "Id", "is_natural_key": True}
            for t in ("Account", "Contact")]
    keys.append({"object_schema": "salesforce", "object_name": "Contact", "attribute_name": "AccountId",
                 "is_foreign_key_candidate": True})
    assert apply(d, {"attribute_enrichment": keys}) == []
    d.cur = d.conn.cursor(row_factory=dict_row)
    return d


def apply(d, documents):
    return [str(p) for p in change_sets.apply(d.conn, d.ben, change_sets.make_draft(d.conn, d.ben, d.sales, documents, "x"))
            if p.level == "blocks_apply"]


def run_of(d, step, request=None):
    run = {"project_id": d.sales, "project_workflow": step.workflow, "extra_instructions": None,
           "run_request_document": request or {}}
    prepared, lines = step.prepare(d.cur, run, step.items(d.cur, d.sales, request or {}))
    return run, prepared, lines


def contact():
    return {"tables": [{"object_schema": "salesforce", "object_name": "Contact"}]}


# --- Relationships -------------------------------------------------------------------------------------------------


def test_the_links_input_shows_only_key_and_pointing_columns(a):
    _, prepared, lines = run_of(a, relationships.STEP, contact())
    to_tables = prepared["salesforce.Contact"]["to_tables"]
    assert "Id|STRING" not in to_tables  # inferred type not set: shows as null
    assert "\nId|null|true|null|null|null|[]" in to_tables and "Name|" not in to_tables
    assert "sap.KNA1 has no key marked, so no link can point at it." in lines


def test_a_real_answer_becomes_links_that_keep_the_rules(a):
    run, _, _ = run_of(a, relationships.STEP, contact())
    documents, notes = relationships.records(a.cur, run, "salesforce.Contact", answer("analysis"))
    assert documents == {"analysis_result": [{"from_object_schema": "salesforce", "from_object_name": "Contact",
                                              "from_attribute_name": "AccountId", "to_object_schema": "salesforce",
                                              "to_object_name": "Account", "to_attribute_name": "Id",
                                              "relationship_kind": "foreign_key", "inferred_cardinality": "unknown",
                                              "is_active": True}]}
    assert apply(a, documents) == []
    run, _, _ = run_of(a, relationships.STEP, contact())  # the same answer again changes nothing
    assert relationships.records(a.cur, run, "salesforce.Contact", answer("analysis")) == ({}, [])


def test_a_link_a_person_switched_off_is_not_brought_back(a):
    run, _, _ = run_of(a, relationships.STEP, contact())
    documents, _ = relationships.records(a.cur, run, "salesforce.Contact", answer("analysis"))
    assert apply(a, documents) == []
    documents["analysis_result"][0]["is_active"] = False  # a person switches the link off
    assert apply(a, documents) == []
    run, _, _ = run_of(a, relationships.STEP, contact())
    documents, notes = relationships.records(a.cur, run, "salesforce.Contact", answer("analysis"))
    assert documents == {} and notes == ["the link from AccountId was switched off by a person, left out."]


def test_relationship_002_the_same_pair_both_ways(a):
    both = [{"from_object_schema": "salesforce", "from_object_name": f, "from_attribute_name": fc,
             "to_object_schema": "salesforce", "to_object_name": t, "to_attribute_name": tc,
             "relationship_kind": "foreign_key"}
            for f, fc, t, tc in (("Contact", "AccountId", "Account", "Id"), ("Account", "Id", "Contact", "AccountId"))]
    problems = apply(a, {"analysis_result": both})
    assert [p.split(":")[0] for p in problems] == ["RELATIONSHIP-002", "RELATIONSHIP-002"]


def test_run_005_relationships_need_a_key_somewhere(a):
    a.conn.execute("UPDATE workflow.attribute_enrichment SET is_natural_key = FALSE")
    with pytest.raises(Refused) as info:
        relationships.items(a.cur, a.sales, {})
    assert info.value.rule_id == "RUN-005"


def test_enrichment_001_a_column_of_a_table_out_of_scope(a):
    problems = apply(a, {"attribute_enrichment": [{"object_schema": "salesforce", "object_name": "Lead",
                                                  "attribute_name": "Email", "is_pii": True}],
                         "project_input_scope": [{"tenant_code": "ACME", "system_code": "SALESFORCE_CRM",
                                                  "connection_code": "salesforce_crm", "object_schema": "salesforce",
                                                  "object_name": "Lead", "is_active": False}]})
    assert [p.split(":")[0] for p in problems] == ["ENRICHMENT-001"]


# --- Subject areas -------------------------------------------------------------------------------------------------


def test_a_real_answer_becomes_areas_and_their_tables(a):
    run, prepared, _ = run_of(a, subject_areas.STEP)
    assert prepared["the whole scope"]["existing_subject_areas"] == "none"
    documents, notes = subject_areas.records(a.cur, run, "the whole scope", answer("subject_area"))
    assert len(documents["subject_area"]) == 6 and len(documents["subject_area_table"]) == 27
    found = change_sets.validate(a.conn, a.ben, change_sets.make_draft(a.conn, a.ben, a.sales, documents, "Areas"))
    assert [p.rule_id for p in found] == []


def test_a_rerun_switches_off_a_table_missing_from_an_area_but_not_a_locked_one(a):
    run, _, _ = run_of(a, subject_areas.STEP)
    documents, _ = subject_areas.records(a.cur, run, "the whole scope", answer("subject_area"))
    assert apply(a, documents) == []
    a.conn.execute("""UPDATE workflow.subject_area_table SET is_locked = TRUE WHERE object_id =
                      (SELECT object_id FROM core.object WHERE object_name = 'KNVV')""")
    again = answer("subject_area")
    accounts = next(s for s in again["subject_areas"] if s["subject_area_name"] == "Customer accounts")
    accounts["tables"] = [t for t in accounts["tables"] if t["object_name"] in ("Account", "KNA1")]
    run, _, _ = run_of(a, subject_areas.STEP)
    documents, _ = subject_areas.records(a.cur, run, "the whole scope", again)
    assert documents == {"subject_area_table": [{"subject_area_name": "Customer accounts", "object_schema": "salesforce",
                                                 "object_name": "Contact", "is_active": False}]}


def test_subject_area_001_a_table_taken_out_of_scope_while_an_area_has_it(a):
    run, _, _ = run_of(a, subject_areas.STEP)
    documents, _ = subject_areas.records(a.cur, run, "the whole scope", answer("subject_area"))
    assert apply(a, documents) == []
    problems = apply(a, {"project_input_scope": [{"tenant_code": "ACME", "system_code": "SAP_ERP",
                                                  "connection_code": "sap_erp", "object_schema": "sap",
                                                  "object_name": "KNA1", "is_active": False}]})
    assert [p.split(":")[0] for p in problems] == ["SUBJECT-AREA-001", "SUBJECT-AREA-001"]
