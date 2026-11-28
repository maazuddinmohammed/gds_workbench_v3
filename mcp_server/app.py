"""The MCP server, deployed on Azure App Service (step 4b). AI tools in VS Code call it; the Bridge will too (4c).

Every tool is a thin door into core/, like the web app's routes: it finds who you are, calls one core/ function with
`via_mcp=True`, and returns its answer. No tool checks roles or locks itself; the core/ function calls `require`.

Who you are: on Azure, App Service sign-in checks the Microsoft token and sends the person's claims in the
`X-MS-CLIENT-PRINCIPAL` header (App Service removes one a caller sends). We take the object ID (`oid`) and find the
user with `core.access.find_user_by_object_id`, as v2 did. Locally there is no App Service, so
GDS_LOCAL_PRINCIPAL_OBJECT_ID says which user you are (the demo users' IDs are in database/demo/01_access.sql).

Settings (v2's names, kept so the App Service settings on the portal stay as they are):
- GDS_ENVIRONMENT: `local` or `production` (required).
- GDS_DATABASE_DSN: the Postgres connection (required).
- GDS_MCP_PUBLIC_URL: the server's own address ending in /mcp; its host is the only one the server answers to, and
  it is the address VS Code signs in for.
- GDS_ENTRA_TENANT_ID: the Microsoft tenant people sign in with; a sign-in from any other tenant is refused.
- GDS_LOCAL_PRINCIPAL_OBJECT_ID: local only, the user you are.
v2's other GDS_* settings may stay on the portal; they are not used yet and not refused.
"""

import base64
import json
import os
from dataclasses import asdict
from datetime import timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from core import access, projects, tenant_lock
from core.problems import NotFound, Refused

HERE = Path(__file__).resolve().parent

server = MCPServer(
    name="GDS Workbench",
    instructions="Read and change GDS Workbench projects. Every change goes into a draft that a person applies.",
)


# --- Settings, connection and sign-in ------------------------------------------------------------------------------


def setting(name, required=True):
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise RuntimeError(f"{name} is not set")
    return value


def is_local():
    environment = setting("GDS_ENVIRONMENT")
    if environment not in ("local", "production"):
        raise RuntimeError("GDS_ENVIRONMENT must be local or production")
    return environment == "local"


def open_database():
    """One autocommit connection per tool call, so each core/ call is its own transaction (docs/design.md)."""
    return psycopg.connect(setting("GDS_DATABASE_DSN"), autocommit=True)


class NotSignedIn(Exception):
    pass


def object_id_from_headers(headers):
    """The signed-in person's Microsoft object ID: from App Service sign-in on Azure, from the setting locally."""
    if is_local():
        return setting("GDS_LOCAL_PRINCIPAL_OBJECT_ID")
    encoded = {key.lower(): value for key, value in (headers or {}).items()}.get("x-ms-client-principal")
    if not encoded:
        raise NotSignedIn()
    try:
        claims = json.loads(base64.b64decode(encoded))["claims"]
    except (ValueError, KeyError, TypeError) as exc:
        raise NotSignedIn() from exc
    values = {}
    for claim in claims:
        typ = claim.get("typ", "")
        values[typ.rsplit("/", 1)[-1]] = claim.get("val", "")  # long Microsoft names end in tenantid, objectidentifier
    tenant = values.get("tid") or values.get("tenantid")
    if tenant != setting("GDS_ENTRA_TENANT_ID"):
        raise NotSignedIn()
    return values.get("oid") or values.get("objectidentifier") or ""


def signed_in(conn, ctx):
    """The signed-in user. What they may do is decided by `require` in each core/ call."""
    try:
        user = access.find_user_by_object_id(conn, object_id_from_headers(ctx.headers) or None)
    except psycopg.errors.InvalidTextRepresentation:  # not a UUID
        user = None
    if user is None:
        raise NotSignedIn()
    return user


def call_core(ctx, work):
    """Open a connection, find the user, run `work(conn, user)`; refusals become tool errors naming the rule ID."""
    try:
        with open_database() as conn:
            return work(conn, signed_in(conn, ctx))
    except NotSignedIn:
        raise ToolError("You are not signed in, or your user is switched off or unknown.") from None
    except (NotFound, Refused) as exc:
        raise ToolError(f"{exc.rule_id}: {exc.message}") from None


# --- Addresses open without sign-in -------------------------------------------------------------------------------
# On Azure, App Service sign-in lets only these through without a token (v2's "excluded paths" on the portal), so
# they keep v2's addresses and answers.


def build_version():
    """version.txt is written by scripts/build.py (step 5); running from the repo it is 'local'."""
    version_file = HERE / "version.txt"
    return version_file.read_text().strip() if version_file.exists() else "local"


@server.custom_route("/health/live", methods=["GET"])
async def health_live(request: Request):
    """The server is up, and which build."""
    return JSONResponse({"status": "live", "version": build_version(), "environment": setting("GDS_ENVIRONMENT")},
                        headers={"Cache-Control": "no-store"})


@server.custom_route("/health/ready", methods=["GET"])
async def health_ready(request: Request):
    """The server can reach its database (503 if not). Says nothing about who may do what."""
    try:
        with open_database() as conn:
            conn.execute("SELECT 1")
    except Exception:
        return JSONResponse({"status": "not_ready", "version": build_version()}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "ready", "version": build_version()}, headers={"Cache-Control": "no-store"})


async def oauth_protected_resource(request: Request):
    """How VS Code signs in: with Microsoft, for this server's address and v2's `workbench.access` scope.

    The same answer as v2, so the app registration in Entra (Application ID URI = GDS_MCP_PUBLIC_URL, scope
    workbench.access) works unchanged.
    """
    public_url = setting("GDS_MCP_PUBLIC_URL")
    return JSONResponse(
        {
            "resource": public_url,
            "authorization_servers": [f"https://login.microsoftonline.com/{setting('GDS_ENTRA_TENANT_ID')}/v2.0"],
            "scopes_supported": [f"{public_url}/workbench.access"],
            "bearer_methods_supported": ["header"],
        },
        headers={"Cache-Control": "public, max-age=300"},
    )


server.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(oauth_protected_resource)
server.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])(oauth_protected_resource)


# --- Tools ---------------------------------------------------------------------------------------------------------


def utc(moment):
    """A time as the tools write it: 2026-11-21T14:30:00Z."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def lock_answer(tenant_code, lock, user):
    if lock is None:
        return {"tenant_code": tenant_code, "is_locked": False}
    return {
        "tenant_code": tenant_code,
        "is_locked": True,
        "locked_by_display_name": lock.locked_by_display_name,
        "is_yours": lock.locked_by_principal_id == user.principal_id,
        "tenant_lock_purpose": lock.purpose,
        "tenant_lock_acquired_time": utc(lock.acquired_time),
        "tenant_lock_expires_time": utc(lock.expires_time),
    }


@server.tool()
def list_tenants(ctx: Context) -> dict:
    """Used for: picking the tenant to work in, and knowing before anything else what you may do there: your role,
    whether MCP access is on, whether the catalog can be changed, and where the tenant's data sits in Databricks."""

    def work(conn, user):
        tenants = []
        for t in access.my_tenants(conn, user.principal_id):
            row = asdict(t)
            row.pop("tenant_id")
            row["tenant_role"] = row.pop("role")
            tenants.append(row)
        return {
            "user": {"principal_display_name": user.display_name, "principal_email": user.email,
                     "is_super_admin": user.is_super_admin},
            "tenants": tenants,
        }

    return call_core(ctx, work)


@server.tool()
def list_projects(tenant_code: str, ctx: Context) -> dict:
    """Used for: picking the project, and seeing at once whether it is locked. Only active projects are listed."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        found = projects.list_projects(conn, user.principal_id, tenant_id, via_mcp=True)
        return {"tenant_code": tenant_code,
                "projects": [{k: v for k, v in asdict(p).items() if k != "project_id"} for p in found]}

    return call_core(ctx, work)


@server.tool()
def get_project_detail(tenant_code: str, project_name: str, ctx: Context) -> dict:
    """Used for: knowing how to model in this project before touching anything (schemas, naming, SCD type, audit
    columns, whether samples may be stored), seeing how far the project is (row_counts: active rows per part), and
    checking whether pulled files are still current (project_version)."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        project_id = projects.find_project(conn, user.principal_id, tenant_id, project_name, via_mcp=True)
        return projects.get_project_detail(conn, user.principal_id, project_id, via_mcp=True)

    return call_core(ctx, work)


@server.tool()
def check_tenant_lock(tenant_code: str, ctx: Context) -> dict:
    """Used for: seeing whether you can change things now, and if not, who to ask and how long to wait.
    A lock whose time has run out counts as free."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        return lock_answer(tenant_code, tenant_lock.current_lock(conn, user.principal_id, tenant_id, via_mcp=True), user)

    return call_core(ctx, work)


@server.tool()
def acquire_tenant_lock(tenant_code: str, ctx: Context, minutes: int = tenant_lock.DEFAULT_MINUTES,
                        tenant_lock_purpose: str | None = None) -> dict:
    """Used for: holding the tenant while you push, validate and apply. minutes is 1 to 240 (60 if left out).
    Acquiring again while you hold it starts your time over. Refused with ACCESS-003 and their name if someone else
    holds it; it never takes the lock from them."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        lock = tenant_lock.take_lock(conn, user.principal_id, tenant_id, minutes, tenant_lock_purpose, via_mcp=True)
        return lock_answer(tenant_code, lock, user)

    return call_core(ctx, work)


@server.tool()
def release_tenant_lock(tenant_code: str, ctx: Context) -> dict:
    """Used for: freeing the tenant when you are done. Only your own lock: someone else's is refused (ACCESS-003);
    ending theirs is override_tenant_lock, after the person agrees in chat."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        return {"tenant_code": tenant_code,
                "released": tenant_lock.release_lock(conn, user.principal_id, tenant_id, via_mcp=True)}

    return call_core(ctx, work)


@server.tool()
def override_tenant_lock(tenant_code: str, ctx: Context) -> dict:
    """Used for: ending a lock someone left behind, only after the person has agreed to it in chat. It does not give
    you the lock: acquire it as a separate step."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        ended = tenant_lock.override_lock(conn, user.principal_id, tenant_id, via_mcp=True)
        if ended is None:
            return {"tenant_code": tenant_code, "overridden": False}
        return {"tenant_code": tenant_code, "overridden": True,
                "was_locked_by_display_name": ended.locked_by_display_name,
                "tenant_lock_purpose": ended.purpose, "tenant_lock_expires_time": utc(ended.expires_time)}

    return call_core(ctx, work)


@server.tool()
def see_project_scope(project_id: int, ctx: Context, include_switched_off: bool = False) -> list[dict]:
    """The Source and Bronze tables in a project's scope (the tables its work may use), in zone, schema, name order.

    Each table is named by its row key: tenant_code, system_code, connection_code, object_schema, object_name.
    Tables taken out of scope show only when include_switched_off is true. Needs read access to the project.
    """
    return call_core(
        ctx,
        lambda conn, user: [
            asdict(row)
            for row in projects.current_scope(conn, user.principal_id, project_id, include_switched_off, via_mcp=True)
        ],
    )


# --- The app App Service runs (startup.sh: gunicorn app:app) ------------------------------------------------------


def allowed_hosts():
    """Only the server's own host (from GDS_MCP_PUBLIC_URL), plus this computer when local."""
    hosts = []
    public_url = os.environ.get("GDS_MCP_PUBLIC_URL", "").strip()
    if public_url:
        host = urlsplit(public_url).hostname
        hosts += [host, f"{host}:*"]
    if os.environ.get("GDS_ENVIRONMENT", "").strip() == "local":
        hosts += ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"]
    return hosts


def create_app():
    """A fresh app (an app can run only once, so each test makes its own). Stateless: each call stands alone."""
    return server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts(), allowed_origins=[]),
    )


app = create_app()
