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
- GDS_MCP_PUBLIC_URL: the server's own address ending in /mcp; its host is the only one the server answers to.
- GDS_ENTRA_TENANT_ID: on Azure, a sign-in from any other Microsoft tenant is refused.
- GDS_LOCAL_PRINCIPAL_OBJECT_ID: local only, the user you are.
v2's other GDS_* settings may stay on the portal; they are not used yet and not refused.
"""

import base64
import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from core import access, projects
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


# --- Health --------------------------------------------------------------------------------------------------------


@server.custom_route("/health", methods=["GET"])
async def health(request: Request):
    """Up, and which build: version.txt is written by scripts/build.py (step 5); running from the repo it is 'local'."""
    version_file = HERE / "version.txt"
    version = version_file.read_text().strip() if version_file.exists() else "local"
    return JSONResponse({"status": "ok", "version": version, "environment": os.environ.get("GDS_ENVIRONMENT", "")})


# --- Tools ---------------------------------------------------------------------------------------------------------


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
