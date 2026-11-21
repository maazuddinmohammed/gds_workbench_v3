"""Test setup: a throwaway database just for tests, rebuilt once per test run.

The tests use their own database, `gds_test`, on the same local Postgres as `scripts/local_db.py`, so running
them never touches your `gds_local` database. Each test runs inside a transaction that is rolled back at the
end, so tests never see each other's rows.
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent

os.environ["GDS_LOCAL_DB"] = "gds_test"
_spec = importlib.util.spec_from_file_location("local_db", ROOT / "scripts" / "local_db.py")
local_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(local_db)


@pytest.fixture(scope="session")
def test_database():
    """Rebuild the test database (install + seed) once for the whole run."""
    local_db.main()
    return local_db.DB


@pytest.fixture
def conn(test_database):
    """A connection whose changes are thrown away after the test."""
    with psycopg.connect(
        host=local_db.HOST,
        port=local_db.PORT,
        user=local_db.USER,
        password=local_db.PASSWORD,
        dbname=test_database,
    ) as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def demo(conn):
    """Small set of rows for the tests, rolled back after each test.

    They follow the examples in docs/rules/access.md: Asha (Viewer), Ben (Developer) and Cara (Tenant Admin) in
    Contoso, Sam the Super Admin, Olly with no membership, and Ina who is switched off. Contoso and Fabrikam are
    private, Shared is global. Projects: Retail (Contoso) and HR (Fabrikam).
    """

    def one(sql, params=()):
        return conn.execute(sql, params).fetchone()[0]

    def user(email, name, super_admin=False, active=True):
        return one(
            """INSERT INTO security.principal (principal_email, principal_display_name, is_super_admin, is_active)
               VALUES (%s, %s, %s, %s) RETURNING principal_id""",
            (email, name, super_admin, active),
        )

    def tenant(code, name, visibility="private"):
        return one(
            """INSERT INTO core.tenant (lane_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog,
                                        tenant_visibility)
               VALUES (%s, %s, %s, %s, 'gds_admin', %s) RETURNING tenant_id""",
            (lane, code, name, code.lower(), visibility),
        )

    def member(tenant_id, principal_id, role, mcp=False):
        conn.execute(
            """INSERT INTO security.tenant_principal_access
                   (tenant_id, principal_id, tenant_role, mcp_access_enabled, granted_by_principal_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (tenant_id, principal_id, role, mcp, sam),
        )

    lane = one("INSERT INTO core.lane (lane_code, lane_name) VALUES ('test', 'Test') RETURNING lane_id")
    d = SimpleNamespace()
    d.sam = sam = user("sam@example.com", "Sam", super_admin=True)
    d.asha = user("asha@contoso.com", "Asha")
    d.ben = user("ben@contoso.com", "Ben")
    d.cara = user("cara@contoso.com", "Cara")
    d.olly = user("olly@example.com", "Olly")
    d.ina = user("ina@contoso.com", "Ina", active=False)

    d.contoso = tenant("CONTOSO", "Contoso")
    d.fabrikam = tenant("FABRIKAM", "Fabrikam")
    d.shared = tenant("SHARED", "Shared", visibility="global")

    member(d.contoso, d.asha, "viewer")
    member(d.contoso, d.ben, "developer", mcp=True)
    member(d.contoso, d.cara, "tenant_admin")
    member(d.contoso, d.ina, "developer")
    member(d.shared, d.ben, "developer", mcp=True)

    d.retail = one("INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Retail') RETURNING project_id",
                   (d.contoso,))
    d.hr = one("INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'HR') RETURNING project_id",
               (d.fabrikam,))

    def lock(tenant_id, principal_id, minutes=60):
        """Give someone the tenant lock. Negative minutes make a lock that has already ended."""
        conn.execute(
            """INSERT INTO security.tenant_lock (tenant_id, locked_by_principal_id,
                                                 tenant_lock_acquired_time, tenant_lock_expires_time)
               VALUES (%s, %s, CURRENT_TIMESTAMP - INTERVAL '2 hours',
                       CURRENT_TIMESTAMP + make_interval(mins => %s))""",
            (tenant_id, principal_id, minutes),
        )

    d.lock = lock
    d.conn = conn
    return d
