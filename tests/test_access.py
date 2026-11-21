"""Tests for core/access.py: the pass and fail examples of ACCESS-001 to 004, CHANGE-SET-004 and 011.

The people and tenants follow the examples in docs/rules/access.md: Asha (Viewer), Ben (Developer) and
Cara (Tenant Admin) in Contoso, Sam the Super Admin, Olly with no membership, and Ina who is switched off.
Contoso and Fabrikam are private, Shared is global.
"""

from types import SimpleNamespace

import pytest

from core.access import CHANGE, MANAGE_TENANT, READ, require
from core.problems import NotFound, Refused


@pytest.fixture
def demo(conn):
    """Small set of rows for the tests. Rolled back after each test."""

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


def refused(rule_id, call, kind=Refused):
    """Assert the call is refused by the given rule, and return the problem."""
    with pytest.raises(kind) as info:
        call()
    assert info.value.rule_id == rule_id
    return info.value


# --- ACCESS-001 · You can only see a tenant you have access to -----------------------------------------------------


def test_access_001_member_reads_own_tenant_and_project(demo):
    access = require(demo.conn, demo.asha, demo.contoso, READ, project_id=demo.retail)
    assert access.role == "viewer"


def test_access_001_anyone_reads_a_global_tenant_as_viewer(demo):
    assert require(demo.conn, demo.olly, demo.shared, READ).role == "viewer"


def test_access_001_member_keeps_own_role_in_a_global_tenant(demo):
    assert require(demo.conn, demo.ben, demo.shared, READ).role == "developer"


def test_access_001_super_admin_is_tenant_admin_everywhere(demo):
    assert require(demo.conn, demo.sam, demo.fabrikam, READ).role == "tenant_admin"


def test_access_001_other_private_tenant_is_not_found(demo):
    refused("ACCESS-001", lambda: require(demo.conn, demo.asha, demo.fabrikam, READ), NotFound)


def test_access_001_project_of_another_tenant_is_not_found(demo):
    refused("ACCESS-001", lambda: require(demo.conn, demo.asha, demo.contoso, READ, project_id=demo.hr), NotFound)


def test_access_001_switched_off_user_is_refused(demo):
    refused("ACCESS-001", lambda: require(demo.conn, demo.ina, demo.contoso, READ))


def test_access_001_switched_off_tenant_is_not_found(demo):
    demo.conn.execute("UPDATE core.tenant SET is_active = FALSE WHERE tenant_id = %s", (demo.contoso,))
    refused("ACCESS-001", lambda: require(demo.conn, demo.sam, demo.contoso, READ), NotFound)


def test_access_001_removed_member_is_not_found(demo):
    demo.conn.execute(
        "DELETE FROM security.tenant_principal_access WHERE tenant_id = %s AND principal_id = %s",
        (demo.contoso, demo.asha),
    )
    refused("ACCESS-001", lambda: require(demo.conn, demo.asha, demo.contoso, READ), NotFound)


# --- ACCESS-002 · Every action needs a role that is allowed to do it -----------------------------------------------


def test_access_002_viewer_cannot_change(demo):
    problem = refused("ACCESS-002", lambda: require(demo.conn, demo.asha, demo.contoso, CHANGE, demo.retail))
    assert "needs Developer" in problem.message


def test_access_002_developer_cannot_manage_tenant(demo):
    problem = refused("ACCESS-002", lambda: require(demo.conn, demo.ben, demo.contoso, MANAGE_TENANT))
    assert "needs Tenant Admin" in problem.message


def test_access_002_outsider_in_global_tenant_cannot_change(demo):
    refused("ACCESS-002", lambda: require(demo.conn, demo.olly, demo.shared, CHANGE, taking_lock=True))


def test_access_002_tenant_admin_manages_without_the_lock(demo):
    assert require(demo.conn, demo.cara, demo.contoso, MANAGE_TENANT).role == "tenant_admin"


# --- ACCESS-003 · Every change needs the tenant lock, and you must hold it -----------------------------------------


def test_access_003_developer_with_the_lock_can_change(demo):
    demo.lock(demo.contoso, demo.ben)
    assert require(demo.conn, demo.ben, demo.contoso, CHANGE, project_id=demo.retail).role == "developer"


def test_access_003_no_lock_means_take_it_first(demo):
    problem = refused("ACCESS-003", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, demo.retail))
    assert "Take the lock" in problem.message


def test_access_003_someone_else_holds_the_lock(demo):
    demo.lock(demo.contoso, demo.cara)
    problem = refused("ACCESS-003", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, demo.retail))
    assert "locked by Cara until" in problem.message


def test_access_003_an_ended_lock_counts_as_no_lock(demo):
    demo.lock(demo.contoso, demo.ben, minutes=-5)
    refused("ACCESS-003", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, demo.retail))


def test_access_003_super_admin_needs_the_lock_too(demo):
    refused("ACCESS-003", lambda: require(demo.conn, demo.sam, demo.contoso, CHANGE, demo.retail))


def test_access_003_taking_the_lock_does_not_need_the_lock(demo):
    assert require(demo.conn, demo.ben, demo.contoso, CHANGE, taking_lock=True).role == "developer"


def test_access_003_reading_does_not_need_the_lock(demo):
    demo.lock(demo.contoso, demo.cara)
    require(demo.conn, demo.ben, demo.contoso, READ, project_id=demo.retail)


# --- ACCESS-004 · The MCP server and the Bridge need MCP access in that tenant -------------------------------------


def test_access_004_member_with_mcp_access_can_use_mcp(demo):
    require(demo.conn, demo.ben, demo.contoso, READ, project_id=demo.retail, via_mcp=True)


def test_access_004_tenant_admin_without_mcp_access_is_refused(demo):
    refused("ACCESS-004", lambda: require(demo.conn, demo.cara, demo.contoso, READ, via_mcp=True))


def test_access_004_without_mcp_access_the_web_app_still_works(demo):
    require(demo.conn, demo.asha, demo.contoso, READ)
    refused("ACCESS-004", lambda: require(demo.conn, demo.asha, demo.contoso, READ, via_mcp=True))


def test_access_004_super_admin_always_has_mcp_access(demo):
    require(demo.conn, demo.sam, demo.contoso, READ, via_mcp=True)


def test_access_004_reader_of_a_global_tenant_has_no_mcp_access(demo):
    refused("ACCESS-004", lambda: require(demo.conn, demo.olly, demo.shared, READ, via_mcp=True))


def test_access_004_outsider_gets_not_found_before_mcp_refusal(demo):
    refused("ACCESS-001", lambda: require(demo.conn, demo.olly, demo.contoso, READ, via_mcp=True), NotFound)


# --- CHANGE-SET-004 and 011 · Locked projects and catalogs cannot change -------------------------------------------


def test_change_set_004_locked_project_cannot_change(demo):
    demo.lock(demo.contoso, demo.ben)
    demo.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (demo.retail,))
    problem = refused("CHANGE-SET-004", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, demo.retail))
    assert "Retail is locked" in problem.message


def test_change_set_004_locked_project_can_still_be_read(demo):
    demo.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (demo.retail,))
    require(demo.conn, demo.asha, demo.contoso, READ, project_id=demo.retail)


def test_change_set_011_locked_catalog_cannot_change(demo):
    demo.lock(demo.contoso, demo.ben)
    demo.conn.execute("UPDATE core.tenant SET is_metadata_locked = TRUE WHERE tenant_id = %s", (demo.contoso,))
    problem = refused("CHANGE-SET-011", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE))
    assert "Contoso's catalog is locked" in problem.message


def test_change_set_011_locked_catalog_leaves_project_work_alone(demo):
    demo.lock(demo.contoso, demo.ben)
    demo.conn.execute("UPDATE core.tenant SET is_metadata_locked = TRUE WHERE tenant_id = %s", (demo.contoso,))
    require(demo.conn, demo.ben, demo.contoso, CHANGE, project_id=demo.retail)


def test_tenant_admin_can_unlock_a_locked_project_without_the_lock(demo):
    demo.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (demo.retail,))
    require(demo.conn, demo.cara, demo.contoso, MANAGE_TENANT, project_id=demo.retail)
