"""Tests for the demo data in database/demo/ (step 4a1): tenant ACME with SAP ERP, Salesforce CRM and Workday HR,
and the global data lake tenant GDS (database/demo/README.md).

The demo data is what you see when you run the apps locally, so these tests check it fits the rules: each demo
user sees the tables they should, and the roles behave as their names say. The test database is built without
demo data, so each test loads it inside its own transaction, which is rolled back at the end.
"""

import pytest

from core.access import find_user_by_object_id
from core.catalog import list_tables
from core.problems import Refused
from core.project_change_sets import apply_scope_draft, make_scope_draft
from core.tenant_lock import take_lock


@pytest.fixture
def d(demo_data):
    return demo_data


def names(tables):
    return {f"{t.object_schema}.{t.object_name}" for t in tables}


def test_viewer_sees_acme_tables_from_all_three_systems_and_the_global_gds_tables(d):
    page = list_tables(d.conn, d.asha, d.acme)

    assert page.total == 29  # 22 Source, 4 Bronze and 1 Silver of ACME's, 2 Bronze of GDS's
    source_systems = {t.system_code for t in page.tables if t.zone_code == "source"}
    assert source_systems == {"SAP_ERP", "SALESFORCE_CRM", "WORKDAY_HR"}
    assert names(t for t in page.tables if t.is_global) == {"bronze_gds.calendar", "bronze_gds.currency"}


def test_switched_off_table_shows_only_when_asked_for(d):
    assert "sap.ZOLD_ORDERS" not in names(list_tables(d.conn, d.asha, d.acme).tables)
    assert "sap.ZOLD_ORDERS" in names(list_tables(d.conn, d.asha, d.acme, include_switched_off=True).tables)


def test_only_source_and_bronze_tables_can_be_scoped(d):
    page = list_tables(d.conn, d.asha, d.acme)
    assert names(t for t in page.tables if not t.can_scope) == {"silver_sales.sales_order"}
    assert list_tables(d.conn, d.asha, d.acme, scope_only=True).total == 28


@pytest.mark.parametrize("who, allowed", [("asha", False), ("ben", True), ("cara", True), ("sam", True)])
def test_only_the_viewer_cannot_take_the_acme_lock(d, who, allowed):
    if allowed:
        assert take_lock(d.conn, getattr(d, who), d.acme).locked_by_principal_id == getattr(d, who)
    else:
        with pytest.raises(Refused) as info:
            take_lock(d.conn, getattr(d, who), d.acme)
        assert info.value.rule_id == "ACCESS-002"


def record(tenant, system, connection, schema, name):
    return {"tenant_code": tenant, "system_code": system, "connection_code": connection,
            "object_schema": schema, "object_name": name, "is_active": True, "is_locked": False}


def test_developer_can_scope_tables_from_two_systems_and_a_global_table_into_the_demo_project(d):
    take_lock(d.conn, d.ben, d.acme)
    records = [
        record("ACME", "SAP_ERP", "sap_erp", "sap", "VBAK"),
        record("ACME", "SALESFORCE_CRM", "salesforce_crm", "salesforce", "Account"),
        record("GDS", "GDS_US", "gds_us", "bronze_gds", "calendar"),
    ]
    change_set_id = make_scope_draft(d.conn, d.ben, d.sales, records, "Sales scope")

    assert apply_scope_draft(d.conn, d.ben, change_set_id) == []
    scoped = d.conn.execute(
        """SELECT o.object_schema || '.' || o.object_name
             FROM project.project_input_scope AS s JOIN core.object AS o USING (object_id)
            WHERE s.project_id = %s ORDER BY 1""",
        (d.sales,),
    ).fetchall()
    assert [row[0] for row in scoped] == ["bronze_gds.calendar", "salesforce.Account", "sap.VBAK"]


def test_each_demo_user_signs_in_to_the_local_mcp_server_by_their_made_up_object_id(d):
    ids = {name: f"00000000-0000-4000-8000-00000000000{n}" for n, name in enumerate(["sam", "asha", "ben", "cara"], 1)}

    assert {name: find_user_by_object_id(d.conn, oid).principal_id for name, oid in ids.items()} == {
        name: getattr(d, name) for name in ids
    }
