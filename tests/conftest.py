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


@pytest.fixture
def cat(demo):
    """A small catalog on top of `demo`, rolled back after each test.

    ERP (private) owns Source table sap.VBAK on its own connection erp_db, and Bronze, Silver and Gold tables on
    the GDS US connection gds_us of the data lake tenant GDS. Shared (global) and Fabrikam (private) each own one
    Bronze table on gds_us. Eve is a Viewer in ERP only, Gus a Viewer in GDS only.
    """
    conn = demo.conn

    def one(sql, params=()):
        return conn.execute(sql, params).fetchone()[0]

    def tenant(code, visibility="private", data_lake=False):
        return one(
            """INSERT INTO core.tenant (lane_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog,
                                        tenant_visibility, is_data_lake)
               SELECT lane_id, %s, %s, %s, 'gds_admin', %s, %s FROM core.lane WHERE lane_code = 'test'
               RETURNING tenant_id""",
            (code, code.title(), code.lower(), visibility, data_lake),
        )

    def user(name, tenant_id, mcp=False):
        principal_id = one(
            """INSERT INTO security.principal (principal_email, principal_display_name)
               VALUES (%s, %s) RETURNING principal_id""",
            (f"{name.lower()}@example.com", name),
        )
        conn.execute(
            """INSERT INTO security.tenant_principal_access
                   (tenant_id, principal_id, tenant_role, mcp_access_enabled, granted_by_principal_id)
               VALUES (%s, %s, 'viewer', %s, %s)""",
            (tenant_id, principal_id, mcp, demo.sam),
        )
        return principal_id

    system_type = one(
        "INSERT INTO reference.system_type (system_type_code, system_type_name) VALUES ('db', 'Database') "
        "RETURNING system_type_id"
    )
    connection_type = one(
        "INSERT INTO reference.connection_type (connection_type_code, connection_type_name) VALUES ('jdbc', 'JDBC') "
        "RETURNING connection_type_id"
    )
    table_type = one(
        "INSERT INTO reference.object_type (object_type_code, object_type_name) VALUES ('table', 'Table') "
        "RETURNING object_type_id"
    )
    zone = dict(conn.execute("SELECT lower(zone_code), zone_id FROM reference.zone").fetchall())

    def connection(tenant_id, code):
        system_id = one(
            """INSERT INTO core.system (system_type_id, system_code, system_name)
               VALUES (%s, %s, %s) RETURNING system_id""",
            (system_type, code.upper(), code),
        )
        return one(
            """INSERT INTO core.connection (tenant_id, system_id, connection_type_id, connection_code, connection_name)
               VALUES (%s, %s, %s, %s, %s) RETURNING connection_id""",
            (tenant_id, system_id, connection_type, code, code),
        )

    def table(connection_id, source_tenant_id, zone_code, schema, name, active=True):
        return one(
            """INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema,
                                        object_name, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING object_id""",
            (connection_id, source_tenant_id, table_type, zone[zone_code], schema, name, active),
        )

    c = SimpleNamespace(conn=conn, demo=demo, table=table, connection=connection)
    c.erp = tenant("ERP")
    c.gds = tenant("GDS", data_lake=True)
    c.erp_db = connection(c.erp, "erp_db")
    c.gds_us = connection(c.gds, "gds_us")
    conn.execute("UPDATE core.tenant SET data_lake_connection_id = %s WHERE tenant_id = %s", (c.gds_us, c.erp))
    c.eve = user("Eve", c.erp)
    c.gus = user("Gus", c.gds)

    c.erp_source = table(c.erp_db, c.erp, "source", "sap", "VBAK")
    c.erp_bronze = table(c.gds_us, c.erp, "bronze", "bronze_erp", "orders")
    c.erp_silver = table(c.gds_us, c.erp, "silver", "silver_erp", "order")
    c.erp_gold = table(c.gds_us, c.erp, "gold", "gold_erp", "fact_order")
    c.shared_bronze = table(c.gds_us, demo.shared, "bronze", "bronze_shared", "calendar")
    c.fabrikam_bronze = table(c.gds_us, demo.fabrikam, "bronze", "bronze_hr", "employees")
    return c
