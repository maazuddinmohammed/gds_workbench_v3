"""Who may read and change what.

Every web route, MCP tool and Bridge call starts with `require(...)`. It makes the access checks in a fixed order
and stops at the first one that fails. The rules are in docs/rules/access.md and docs/rules/change-sets.md, and the
flow is in design/shared/access.md.

Each check is one small function named after its rule ID (for example `access_001`), so a failing check is easy to
find from the problem it shows. `core/` never opens a database connection itself: the caller passes one in.
"""

from dataclasses import dataclass

from psycopg.rows import dict_row

from core.problems import NotFound, Refused

# The three permissions.
READ = "READ"
CHANGE = "CHANGE"
MANAGE_TENANT = "MANAGE_TENANT"

# What each role may do. Changing a role means changing this map only; no route changes.
ROLE_PERMISSIONS = {
    "viewer": {READ},
    "developer": {READ, CHANGE},
    "tenant_admin": {READ, CHANGE, MANAGE_TENANT},
}

# How each role is named to people, for messages such as "needs Developer".
ROLE_NAMES = {"viewer": "Viewer", "developer": "Developer", "tenant_admin": "Tenant Admin"}


@dataclass(frozen=True)
class Access:
    """What `require` found out: who is asking, in which tenant (and project), with which role."""

    principal_id: int
    tenant_id: int
    role: str
    project_id: int | None = None


def require(conn, principal_id, tenant_id, permission, project_id=None, via_mcp=False, taking_lock=False):
    """Check that a user may do something in a tenant, or raise `NotFound` / `Refused` naming the rule.

    - `permission` is READ, CHANGE or MANAGE_TENANT.
    - `project_id` is given when the action is about one project. It must belong to the tenant.
    - `via_mcp` is True only in the MCP server's code (MCP tools and the Bridge), never read from the request.
    - `taking_lock` is True only when the call is taking the tenant lock itself, which cannot need the lock.

    Returns an `Access` with the user's role in the tenant.
    """
    if permission not in (READ, CHANGE, MANAGE_TENANT):
        raise ValueError(f"unknown permission: {permission}")

    with conn.cursor(row_factory=dict_row) as cur:
        user = _load_user(cur, principal_id)
        tenant = _load_tenant(cur, tenant_id)
        member = _load_membership(cur, tenant_id, principal_id)
        project = _load_project(cur, project_id) if project_id is not None else None

        # 1 and 2. The user is active and can read the tenant (and the project is in it).
        role = access_001(user, tenant, member, project)
        # 3. MCP access, only for calls through the MCP server.
        if via_mcp:
            access_004(user, tenant, member)
        # 4. The role has the permission.
        access_002(role, permission)

        if permission == CHANGE and not taking_lock:
            # 5. You hold the tenant lock.
            access_003(_load_tenant_lock(cur, tenant_id), principal_id, tenant)
            # 6. The project, or the catalog, is not switched to read-only.
            if project is not None:
                change_set_004(project)
            else:
                change_set_011(tenant)

    return Access(principal_id=principal_id, tenant_id=tenant_id, role=role, project_id=project_id)


# --- Who you are and where you can go ------------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    """A signed-in person, as the apps show them."""

    principal_id: int
    email: str
    display_name: str
    is_super_admin: bool


@dataclass(frozen=True)
class MyTenant:
    """A tenant you can read, and your role in it."""

    tenant_id: int
    tenant_code: str
    tenant_name: str
    tenant_visibility: str
    is_data_lake: bool
    role: str
    permissions: list[str]  # what the role may do (ROLE_PERMISSIONS), so the apps can offer only what you may do


def find_user(conn, email):
    """The active user with this email (any upper or lower case), or None.

    This is how the web app turns the email from the Databricks sign-in into a user. It checks nothing else: what
    the user may do is decided by `require` on every call.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT principal_id, principal_email, principal_display_name, is_super_admin
                 FROM security.principal WHERE principal_email = lower(btrim(%s)) AND is_active""",
            (email or "",),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return User(row["principal_id"], row["principal_email"], row["principal_display_name"], row["is_super_admin"])


def my_tenants(conn, principal_id):
    """Every active tenant you can read (ACCESS-001), by name, with your role in each.

    That is your memberships and every global tenant; a Super Admin reads every tenant. Your role in each comes
    from `require`, so the role rules exist once. A user that is switched off is refused (ACCESS-001).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        _active(_load_user(cur, principal_id))
        cur.execute(
            """SELECT t.tenant_id, t.tenant_code, t.tenant_name, t.tenant_visibility, t.is_data_lake
                 FROM core.tenant AS t
                WHERE t.is_active
                  AND (t.tenant_visibility = 'global'
                       OR EXISTS (SELECT 1 FROM security.tenant_principal_access AS a
                                   WHERE a.tenant_id = t.tenant_id AND a.principal_id = %(p)s)
                       OR EXISTS (SELECT 1 FROM security.principal AS u
                                   WHERE u.principal_id = %(p)s AND u.is_super_admin))
                ORDER BY lower(t.tenant_name), t.tenant_id""",
            {"p": principal_id},
        )
        rows = cur.fetchall()
    tenants = []
    for row in rows:
        role = require(conn, principal_id, row["tenant_id"], READ).role
        tenants.append(MyTenant(**row, role=role, permissions=sorted(ROLE_PERMISSIONS[role])))
    return tenants


# --- The checks, one per rule --------------------------------------------------------------------------------------


def access_001(user, tenant, member, project):
    """ACCESS-001: you can only see a tenant you have access to. Returns your role in it.

    A user that is switched off is refused. A tenant you cannot read, or a project that is not in the tenant,
    gives "not found", so an outsider cannot tell that it exists.
    """
    _active(user)
    if tenant is None or not tenant["is_active"]:
        raise NotFound("ACCESS-001", "Tenant not found.")

    if user["is_super_admin"]:
        role = "tenant_admin"  # a Super Admin counts as a Tenant Admin in every tenant
    elif member is not None:
        role = member["tenant_role"]  # a member keeps their own role, in a global tenant too
    elif tenant["tenant_visibility"] == "global":
        role = "viewer"  # anyone signed in is a Viewer in a global tenant
    else:
        raise NotFound("ACCESS-001", "Tenant not found.")

    if project is not None and project["tenant_id"] != tenant["tenant_id"]:
        raise NotFound("ACCESS-001", "Project not found.")
    return role


def _active(user):
    """Part of ACCESS-001: a user that is switched off, or does not exist, may do nothing."""
    if user is None or not user["is_active"]:
        raise Refused("ACCESS-001", "Your user is switched off or does not exist.")


def access_002(role, permission):
    """ACCESS-002: every action needs a role that is allowed to do it."""
    if permission not in ROLE_PERMISSIONS[role]:
        needed = next(r for r, perms in ROLE_PERMISSIONS.items() if permission in perms)
        raise Refused("ACCESS-002", f"This needs {ROLE_NAMES[needed]}. You are {ROLE_NAMES[role]}.")


def access_003(lock, principal_id, tenant):
    """ACCESS-003: every change needs the tenant lock, and you must hold it.

    `lock` is the tenant's lock row if it has not ended yet, otherwise None. Super Admins follow this too.
    """
    if lock is None:
        raise Refused("ACCESS-003", f"Take the lock on {tenant['tenant_name']} first.")
    if lock["locked_by_principal_id"] != principal_id:
        until = lock["tenant_lock_expires_time"].strftime("%Y-%m-%d %H:%M %Z")
        raise Refused(
            "ACCESS-003",
            f"{tenant['tenant_name']} is locked by {lock['locked_by_display_name']} until {until}.",
        )


def access_004(user, tenant, member):
    """ACCESS-004: the MCP server and the Bridge need MCP access in that tenant.

    Every role needs the switch on its membership. Super Admins always have it. Someone who reads a global tenant
    without being a member has no membership, so no switch.
    """
    if user["is_super_admin"]:
        return
    if member is None or not member["mcp_access_enabled"]:
        raise Refused(
            "ACCESS-004",
            f"You do not have MCP access in {tenant['tenant_name']}. Ask a Tenant Admin, or use the web app.",
        )


def change_set_004(project):
    """CHANGE-SET-004: a locked project cannot change."""
    if project["is_locked"]:
        raise Refused("CHANGE-SET-004", f"{project['project_name']} is locked. Ask a Tenant Admin to unlock it.")


def change_set_011(tenant):
    """CHANGE-SET-011: a locked catalog cannot change."""
    if tenant["is_metadata_locked"]:
        raise Refused(
            "CHANGE-SET-011", f"{tenant['tenant_name']}'s catalog is locked. Ask a Tenant Admin to unlock it."
        )


# --- Reading the rows the checks need ------------------------------------------------------------------------------


def _load_user(cur, principal_id):
    cur.execute(
        "SELECT principal_id, is_active, is_super_admin FROM security.principal WHERE principal_id = %s",
        (principal_id,),
    )
    return cur.fetchone()


def _load_tenant(cur, tenant_id):
    cur.execute(
        """SELECT tenant_id, tenant_name, tenant_visibility, is_metadata_locked, is_active
             FROM core.tenant WHERE tenant_id = %s""",
        (tenant_id,),
    )
    return cur.fetchone()


def _load_membership(cur, tenant_id, principal_id):
    cur.execute(
        """SELECT tenant_role, mcp_access_enabled FROM security.tenant_principal_access
            WHERE tenant_id = %s AND principal_id = %s""",
        (tenant_id, principal_id),
    )
    return cur.fetchone()


def _load_project(cur, project_id):
    cur.execute(
        "SELECT project_id, tenant_id, project_name, is_locked FROM project.project WHERE project_id = %s",
        (project_id,),
    )
    return cur.fetchone()


def _load_tenant_lock(cur, tenant_id):
    """The tenant's lock if it has not ended yet. A lock past its end time counts as no lock."""
    cur.execute(
        """SELECT l.locked_by_principal_id, l.tenant_lock_expires_time, p.principal_display_name AS locked_by_display_name
             FROM security.tenant_lock AS l
             JOIN security.principal AS p ON p.principal_id = l.locked_by_principal_id
            WHERE l.tenant_id = %s AND l.tenant_lock_expires_time > CURRENT_TIMESTAMP""",
        (tenant_id,),
    )
    return cur.fetchone()
