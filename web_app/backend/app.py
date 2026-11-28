"""The web app's backend (FastAPI), deployed as a Databricks App (step 4a2).

Every route is a thin door into core/: it finds who you are, calls one core/ function, and returns its answer as
JSON. No route checks roles or locks itself; the core/ function calls `require` first. The route test in
tests/test_web_app.py calls every route as an outsider and as a Viewer to prove none can skip it.

Who you are: Databricks Apps send the signed-in person's email in the `X-Forwarded-Email` header. Locally, the page's
"pick a demo user" sets the same header (scripts/run_local.py, step 4a3).

Answers when core/ says no: 401 when nobody is signed in or the email is not an active user, 404 for "not found"
(ACCESS-001), 403 for any other refusal, 422 for a request of the wrong shape. Each says the rule ID.

Settings (v2's names): GDS_WEB_DATABASE_DSN (required), GDS_WEB_ENVIRONMENT, GDS_WEB_STATIC_DIR (the built page, which
this app serves at / on Databricks; locally Vite serves it instead, so it is not set). For Runs: GDS_WEB_FOUNDRY_OPENAI_BASE_URL
and GDS_WEB_FOUNDRY_API_KEY (v2's names, for Foundry), and GDS_WEB_OPENAI_API_KEY (new, Nov 28: the OpenAI API, for
testing; scripts/run_local.py sets it from OPEN_AI_KEY in .env).

On Databricks the App starts `python app.py` (web_app/app.yaml), which listens on DATABRICKS_APP_PORT (step 5c).
"""

import os
import threading
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import access, catalog, change_sets, projects, runs, tenant_lock
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
    """Release your own lock. Someone else's is refused (ACCESS-003): that is an override."""
    return {"released": tenant_lock.release_lock(conn, user.principal_id, tenant_id)}


@app.post("/api/tenants/{tenant_id}/lock/override")
def override_lock(tenant_id: int, user=Depends(signed_in), conn=Depends(database)):
    """End someone else's lock. The page asks "are you sure?" first."""
    return {"overridden": tenant_lock.override_lock(conn, user.principal_id, tenant_id)}


@app.get("/api/projects/{project_id}")
def project_detail(project_id: int, user=Depends(signed_in), conn=Depends(database)):
    return projects.get_project_detail(conn, user.principal_id, project_id)


@app.get("/api/projects/{project_id}/scope")
def scope(project_id: int, include_switched_off: bool = False, user=Depends(signed_in), conn=Depends(database)):
    return projects.current_scope(conn, user.principal_id, project_id, include_switched_off=include_switched_off)


@app.get("/api/projects/{project_id}/records/{part}")
def records(project_id: int, part: str, user=Depends(signed_in), conn=Depends(database)):
    """The project's saved rows of one part (core/parts.py), as records."""
    return change_sets.read_records(conn, user.principal_id, project_id, part)


# --- Change sets (design/operations/change-sets.md). Only project change sets are built so far. -------------------


class NewDraft(BaseModel):
    title: str
    documents: dict[str, list[dict]]


@app.post("/api/projects/{project_id}/change-sets", status_code=201)
def make_draft(project_id: int, body: NewDraft, user=Depends(signed_in), conn=Depends(database)):
    """A hand edit: the records typed or clicked on a page, saved as a draft."""
    return {"change_set_id": change_sets.make_draft(conn, user.principal_id, project_id, body.documents, body.title)}


@app.get("/api/tenants/{tenant_id}/change-sets")
def list_change_sets(tenant_id: int, project_id: int | None = None, status: str | None = None,
                     user=Depends(signed_in), conn=Depends(database)):
    return change_sets.list_change_sets(conn, user.principal_id, tenant_id, project_id, status)


def project_kind(kind: str):
    if kind != "project":
        raise ValueError("Only project change sets are built so far.")


@app.get("/api/change-sets/{kind}/{change_set_id}")
def get_change_set(kind: str, change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    project_kind(kind)
    return change_sets.get_change_set(conn, user.principal_id, change_set_id)


@app.get("/api/change-sets/{kind}/{change_set_id}/changes")
def list_changes(kind: str, change_set_id: int, part: str, change: str | None = None, page: int = 1,
                 user=Depends(signed_in), conn=Depends(database)):
    project_kind(kind)
    return change_sets.list_changes(conn, user.principal_id, change_set_id, part, change, page)


@app.get("/api/change-sets/{kind}/{change_set_id}/problems")
def problems(kind: str, change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    project_kind(kind)
    found = change_sets.validate(conn, user.principal_id, change_set_id)
    return {"can_apply": not any(p.level == "blocks_apply" for p in found), "problems": found}


class TakeOut(BaseModel):
    part: str
    record: int


@app.post("/api/change-sets/{kind}/{change_set_id}/take-out")
def take_out(kind: str, change_set_id: int, body: TakeOut, user=Depends(signed_in), conn=Depends(database)):
    """Take one record out of a draft during review (C9)."""
    project_kind(kind)
    return {"problems": change_sets.take_out(conn, user.principal_id, change_set_id, body.part, body.record)}


@app.post("/api/change-sets/{kind}/{change_set_id}/apply")
def apply(kind: str, change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    project_kind(kind)
    found = change_sets.apply(conn, user.principal_id, change_set_id)
    return {"applied": not found, "problems": found}


@app.post("/api/change-sets/{kind}/{change_set_id}/reject")
def reject(kind: str, change_set_id: int, user=Depends(signed_in), conn=Depends(database)):
    project_kind(kind)
    found = change_sets.reject(conn, user.principal_id, change_set_id)
    return {"rejected": not found, "problems": found}


# --- Runs (design/overview/run.md) ---------------------------------------------------------------------------------


def ai_credentials():
    """Where each AI provider is reached, from the app's settings (core/ never reads settings)."""
    return {
        "foundry_openai": {"base_url": os.environ.get("GDS_WEB_FOUNDRY_OPENAI_BASE_URL"),
                           "api_key": os.environ.get("GDS_WEB_FOUNDRY_API_KEY")},
        "openai": {"api_key": os.environ.get("GDS_WEB_OPENAI_API_KEY")},
    }


def execute_in_background(run_id):
    """A Run works in the background, on a connection of its own, so the page can follow its log."""
    def work():
        with psycopg.connect(os.environ["GDS_WEB_DATABASE_DSN"], autocommit=True) as conn:
            runs.execute(conn, run_id, ai_credentials())

    threading.Thread(target=work, daemon=True).start()


class NewRun(BaseModel):
    project_workflow: str
    request: dict = {}
    prompt_version_id: int | None = None
    agent_model_id: int | None = None
    reasoning_effort_code: str | None = None
    max_turns: int | None = None
    extra_instructions: str | None = None


@app.post("/api/projects/{project_id}/runs", status_code=201)
def start_run(project_id: int, body: NewRun, user=Depends(signed_in), conn=Depends(database)):
    run_id = runs.start_run(conn, user.principal_id, project_id, body.project_workflow, body.request,
                            body.prompt_version_id, body.agent_model_id, body.reasoning_effort_code, body.max_turns,
                            body.extra_instructions)
    execute_in_background(run_id)
    return {"run_id": run_id}


@app.get("/api/projects/{project_id}/runs")
def project_runs(project_id: int, user=Depends(signed_in), conn=Depends(database)):
    return runs.list_runs(conn, user.principal_id, project_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, user=Depends(signed_in), conn=Depends(database)):
    return runs.get_run(conn, user.principal_id, run_id)


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: int, user=Depends(signed_in), conn=Depends(database)):
    return runs.get_run(conn, user.principal_id, run_id)["events"]


@app.get("/api/models")
def models(user=Depends(signed_in), conn=Depends(database)):
    return runs.list_models(conn)


# --- The built page and the start on Databricks (step 5c) ---------------------------------------------------------

# Last, so every /api and /health route above is matched first.
if os.environ.get("GDS_WEB_STATIC_DIR"):
    app.mount("/", StaticFiles(directory=HERE / os.environ["GDS_WEB_STATIC_DIR"], html=True), name="page")


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0: Databricks Apps reach the app through their own proxy, which does the sign-in.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))
