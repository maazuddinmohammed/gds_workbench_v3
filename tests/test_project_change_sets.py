"""Tests for core/project_change_sets.py: making and checking a scope draft (step 3d1).

Project Orders belongs to ERP. Ben is a Developer in ERP. The catalog comes from the `cat` fixture in conftest.py:
ERP's Source table sap.VBAK on erp_db, ERP's Bronze, Silver and Gold on the data lake connection gds_us, Shared's
global Bronze table and Fabrikam's private Bronze table, also on gds_us.
"""

from types import SimpleNamespace

import pytest

from core.problems import NotFound, Refused
from core.project_change_sets import check_scope_draft, make_scope_draft


@pytest.fixture
def p(cat):
    conn, demo = cat.conn, cat.demo
    conn.execute(
        """INSERT INTO security.tenant_principal_access (tenant_id, principal_id, tenant_role, granted_by_principal_id)
           VALUES (%s, %s, 'developer', %s)""",
        (cat.erp, demo.ben, demo.sam),
    )
    project = conn.execute(
        "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Orders') RETURNING project_id", (cat.erp,)
    ).fetchone()[0]
    demo.lock(cat.erp, demo.ben)
    return SimpleNamespace(cat=cat, conn=conn, demo=demo, project=project, ben=demo.ben)


def rec(schema, name, connection="gds_us", active=True, locked=False):
    tenant, system = {"gds_us": ("GDS", "GDS_US"), "erp_db": ("ERP", "ERP_DB")}[connection]
    return {
        "tenant_code": tenant,
        "system_code": system,
        "connection_code": connection,
        "object_schema": schema,
        "object_name": name,
        "is_active": active,
        "is_locked": locked,
    }


BRONZE = rec("bronze_erp", "orders")
SOURCE = rec("sap", "VBAK", connection="erp_db")
SILVER = rec("silver_erp", "order")
SHARED = rec("bronze_shared", "calendar")
FABRIKAM = rec("bronze_hr", "employees")


def draft(p, *records, title="Scope for Orders"):
    return make_scope_draft(p.conn, p.ben, p.project, list(records), title)


def check(p, change_set_id):
    return [(problem.rule_id, problem.record) for problem in check_scope_draft(p.conn, p.ben, change_set_id)]


def refused(rule_id, call, kind=Refused):
    with pytest.raises(kind) as info:
        call()
    assert info.value.rule_id == rule_id


def scope_rows(p):
    sql = "SELECT count(*) FROM project.project_input_scope WHERE project_id = %s"
    return p.conn.execute(sql, (p.project,)).fetchone()[0]


# --- Making a draft --------------------------------------------------------------------------------------------------


def test_draft_is_saved_on_the_current_version_and_scope_does_not_change(p):
    p.conn.execute("UPDATE project.project SET project_version = 7 WHERE project_id = %s", (p.project,))
    change_set_id = draft(p, BRONZE, SOURCE)
    saved = p.conn.execute(
        """SELECT project_id, project_change_set_status, project_change_set_source, base_project_version,
                  project_input_scope_document, created_by_principal_id
             FROM application.project_change_set WHERE project_change_set_id = %s""",
        (change_set_id,),
    ).fetchone()
    assert saved == (p.project, "draft", "web_app_edit", 7, [BRONZE, SOURCE], p.ben)
    assert scope_rows(p) == 0


def test_viewer_cannot_make_a_draft(p):
    refused("ACCESS-002", lambda: make_scope_draft(p.conn, p.cat.eve, p.project, [BRONZE], "Scope"))


def test_without_the_tenant_lock_you_cannot_make_a_draft(p):
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    refused("ACCESS-003", lambda: draft(p, BRONZE))


def test_the_lock_on_the_data_lake_tenant_does_not_count(p):
    """Orders belongs to ERP, so only ERP's lock counts, even for a table that sits in the lake."""
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    p.demo.lock(p.cat.gds, p.ben)
    refused("ACCESS-003", lambda: draft(p, BRONZE))


def test_locked_project_cannot_get_a_draft(p):
    p.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (p.project,))
    refused("CHANGE-SET-004", lambda: draft(p, BRONZE))


def test_unknown_project_is_not_found(p):
    refused("ACCESS-001", lambda: make_scope_draft(p.conn, p.ben, -1, [BRONZE], "Scope"), kind=NotFound)


def test_outsider_gets_not_found(p):
    refused("ACCESS-001", lambda: make_scope_draft(p.conn, p.cat.gus, p.project, [BRONZE], "Scope"), kind=NotFound)


@pytest.mark.parametrize(
    "records",
    [
        [],
        "not a list",
        [{k: v for k, v in BRONZE.items() if k != "is_locked"}],  # a field missing
        [BRONZE | {"object_id": 5}],  # a database id is not allowed
        [BRONZE | {"is_active": "yes"}],
        [BRONZE | {"object_name": "  "}],
        [BRONZE, BRONZE | {"object_name": " ORDERS ", "is_active": False}],  # the same table twice
    ],
)
def test_malformed_records_are_refused_and_nothing_is_saved(p, records):
    with pytest.raises(ValueError):
        make_scope_draft(p.conn, p.ben, p.project, records, "Scope")
    assert p.conn.execute("SELECT count(*) FROM application.project_change_set").fetchone()[0] == 0


def test_a_draft_needs_a_title(p):
    with pytest.raises(ValueError):
        draft(p, BRONZE, title="  ")


# --- Checking a draft ------------------------------------------------------------------------------------------------


def test_a_good_draft_has_no_problems(p):
    """ERP's Source and Bronze tables, and Shared's global table, may all be in scope (SCOPE-001 and 002 pass)."""
    assert check(p, draft(p, SOURCE, BRONZE, SHARED)) == []


def test_names_are_matched_ignoring_case_and_outer_spaces(p):
    shouty = {k: (f" {v.upper()} " if isinstance(v, str) else v) for k, v in BRONZE.items()}
    assert check(p, draft(p, shouty)) == []


def test_change_set_001_only_a_draft(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute(
        """UPDATE application.project_change_set SET project_change_set_status = 'rejected',
                  decided_by_principal_id = %s, decided_time = CURRENT_TIMESTAMP
            WHERE project_change_set_id = %s""",
        (p.ben, change_set_id),
    )
    assert check(p, change_set_id) == [("CHANGE-SET-001", None)]


def test_change_set_002_project_moved_on(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("UPDATE project.project SET project_version = 2 WHERE project_id = %s", (p.project,))
    assert check(p, change_set_id) == [("CHANGE-SET-002", None)]


def test_change_set_003_table_that_does_not_exist(p):
    assert check(p, draft(p, BRONZE, rec("bronze_erp", "nope"))) == [("CHANGE-SET-003", 1)]


def test_change_set_003_same_name_on_another_connection_is_not_found(p):
    """bronze_erp.orders exists on gds_us, not on erp_db."""
    assert check(p, draft(p, rec("bronze_erp", "orders", connection="erp_db"))) == [("CHANGE-SET-003", 0)]


def test_scope_001_silver_table_refused(p):
    problems = check_scope_draft(p.conn, p.ben, draft(p, SILVER))
    assert [(x.rule_id, x.record) for x in problems] == [("SCOPE-001", 0)]
    assert str(problems[0]) == "SCOPE-001: silver_erp.order is in zone Silver; only Source and Bronze can be in scope."


def test_scope_002_another_private_tenants_table_refused(p):
    assert check(p, draft(p, FABRIKAM)) == [("SCOPE-002", 0)]


def test_switching_a_table_off_is_never_a_scope_problem(p):
    assert check(p, draft(p, SILVER | {"is_active": False}, FABRIKAM | {"is_active": False})) == []


def test_every_problem_is_reported_at_once(p):
    change_set_id = draft(p, SILVER, FABRIKAM, BRONZE, rec("x", "y"))
    p.conn.execute("UPDATE project.project SET project_version = 2 WHERE project_id = %s", (p.project,))
    assert check(p, change_set_id) == [
        ("CHANGE-SET-002", None),
        ("SCOPE-001", 0),
        ("SCOPE-002", 1),
        ("CHANGE-SET-003", 3),
    ]


@pytest.fixture
def locked_bronze(p):
    p.conn.execute(
        "INSERT INTO project.project_input_scope (project_id, object_id, is_locked) VALUES (%s, %s, TRUE)",
        (p.project, p.cat.erp_bronze),
    )


@pytest.mark.parametrize("source", ["vscode_push", "ai_run"])
def test_change_set_005_push_or_run_cannot_change_a_locked_row(p, locked_bronze, source):
    change_set_id = draft(p, BRONZE | {"is_active": False, "is_locked": True})
    p.conn.execute(
        "UPDATE application.project_change_set SET project_change_set_source = %s WHERE project_change_set_id = %s",
        (source, change_set_id),
    )
    assert check(p, change_set_id) == [("CHANGE-SET-005", 0)]


def test_change_set_005_push_that_leaves_a_locked_row_as_it_is_is_fine(p, locked_bronze):
    change_set_id = draft(p, BRONZE | {"is_locked": True})
    p.conn.execute(
        "UPDATE application.project_change_set SET project_change_set_source = 'vscode_push' "
        "WHERE project_change_set_id = %s",
        (change_set_id,),
    )
    assert check(p, change_set_id) == []


def test_change_set_005_hand_edit_may_unlock_a_locked_row(p, locked_bronze):
    assert check(p, draft(p, BRONZE | {"is_locked": False})) == []


def test_anyone_who_reads_the_project_may_check_but_outsiders_get_not_found(p):
    change_set_id = draft(p, BRONZE)
    assert check_scope_draft(p.conn, p.cat.eve, change_set_id) == []  # Eve is a Viewer in ERP
    refused("ACCESS-001", lambda: check_scope_draft(p.conn, p.cat.gus, change_set_id), kind=NotFound)
    refused("ACCESS-001", lambda: check_scope_draft(p.conn, p.ben, -1), kind=NotFound)
