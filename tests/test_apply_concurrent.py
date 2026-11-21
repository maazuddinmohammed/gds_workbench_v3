"""Two Applies at the same moment: only one gets through (CHANGE-SET-002, step 3d2).

The other tests run inside one transaction that is rolled back, so they cannot show two people pressing Apply at
once. This test uses two real connections to the test database, like two web app requests. It makes its own rows
with unique names and deletes them at the end, even if the test fails.

Draft A and draft B are both built on project version 1. Connection 1 applies A but has not committed yet, so it
still holds the project row. Connection 2 applies B at the same time: it must wait, and once A is saved it must
see the project at version 2 and refuse B with CHANGE-SET-002.
"""

import threading
import time
import uuid

import psycopg
import pytest

from conftest import local_db
from core.project_change_sets import apply_scope_draft, make_scope_draft


def connect(test_database):
    return psycopg.connect(
        host=local_db.HOST,
        port=local_db.PORT,
        user=local_db.USER,
        password=local_db.PASSWORD,
        dbname=test_database,
        autocommit=True,
    )


@pytest.fixture
def rows(test_database):
    """A tenant with one Developer holding its lock, a project, and two Bronze tables. Deleted afterwards."""
    tag = uuid.uuid4().hex[:8]
    conn = connect(test_database)

    def one(sql, params=()):
        return conn.execute(sql, params).fetchone()[0]

    ids = {}
    try:
        ids["lane"] = one(
            "INSERT INTO core.lane (lane_code, lane_name) VALUES (%s, 'Race') RETURNING lane_id", (f"race_{tag}",)
        )
        ids["tenant"] = one(
            """INSERT INTO core.tenant (lane_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog)
               VALUES (%s, %s, 'Race', 'race', 'gds_admin') RETURNING tenant_id""",
            (ids["lane"], f"RACE_{tag}"),
        )
        ids["ben"] = one(
            "INSERT INTO security.principal (principal_email, principal_display_name) VALUES (%s, 'Ben') "
            "RETURNING principal_id",
            (f"ben_{tag}@example.com",),
        )
        conn.execute(
            """INSERT INTO security.tenant_principal_access
                   (tenant_id, principal_id, tenant_role, granted_by_principal_id)
               VALUES (%s, %s, 'developer', %s)""",
            (ids["tenant"], ids["ben"], ids["ben"]),
        )
        conn.execute(
            """INSERT INTO security.tenant_lock (tenant_id, locked_by_principal_id, tenant_lock_expires_time)
               VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour')""",
            (ids["tenant"], ids["ben"]),
        )
        ids["project"] = one(
            "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Race') RETURNING project_id",
            (ids["tenant"],),
        )
        ids["system_type"] = one(
            "INSERT INTO reference.system_type (system_type_code, system_type_name) VALUES (%s, 'Race') "
            "RETURNING system_type_id",
            (f"race_{tag}",),
        )
        ids["connection_type"] = one(
            "INSERT INTO reference.connection_type (connection_type_code, connection_type_name) VALUES (%s, 'Race') "
            "RETURNING connection_type_id",
            (f"race_{tag}",),
        )
        ids["object_type"] = one(
            "INSERT INTO reference.object_type (object_type_code, object_type_name) VALUES (%s, 'Race') "
            "RETURNING object_type_id",
            (f"race_{tag}",),
        )
        ids["system"] = one(
            "INSERT INTO core.system (system_type_id, system_code, system_name) VALUES (%s, %s, 'Race') "
            "RETURNING system_id",
            (ids["system_type"], f"RACE_{tag}"),
        )
        ids["connection"] = one(
            """INSERT INTO core.connection (tenant_id, system_id, connection_type_id, connection_code, connection_name)
               VALUES (%s, %s, %s, 'race_db', 'Race') RETURNING connection_id""",
            (ids["tenant"], ids["system"], ids["connection_type"]),
        )
        bronze = one("SELECT zone_id FROM reference.zone WHERE zone_code = 'bronze'")
        for name in ("a", "b"):
            ids[f"table_{name}"] = one(
                """INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema,
                                            object_name)
                   VALUES (%s, %s, %s, %s, 'bronze_race', %s) RETURNING object_id""",
                (ids["connection"], ids["tenant"], ids["object_type"], bronze, name),
            )
        ids["record"] = lambda name: {
            "tenant_code": f"RACE_{tag}",
            "system_code": f"RACE_{tag}",
            "connection_code": "race_db",
            "object_schema": "bronze_race",
            "object_name": name,
            "is_active": True,
            "is_locked": False,
        }
        yield ids
    finally:
        _clean_up(conn, ids)
        conn.close()


def _clean_up(conn, ids):
    """Delete the test's rows, children first. Only rows of this test's own tenant, system and types."""
    steps = [
        ("project.project_input_scope", "project_id", "project"),
        ("application.project_change_set", "project_id", "project"),
        ("project.project", "project_id", "project"),
        ("core.object", "connection_id", "connection"),
        ("core.connection", "connection_id", "connection"),
        ("core.system", "system_id", "system"),
        ("reference.object_type", "object_type_id", "object_type"),
        ("reference.connection_type", "connection_type_id", "connection_type"),
        ("reference.system_type", "system_type_id", "system_type"),
        ("security.tenant_lock", "tenant_id", "tenant"),
        ("security.tenant_principal_access", "tenant_id", "tenant"),
        ("core.tenant", "tenant_id", "tenant"),
        ("security.principal", "principal_id", "ben"),
        ("core.lane", "lane_id", "lane"),
    ]
    for table, column, key in steps:
        if key in ids:
            conn.execute(f"DELETE FROM {table} WHERE {column} = %s", (ids[key],))


def test_two_applies_at_once_only_the_first_gets_through(test_database, rows):
    first, second = connect(test_database), connect(test_database)
    try:
        draft_a = make_scope_draft(first, rows["ben"], rows["project"], [rows["record"]("a")], "Add a")
        draft_b = make_scope_draft(first, rows["ben"], rows["project"], [rows["record"]("b")], "Add b")

        result = {}

        def apply_b():
            result["b"] = apply_scope_draft(second, rows["ben"], draft_b)

        with first.transaction():  # A is applied but not committed: the project row stays locked
            assert apply_scope_draft(first, rows["ben"], draft_a) == []
            racer = threading.Thread(target=apply_b)
            racer.start()
            time.sleep(1)
            assert racer.is_alive(), "B should be waiting for A"
        racer.join(timeout=10)
        assert not racer.is_alive()

        assert [(p.rule_id, p.record) for p in result["b"]] == [("CHANGE-SET-002", None)]
        check = connect(test_database)
        try:
            version = check.execute(
                "SELECT project_version FROM project.project WHERE project_id = %s", (rows["project"],)
            ).fetchone()[0]
            scope = check.execute(
                "SELECT object_id FROM project.project_input_scope WHERE project_id = %s", (rows["project"],)
            ).fetchall()
            statuses = dict(
                check.execute(
                    """SELECT project_change_set_id, project_change_set_status FROM application.project_change_set
                        WHERE project_id = %s""",
                    (rows["project"],),
                ).fetchall()
            )
        finally:
            check.close()
        assert version == 2
        assert scope == [(rows["table_a"],)]
        assert statuses == {draft_a: "applied", draft_b: "draft"}
    finally:
        first.close()
        second.close()
