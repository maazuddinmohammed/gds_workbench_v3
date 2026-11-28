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
import threading
import urllib.parse
import urllib.request
from datetime import datetime
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

from core import access, change_sets, profiling, projects, runs, snapshot, storage, tenant_lock
from core.parts import PARTS
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


# --- Change sets (design/operations/change-sets.md). Only the project kind is built so far. -----------------------


def project_kind(kind):
    if kind != "project":
        raise ToolError("Only kind \"project\" is built so far; metadata change sets come with the metadata snapshot.")


def row_key(conn, change_set_id, problem):
    """The names of the record a problem is about, so the AI can find it without counting."""
    if problem.part is None or problem.record is None:
        return None
    document = conn.execute(f"SELECT {problem.part}_document FROM application.project_change_set "
                            "WHERE project_change_set_id = %s", (change_set_id,)).fetchone()[0]
    record = document[problem.record] if problem.record < len(document) else {}
    return {f: record.get(f) for f in PARTS[problem.part].key_fields}


def problems_answer(conn, change_set_id, found):
    return [{"rule_id": p.rule_id, "level": p.level, "message": p.message, "part": p.part, "record": p.record,
             "row_key": row_key(conn, change_set_id, p), "file": None, "line": None} for p in found]


def change_set_summary(summary):
    return {"kind": "project", **{k: (utc(v) if k.endswith("_time") else v) for k, v in summary.items()}}


@server.tool()
def validate_change_set(kind: str, change_set_id: int, ctx: Context) -> dict:
    """Used for: finding out what must be fixed before Apply, problem by problem, each with its rule ID, level
    (blocks_apply or warning), the part and record it is about and that record's row key. Changes nothing."""
    project_kind(kind)

    def work(conn, user):
        found = change_sets.validate(conn, user.principal_id, change_set_id, via_mcp=True)
        status = change_sets.get_change_set(conn, user.principal_id, change_set_id, via_mcp=True)["project_change_set_status"]
        return {"kind": kind, "project_change_set_id": change_set_id, "project_change_set_status": status,
                "upload_number": None, "can_apply": not any(p.level == "blocks_apply" for p in found),
                "problems": problems_answer(conn, change_set_id, found)}

    return call_core(ctx, work)


@server.tool()
def get_change_set(kind: str, change_set_id: int, ctx: Context) -> dict:
    """Used for: seeing where a change set stands: status, who made it and how (vscode_push, ai_run or web_app_edit),
    the version it was built on next to the project's version now, and for each part how many records add, change,
    switch off or leave a row unchanged. It does not return problems: that is validate_change_set."""
    project_kind(kind)
    return call_core(ctx, lambda conn, user: change_set_summary(
        change_sets.get_change_set(conn, user.principal_id, change_set_id, via_mcp=True)))


@server.tool()
def list_change_set_changes(kind: str, change_set_id: int, part: str, ctx: Context, change: str | None = None,
                            page: int = 1) -> dict:
    """Used for: reviewing what will actually change, record by record, before the person says yes. `part` is one
    of the parts get_change_set counts; `change` optionally keeps added, changed or switched_off. Each change has the
    record and, for a changed or switched-off one, what is saved now (`current`). 50 per page."""
    project_kind(kind)
    return call_core(ctx, lambda conn, user: {"kind": kind, "project_change_set_id": change_set_id, **change_sets.list_changes(
        conn, user.principal_id, change_set_id, part, change, page, via_mcp=True)})


@server.tool()
def list_change_sets(kind: str, tenant_code: str, ctx: Context, project_name: str | None = None,
                     status: str | None = None) -> dict:
    """Used for: finding a change set again, and seeing whether a draft is already waiting before starting another.
    The 5 newest, newest first; `total` says how many match in all. `status` is optional (receiving, draft, applied,
    rejected)."""
    project_kind(kind)

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        project_id = projects.find_project(conn, user.principal_id, tenant_id, project_name, via_mcp=True) if project_name else None
        found = change_sets.list_change_sets(conn, user.principal_id, tenant_id, project_id, status, via_mcp=True)
        return {"kind": kind, "tenant_code": tenant_code, "project_name": project_name, "total": len(found),
                "change_sets": [{k: (utc(v) if k.endswith("_time") else v) for k, v in c.items()} for c in found[:5]]}

    return call_core(ctx, work)


@server.tool()
def apply_change_set(kind: str, change_set_id: int, ctx: Context, upload_number: int | None = None) -> dict:
    """Used for: saving the change set, only after the person said yes in chat. All of it is saved, or nothing; the
    project version goes up by one. When problems block it, they come back and nothing changes."""
    project_kind(kind)

    def work(conn, user):
        found = change_sets.apply(conn, user.principal_id, change_set_id, via_mcp=True)
        summary = change_sets.get_change_set(conn, user.principal_id, change_set_id, via_mcp=True)
        answer = {"kind": kind, "project_change_set_id": change_set_id, "applied": not found,
                  "project_change_set_status": summary["project_change_set_status"]}
        if found:
            return answer | {"problems": problems_answer(conn, change_set_id, found)}
        return answer | {"project_version": summary["project_version"]}

    return call_core(ctx, work)


@server.tool()
def reject_change_set(kind: str, change_set_id: int, ctx: Context) -> dict:
    """Used for: clearing away a change set that is not wanted, also one that was started and never loaded."""
    project_kind(kind)

    def work(conn, user):
        found = change_sets.reject(conn, user.principal_id, change_set_id, via_mcp=True)
        if found:
            return {"kind": kind, "project_change_set_id": change_set_id, "rejected": False,
                    "problems": problems_answer(conn, change_set_id, found)}
        return {"kind": kind, "project_change_set_id": change_set_id, "rejected": True,
                "project_change_set_status": "rejected"}

    return call_core(ctx, work)


# --- Snapshots and pushes (the Bridge). Not tried against Azure storage yet. ----------------------------------------


def where():
    """Azure storage, as v2 set it up: the account, the container, and the managed identity's token."""
    def token():
        query = urllib.parse.urlencode({"resource": "https://storage.azure.com/", "api-version": "2019-08-01",
                                        "client_id": setting("GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID")})
        request = urllib.request.Request(f"{setting('IDENTITY_ENDPOINT')}?{query}",
                                         headers={"X-IDENTITY-HEADER": setting("IDENTITY_HEADER")})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["access_token"]

    return {"account_url": setting("GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL"),
            "container": setting("GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER"), "token": token}


def push_name(conn, change_set_id, upload_number):
    tenant, project = conn.execute(
        """SELECT t.tenant_code, p.project_name FROM application.project_change_set AS cs
             JOIN project.project AS p USING (project_id) JOIN core.tenant AS t ON t.tenant_id = p.tenant_id
            WHERE cs.project_change_set_id = %s""", (change_set_id,)).fetchone()
    return f"push/{tenant}/{project}/{datetime.now().strftime('%Y-%m-%d')}/{change_set_id}/upload-{upload_number}.zip"


@server.tool()
def create_snapshot(kind: str, tenant_code: str, project_name: str, ctx: Context) -> dict:
    """Used for: getting the link the helper script downloads (pull), and noting the version the files are at. The
    zip holds gds.json, README.md and scope.jsonl so far."""
    project_kind(kind)

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        project_id = projects.find_project(conn, user.principal_id, tenant_id, project_name, via_mcp=True)
        snapshot_id, version, data = snapshot.create(conn, user.principal_id, project_id, via_mcp=True)
        name = f"pull/{tenant_code}/{project_name}/{snapshot_id[:10]}/{snapshot_id}.zip"
        storage.put(where(), name, data)
        link, expires = storage.link(where(), name)
        return {"kind": kind, "snapshot_id": snapshot_id, "tenant_code": tenant_code, "project_name": project_name,
                "project_version": version, "download_link": link, "link_expires_time": utc(expires)}

    return call_core(ctx, work)


@server.tool()
def start_change_set(kind: str, tenant_code: str, project_name: str, title: str, ctx: Context) -> dict:
    """Used for: opening the one change set a push works through, and getting the first upload link."""
    project_kind(kind)

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        project_id = projects.find_project(conn, user.principal_id, tenant_id, project_name, via_mcp=True)
        change_set_id = snapshot.start(conn, user.principal_id, project_id, title, via_mcp=True)
        link, expires = storage.link(where(), push_name(conn, change_set_id, 1), write=True)
        return {"kind": kind, "project_change_set_id": change_set_id, "project_change_set_title": title,
                "project_change_set_status": "receiving", "upload_number": 1, "upload_link": link,
                "link_expires_time": utc(expires)}

    return call_core(ctx, work)


@server.tool()
def start_change_set_upload(kind: str, change_set_id: int, ctx: Context) -> dict:
    """Used for: sending the files again after fixing them, or when a link ran out before it was used."""
    project_kind(kind)

    def work(conn, user):
        number = snapshot.next_upload(conn, user.principal_id, change_set_id, via_mcp=True)
        link, expires = storage.link(where(), push_name(conn, change_set_id, number), write=True)
        return {"kind": kind, "project_change_set_id": change_set_id, "upload_number": number, "upload_link": link,
                "link_expires_time": utc(expires)}

    return call_core(ctx, work)


@server.tool()
def load_upload_into_change_set(kind: str, change_set_id: int, upload_number: int, ctx: Context) -> dict:
    """Used for: loading the file the helper script put in storage into the change set, all or nothing. Answers in
    numbers what the push would do. Refused when the files were pulled at an older project version."""
    project_kind(kind)

    def work(conn, user):
        data = storage.get(where(), push_name(conn, change_set_id, upload_number))
        summary = snapshot.load(conn, user.principal_id, change_set_id, upload_number, data, via_mcp=True)
        return {"kind": kind, "project_change_set_id": change_set_id,
                "project_change_set_status": summary["project_change_set_status"], "upload_number": upload_number,
                "base_project_version": summary["base_project_version"], "counts": summary["counts"]}

    return call_core(ctx, work)


# --- Databricks (design/operations/databricks.md) ------------------------------------------------------------------


def secret(name):
    """A Key Vault secret's value: App Service puts Key Vault references in its settings, by name."""
    return os.environ[name]


def profiling_answer(conn, user, run_id):
    run = runs.get_run(conn, user.principal_id, run_id, via_mcp=True)
    done = sum(1 for e in run["events"] if e["run_event_stage"] == "profile")
    request = run["run_request_document"]
    total = conn.execute("""SELECT count(*) FROM project.project_input_scope WHERE project_id = %s AND is_active""",
                         (run["project_id"],)).fetchone()[0]
    version = conn.execute("SELECT project_version FROM project.project WHERE project_id = %s", (run["project_id"],)).fetchone()[0]
    return {"run_id": run_id, "project_workflow": "profiling", "run_status": run["run_status"],
            "run_request_document": request, "table_count": len(request.get("tables") or []) or total,
            "tables_done": done, "base_project_version": run["base_project_version"],
            "started_by_display_name": run["started_by_display_name"], "started_time": utc(run["started_time"]),
            "completed_time": utc(run["completed_time"]), "failure_message": run["failure_message"],
            "project_change_set_id": run["project_change_set_id"],
            "project_change_set_status": run["project_change_set_status"], "project_version": version}


@server.tool()
def start_profiling_run(tenant_code: str, project_name: str, ctx: Context, environment_code: str = "dev",
                        batch_ids: list[str] | None = None, tables: list[dict] | None = None) -> dict:
    """Used for: getting the column counts and sample values of the tables in scope, which every later step builds
    on. Leave `tables` out to profile every active table in scope; give each table by object_schema and object_name
    otherwise. A table with a batch column is measured only on `batch_ids` (1 to 2000). The server writes the
    queries; the Run applies its own change set. Needs the tenant lock. Follow it with get_profiling_run."""

    def work(conn, user):
        tenant_id = access.find_tenant(conn, user.principal_id, tenant_code, via_mcp=True)
        project_id = projects.find_project(conn, user.principal_id, tenant_id, project_name, via_mcp=True)
        request = {"environment_code": environment_code, "batch_ids": batch_ids or []}
        if tables:
            request["tables"] = [{"object_schema": t["object_schema"], "object_name": t["object_name"]} for t in tables]
        run_id = profiling.start_run(conn, user.principal_id, project_id, request, via_mcp=True)

        def execute():
            with open_database() as background:
                profiling.execute(background, run_id, secret)

        threading.Thread(target=execute, daemon=True).start()
        return profiling_answer(conn, user, run_id)

    return call_core(ctx, work)


@server.tool()
def get_profiling_run(run_id: int, ctx: Context) -> dict:
    """Used for: waiting for a profiling Run to finish, seeing how far it is (tables_done of table_count) or why it
    failed, and knowing the new project version when it is done."""
    return call_core(ctx, lambda conn, user: profiling_answer(conn, user, run_id))


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
