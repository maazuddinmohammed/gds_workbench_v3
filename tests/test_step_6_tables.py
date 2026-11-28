"""Tests for the table changes of the step 6 design (design/overview/run.md and design/workflows/).

Each test checks what Postgres keeps or refuses, by constraint name: a stopped Run keeps its draft and says why,
a validation group is one per entity and system and its entity is in its project, and a mapping's table list is
a JSON list.
"""

import psycopg
import pytest
from psycopg.types.json import Jsonb


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def refused(conn, constraint, sql, params=()):
    """Run sql inside a savepoint and check Postgres refuses it with this constraint."""
    with pytest.raises(psycopg.errors.IntegrityError) as error:
        with conn.transaction():
            conn.execute(sql, params)
    assert error.value.diag.constraint_name == constraint


@pytest.fixture
def system(conn):
    system_type = one(conn, "INSERT INTO reference.system_type (system_type_code, system_type_name) "
                            "VALUES ('hr', 'HR') RETURNING system_type_id")
    return one(conn, "INSERT INTO core.system (system_type_id, system_code, system_name) "
                     "VALUES (%s, 'WORKDAY_HR', 'Workday') RETURNING system_id", (system_type,))


def entity(conn, project_id, name):
    return one(conn, "INSERT INTO workflow.operational_entity (project_id, operational_entity_schema_name, "
                     "operational_entity_name) VALUES (%s, 'silver_people', %s) RETURNING operational_entity_id",
               (project_id, name))


RUN = """INSERT INTO application.run (tenant_id, project_id, project_workflow, base_project_version,
                                      started_by_principal_id, run_status, completed_time, failure_message,
                                      project_change_set_id)
         VALUES (%s, %s, 'profiling', 1, %s, %s, CURRENT_TIMESTAMP, %s, %s) RETURNING run_id"""


def test_a_stopped_run_keeps_its_draft_and_says_why(demo):
    conn = demo.conn
    draft = one(conn, """INSERT INTO application.project_change_set (project_id, project_change_set_status,
                             project_change_set_title, project_change_set_source, base_project_version,
                             created_by_principal_id)
                         VALUES (%s, 'draft', 'Operational model: Sales', 'ai_run', 1, %s)
                         RETURNING project_change_set_id""", (demo.retail, demo.ben))

    run_id = one(conn, RUN, (demo.contoso, demo.retail, demo.ben, "stopped", "Stopped at the turn limit (100).", draft))
    assert conn.execute("SELECT run_status, project_change_set_id FROM application.run WHERE run_id = %s",
                        (run_id,)).fetchone() == ("stopped", draft)

    refused(conn, "ck_run_stopped_change_set", RUN,
            (demo.contoso, demo.retail, demo.ben, "stopped", "Stopped at the turn limit (100).", None))
    refused(conn, "ck_run_failure_message", RUN, (demo.contoso, demo.retail, demo.ben, "stopped", None, draft))
    refused(conn, "ck_run_change_set", RUN, (demo.contoso, demo.retail, demo.ben, "failed", "Nothing was saved.", draft))


GROUP = """INSERT INTO workflow.operational_validation_group (project_id, operational_entity_id, system_id)
           VALUES (%s, %s, %s)"""


def test_a_validation_group_is_one_per_entity_and_system(demo, system):
    conn = demo.conn
    employee = entity(conn, demo.retail, "Employee")
    conn.execute(GROUP, (demo.retail, employee, system))

    refused(conn, "uq_operational_validation_group_entity_system", GROUP, (demo.retail, employee, system))
    conn.execute(GROUP, (demo.retail, entity(conn, demo.retail, "JobProfile"), system))
    assert one(conn, "SELECT count(*) FROM workflow.operational_validation_group WHERE system_id = %s",
               (system,)) == 2


def test_a_validation_group_entity_must_be_in_the_group_project(demo, system):
    employee = entity(demo.conn, demo.retail, "Employee")

    refused(demo.conn, "fk_operational_validation_group_operational_entity", GROUP, (demo.hr, employee, system))


MAPPING = """INSERT INTO workflow.operational_object_mapping (operational_entity_id, system_id,
                                                              operational_object_mapping_tables)
             VALUES (%s, %s, %s)"""


def test_a_mapping_table_list_is_a_json_list(demo, system):
    conn = demo.conn
    employee = entity(conn, demo.retail, "Employee")

    refused(conn, "ck_operational_object_mapping_tables", MAPPING,
            (employee, system, Jsonb({"alias": "w", "object_schema": "workday", "object_name": "Worker"})))
    conn.execute(MAPPING, (employee, system,
                           Jsonb([{"alias": "w", "role": "source", "object_schema": "workday", "object_name": "Worker"}])))
    assert one(conn, "SELECT operational_object_mapping_tables -> 0 ->> 'alias' FROM workflow.operational_object_mapping "
                     "WHERE operational_entity_id = %s", (employee,)) == "w"
