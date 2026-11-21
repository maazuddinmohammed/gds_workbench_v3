"""Tests for the app logins (database/install/90_roles.sql) and scripts/db_install.py (step 5d).

The apps connect as gds_web_runtime and gds_mcp_runtime on Azure. These tests run the whole scope loop as each login,
so a missing grant shows up here and not on Azure, check that 99_verify_install.sql notices a missing grant, and
install into a new empty database the way db_install.py does on Azure.
"""

import importlib.util
import sys

import psycopg
import pytest

from conftest import ROOT, local_db
from core.project_change_sets import apply_scope_draft, make_scope_draft
from core.projects import current_scope
from core.tenant_lock import release_lock, take_lock

_spec = importlib.util.spec_from_file_location("db_install", ROOT / "scripts" / "db_install.py")
db_install = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("local_db", local_db)  # db_install imports it by name, as it does when run as a script
_spec.loader.exec_module(db_install)

SAP_VBAK = {"tenant_code": "ACME", "system_code": "SAP_ERP", "connection_code": "sap_erp",
            "object_schema": "sap", "object_name": "VBAK", "is_active": True, "is_locked": False}


@pytest.mark.parametrize("login, via_mcp", [("gds_web_runtime", False), ("gds_mcp_runtime", True)])
def test_each_app_login_can_run_the_scope_loop(demo_data, login, via_mcp):
    d = demo_data
    d.conn.execute(f"SET LOCAL ROLE {login}")

    take_lock(d.conn, d.ben, d.acme, via_mcp=via_mcp)
    draft = make_scope_draft(d.conn, d.ben, d.sales, [SAP_VBAK], "Add VBAK", via_mcp=via_mcp)
    assert apply_scope_draft(d.conn, d.ben, draft, via_mcp=via_mcp) == []
    release_lock(d.conn, d.ben, d.acme, via_mcp=via_mcp)

    assert [t.object_name for t in current_scope(d.conn, d.ben, d.sales, via_mcp=via_mcp)] == ["VBAK"]
    assert d.conn.execute("SELECT current_user").fetchone()[0] == login


def test_install_check_names_a_missing_grant(conn):
    conn.execute("REVOKE INSERT ON core.tenant FROM gds_web_runtime")

    with pytest.raises(psycopg.errors.RaiseException, match="login gds_web_runtime cannot insert core.tenant"):
        conn.execute((ROOT / "database" / "install" / "99_verify_install.sql").read_text())


def test_install_check_names_a_workflow_table_without_is_active(conn):
    conn.execute("ALTER TABLE workflow.operational_link DROP COLUMN is_active")

    with pytest.raises(psycopg.errors.RaiseException, match="missing is_active: workflow.operational_link"):
        conn.execute((ROOT / "database" / "install" / "99_verify_install.sql").read_text())


def test_db_install_fills_an_empty_database_without_demo_data_and_refuses_a_second_time(monkeypatch):
    name = "gds_install_test"
    with local_db.connect("postgres") as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    dsn = f"host={local_db.HOST} port={local_db.PORT} user={local_db.USER} password={local_db.PASSWORD} dbname={name}"
    monkeypatch.setattr(sys, "argv", ["db_install.py", dsn])
    try:
        db_install.main()

        with psycopg.connect(dsn) as conn:
            zones = {row[0] for row in conn.execute("SELECT lower(btrim(zone_code)) FROM reference.zone")}
            users = conn.execute("SELECT count(*) FROM security.principal").fetchone()[0]
        assert zones == {"source", "bronze", "silver", "gold"}  # seed ran
        assert users == 0  # no demo data

        with pytest.raises(psycopg.errors.RaiseException, match="Not a clean database"):
            db_install.main()
    finally:
        with local_db.connect("postgres") as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
