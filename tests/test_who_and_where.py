"""Tests for finding the signed-in user and listing the tenants they can read (core/access.py, step 4a2).

People and tenants come from the `demo` fixture in conftest.py: Asha (Viewer), Ben (Developer, also in Shared) and
Cara (Tenant Admin) in Contoso, Sam the Super Admin, Olly with no membership, Ina switched off. Contoso and Fabrikam
are private, Shared is global.
"""

import pytest

from core.access import find_user, my_tenants
from core.problems import Refused


def test_find_user_ignores_case_and_outer_spaces(demo):
    user = find_user(demo.conn, "  Ben@Contoso.COM ")
    assert (user.principal_id, user.display_name, user.is_super_admin) == (demo.ben, "Ben", False)


def test_find_user_does_not_find_a_switched_off_or_unknown_user(demo):
    assert find_user(demo.conn, "ina@contoso.com") is None
    assert find_user(demo.conn, "nobody@contoso.com") is None
    assert find_user(demo.conn, "") is None


def tenants(conn, principal_id):
    return [(t.tenant_code, t.role) for t in my_tenants(conn, principal_id)]


def test_member_sees_own_tenant_and_global_tenants_with_their_role(demo):
    assert tenants(demo.conn, demo.asha) == [("CONTOSO", "viewer"), ("SHARED", "viewer")]
    assert tenants(demo.conn, demo.ben) == [("CONTOSO", "developer"), ("SHARED", "developer")]


def test_someone_with_no_membership_sees_only_global_tenants(demo):
    assert tenants(demo.conn, demo.olly) == [("SHARED", "viewer")]


def test_super_admin_sees_every_tenant_as_tenant_admin(demo):
    assert tenants(demo.conn, demo.sam) == [
        ("CONTOSO", "tenant_admin"), ("FABRIKAM", "tenant_admin"), ("SHARED", "tenant_admin")
    ]


def test_a_switched_off_tenant_is_not_listed(demo):
    demo.conn.execute("UPDATE core.tenant SET is_active = FALSE WHERE tenant_id = %s", (demo.shared,))
    assert tenants(demo.conn, demo.olly) == []


def test_a_switched_off_user_is_refused(demo):
    with pytest.raises(Refused) as info:
        my_tenants(demo.conn, demo.ina)
    assert info.value.rule_id == "ACCESS-001"


def test_each_tenant_says_what_your_role_may_do(demo):
    permissions = {t.tenant_code: t.permissions for t in my_tenants(demo.conn, demo.cara)}
    assert permissions == {"CONTOSO": ["CHANGE", "MANAGE_TENANT", "READ"], "SHARED": ["READ"]}
