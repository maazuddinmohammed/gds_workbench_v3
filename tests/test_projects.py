"""Tests for core/projects.py: a tenant's projects and a project's current scope (step 4a2).

People from the `demo` fixture and the catalog from the `cat` fixture in conftest.py. Project Orders belongs to ERP;
Eve is a Viewer in ERP, Gus a Viewer in GDS only.
"""

import pytest

from core.problems import NotFound
from core.project_change_sets import check_scope_draft, make_scope_draft
from core.projects import current_scope, list_projects


def test_projects_of_a_tenant_by_name_without_switched_off_ones(demo):
    demo.conn.execute("INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Billing')", (demo.contoso,))
    demo.conn.execute(
        "INSERT INTO project.project (tenant_id, project_name, is_active) VALUES (%s, 'Old', FALSE)", (demo.contoso,)
    )
    assert [p.project_name for p in list_projects(demo.conn, demo.asha, demo.contoso)] == ["Billing", "Retail"]


def test_projects_of_a_tenant_you_cannot_read_are_not_found(demo):
    with pytest.raises(NotFound):
        list_projects(demo.conn, demo.olly, demo.contoso)


@pytest.fixture
def orders(cat):
    conn = cat.conn
    project = conn.execute(
        "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Orders') RETURNING project_id", (cat.erp,)
    ).fetchone()[0]
    for object_id, active in [(cat.shared_bronze, True), (cat.erp_source, True), (cat.erp_bronze, False)]:
        conn.execute(
            "INSERT INTO project.project_input_scope (project_id, object_id, is_active) VALUES (%s, %s, %s)",
            (project, object_id, active),
        )
    return project


def test_scope_lists_active_rows_in_zone_order_named_by_row_key(cat, orders):
    scope = current_scope(cat.conn, cat.eve, orders)
    assert [(t.zone_code, t.object_schema, t.object_name) for t in scope] == [
        ("source", "sap", "VBAK"),
        ("bronze", "bronze_shared", "calendar"),
    ]
    shared = scope[1]
    # The row key names the connection's tenant (GDS owns gds_us); the table itself belongs to Shared.
    assert (shared.tenant_code, shared.system_code, shared.connection_code, shared.source_tenant_code) == (
        "GDS", "GDS_US", "gds_us", "SHARED"
    )


def test_scope_rows_taken_out_show_only_when_asked_for(cat, orders):
    scope = current_scope(cat.conn, cat.eve, orders, include_switched_off=True)
    assert [(t.object_name, t.is_active) for t in scope] == [("VBAK", True), ("orders", False), ("calendar", True)]


def test_scope_of_a_project_you_cannot_read_is_not_found(cat, orders):
    with pytest.raises(NotFound):
        current_scope(cat.conn, cat.gus, orders)
    with pytest.raises(NotFound):
        current_scope(cat.conn, cat.eve, 999_999)


def test_a_scope_row_can_be_sent_back_as_a_draft_record_without_problems(cat, orders):
    demo = cat.demo
    cat.conn.execute(
        """INSERT INTO security.tenant_principal_access (tenant_id, principal_id, tenant_role, granted_by_principal_id)
           VALUES (%s, %s, 'developer', %s)""",
        (cat.erp, demo.ben, demo.sam),
    )
    demo.lock(cat.erp, demo.ben)
    keys = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name", "is_active", "is_locked")
    records = [{k: getattr(t, k) for k in keys} | {"is_locked": True} for t in current_scope(cat.conn, demo.ben, orders)]

    change_set_id = make_scope_draft(cat.conn, demo.ben, orders, records, "Lock the scope")
    assert check_scope_draft(cat.conn, demo.ben, change_set_id) == []
