"""The web app's backend (FastAPI), deployed as a Databricks App (step 4a2).

Every route is a thin door into core/: it finds who you are, calls one core/ function, and returns its answer as
JSON. No route checks roles or locks itself; the core/ function calls `require` first. The route test in
tests/test_web_app.py calls every route as an outsider and as a Viewer to prove none can skip it.

Who you are: Databricks Apps send the signed-in person's email in the `X-Forwarded-Email` header. Locally, the page's
"pick a demo user" sets the same header (scripts/run_local.py, step 4a3).

Answers when core/ says no: 401 when nobody is signed in or the email is not an active user, 404 for "not found"
(ACCESS-001), 403 for any other refusal, 422 for a request of the wrong shape. Each says the rule ID.

Settings (v2's names): GDS_WEB_DATABASE_DSN (required), GDS_WEB_ENVIRONMENT, GDS_WEB_STATIC_DIR (used in step 4a4).
"""

import os
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import access, catalog, project_change_sets, projects, tenant_lock
from core.problems import NotFound, Refused

HERE = Path(__file__).resolve().parent

app = FastAPI(title="GDS Workbench")


# --- Connection and sign-in ----------------------------------------------------------------------------------------


def database():
    """One autocommit connection per request, so each core/ call is its own transaction (docs/design.md)."""
    dsn = os.environ.get("GDS_WEB_DATABASE_DSN")
    if not dsn:
        raise RuntimeError("GDS_WEB_DATABASE_DSN is not set")
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


class NotSignedIn(Exception):
    pass


def signed_in(conn=Depends(database), x_forwarded_email: str | None = Header(default=None)):
    """The signed-in user, from the email Databricks Apps send. What they may do is decided by `require`."""
    user = access.find_user(conn, x_forwarded_email or "")
    if user is None:
        raise NotSignedIn()
    return user


@app.exception_handler(NotSignedIn)
def _not_signed_in(request: Request, exc: NotSignedIn):
    return JSONResponse(status_code=401, content={"message": "You are not signed in, or your user is switched off."})


@app.exception_handler(NotFound)
def _not_found(request: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"rule_id": exc.rule_id, "message": exc.message})


@app.exception_handler(Refused)
def _refused(request: Request, exc: Refused):
    return JSONResponse(status_code=403, content={"rule_id": exc.rule_id, "message": exc.message})


@app.exception_handler(ValueError)
def _bad_request(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"message": str(exc)})


# --- Routes --------------------------------------------------------------------------------------------------------


@app.get("/health")
def health():
    """Up, and which build: version.txt is written by scripts/build.py (step 5); running from the repo it is 'local'."""
    version_file = HERE / "version.txt"
    version = version_file.read_text().strip() if version_file.exists() else "local"
    return {"status": "ok", "version": version, "environment": os.environ.get("GDS_WEB_ENVIRONMENT", "local")}


@app.get("/api/me")
def me(user=Depends(signed_in), conn=Depends(database)):
    return {"user": user, "tenants": access.my_tenants(conn, user.principal_id)}


@app.get("/api/tenants/{tenant_id}/tables")
def tables(
    tenant_id: int,
    zones: list[str] | None = Query(default=None),
    scope_only: bool = False,
    include_switched_off: bool = False,
    page: int = 1,
    user=Depends(signed_in),
    conn=Depends(database),
):
    return catalog.list_tables(
        conn, user.principal_id, tenant_id, zones=zones, scope_only=scope_only,
        include_switched_off=include_switched_off, page=page,
    )


@app.get("/api/tenants/{tenant_id}/projects")
def tenant_projects(tenant_id: int, user=Depends(signed_in), conn=Depends(database)):
    return projects.list_projects(conn, user.principal_id, tenant_id)


@app.get("/api/tenants/{tenant_id}/lock")
def get_lock(tenant_id: int, user=Depends(signed_in), conn=Depends(database)):
    return {"lock": tenant_lock.current_lock(conn, user.principal_id, tenant_id)}


class TakeLock(BaseModel):
    minutes: int = tenant_lock.DEFAULT_MINUTES
    purpose: str | None = None


@app.post("/api/tenants/{tenant_id}/lock")
def take_lock(tenant_id: int, body: TakeLock, user=Depends(signed_in), conn=Depends(database)):
    return {"lock": tenant_lock.take_lock(conn, user.principal_id, tenant_id, body.minutes, body.purpose)}


@app.delete("/api/tenants/{tenant_id}/lock")
def release_lock(tenant_id: int, user=Depends(signed_in), conn=Depends(database)):
    """Release the lock, whoever holds it. The page asks "are you sure?" first when it is someone else's."""
    return {"released": tenant_lock.release_lock(conn, user.principal_id, tenant_id)}


@app.get("/api/projects/{project_id}/scope")
def scope(project_id: int, include_switched_off: bool = False, user=Depends(signed_in), conn=Depends(database)):
    return projects.current_scope(conn, user.principal_id, project_id, include_switched_off=include_switched_off)


class NewScopeDraft(BaseModel):
    title: str
    records: list[dict]


@app.post("/api/projects/{project_id}/scope-drafts", status_code=201)
def make_scope_draft(project_id: int, body: NewScopeDraft, user=Depends(signed_in), conn=Depends(database)):
    change_set_id = project_change_sets.make_scope_draft(conn, user.principal_id, project_id, body.records, body.title)
    return {"change_set_id": change_set_id}


@app.get("/api/scope-drafts/{change_set_id}")
def read_scope_draft(change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    return project_change_sets.read_scope_draft(conn, user.principal_id, change_set_id)


@app.post("/api/scope-drafts/{change_set_id}/apply")
def apply_scope_draft(change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    problems = project_change_sets.apply_scope_draft(conn, user.principal_id, change_set_id)
    return {"applied": not problems, "problems": problems}


@app.post("/api/scope-drafts/{change_set_id}/reject")
def reject_scope_draft(change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    problems = project_change_sets.reject_scope_draft(conn, user.principal_id, change_set_id)
    return {"rejected": not problems, "problems": problems}
