# Plan

## Where we are

Step 0 is done: `CLAUDE.md`, `docs/plan.md`, `docs/terminology.md`, `docs/architecture.md`, `docs/design.md`
and `docs/rules.md` exist. Deploys are by hand from zips (no GitHub Actions), and testing is local with demo
data (no fake AI or fake Databricks, Nov 21, Maaz).

Steps 1a, 1b and 1c are written and tested locally, **waiting for Maaz's review**: `00_preflight.sql`,
`01_reference.sql` (12 lists), `02_core.sql` (lane, tenant, catalog and pipeline tables, v2 names),
`03_security.sql` (principal, tenant_principal_access, tenant_lock), `99_verify_install.sql`,
`scripts/local_db.py`. Patterns are in `design.md` under "Database patterns". Reference rows come with the
seed in 1i.

Steps 1d to 1g were reviewed with Maaz on Nov 18 and are done: `04_project.sql`, `05_project_context.sql`,
`06_workflow_analysis.sql`, `07_workflow_subject_area.sql`, `08_workflow_operational.sql`, `09_workflow_dimensional.sql`,
`10_workflow_mapping.sql`, `11_workflow_code.sql`, `12_workflow_validation.sql`, `13_application_change_sets.sql`, two new reference lists
(context type, operational entity type) and the first seed file `database/seed/01_context_type.sql`.
`scripts/local_db.py` now also runs the seed files. Decisions are in `design.md` under "Projects, workflow and
change set tables". Rules OPERATIONAL-001 to 003, DIMENSIONAL-001 to 003, SUBJECT-AREA-001,
MAPPING-001 and CODE-001 are Approved. Apply stays in Python in `core/` (one transaction), not a stored procedure.

Step 1h, part 1 (prompts) was reviewed with Maaz on Nov 18 and is done: `14_application_prompts.sql` with
`application.prompt` (global or per tenant, one default per step and kind of Run) and `application.prompt_version`.
Decisions are in `design.md` under "Prompts".

Step 1h, part 2 (runs) was reviewed with Maaz on Nov 19 and is done: `15_application_runs.sql` with
`application.run` (one running Run per tenant), `application.run_event` (the Run log) and
`application.run_model_request` (AI usage, one row per AI call). A Run points at the draft change set it made.
AI providers and models are two new lists in `01_reference.sql` (`agent_provider`, `agent_model` with reasoning
efforts and prices); `project_config` and `run` point at the model. Decisions are in `design.md` under "Runs".
Seed `database/seed/02_agent_provider_model.sql` adds v2's three Foundry models with Global Standard prices.
Rules RUN-001 and RUN-002 are Approved (Nov 19).

Step 1i is done (Nov 19): seed files are MERGE statements, safe to rerun. `02_agent_provider_model.sql` (v2's three
Foundry models with Global Standard prices), `03_operational_entity_type.sql` (v2's 14 types), `04_zone.sql` (source,
bronze, silver, gold; v2 had them only in its demo seed). The other reference lists had only demo rows in v2, so
they come with the demo data.

The path from subject areas to code was reviewed with Maaz on Nov 18. The decisions are in `docs/design.md`
under "Path review", and the flows are in the new `design/` folder, one short file with a diagram per workflow
and shared part. Details left open on purpose are listed in each file under "Decided when we build it".

Step 2 was reviewed with Maaz on Nov 20. Rules now live in one file per group under `docs/rules/` (index:
`docs/rules.md`), each rule written as what it means, why, what happens and an example, with the non-obvious
database checks listed too. Roles, permissions and the one `require` check function are in
`design/shared/access.md`. Architect is dropped (three roles: Viewer, Developer, Tenant Admin), membership has no
end date (`access_expires_time` removed), relationships are keyed by project + from column + to column, and every
table's row key is listed in `docs/rules/row-keys.md`. CODE-001 is now a Warning. Decisions are in
`design.md` under "Access and rules review (Nov 20)".

## Next

Nov 21: ACCESS-004, SCOPE-002, CHANGE-SET-007 and CHANGE-SET-011 approved; the metadata version and catalog lock
columns are on `core.tenant` and `application.metadata_change_set`. CHANGE-SET-006 waits for the VS Code push design
(step 4c). Notes get a Note number as their row key, "row key" now names what identifies our own rows (kept apart from natural key), and a
Silver entity can use any Source or Bronze table in scope (Nov 21). Then **step 3: core**.
Starter prompts come with each workflow in step 6 and demo data with step 4a, where each is first used (Nov 19, Maaz).

Step 3 is split into four small pieces (Nov 21, Maaz): 3a `require`, 3b take and release the tenant lock,
3c list the catalog tables a person can see, 3d the scope draft, Apply and Reject.
3a is done (Nov 21): `core/access.py` with `require` and one function per rule (ACCESS-001 to 004,
CHANGE-SET-004 and 011), `core/problems.py` (`Refused`, `NotFound`), tests in `tests/` against a separate
`gds_test` database, and a test that every rule check in `core/` is Approved in `docs/rules/`.
3b is done (Nov 21): `core/tenant_lock.py` with `take_lock` (you choose 1 minute to 4 hours, 60 by default; taking
it again starts your time over; an ended lock is replaced), `release_lock` (anyone with `CHANGE` releases anyone's
lock) and `current_lock` (who holds it, for anyone who can read the tenant).
The data lake schema change is done (Nov 21): `core.tenant.is_data_lake` and `data_lake_connection_id` (was
`gds_connection_id`); `connection.is_global_data_store` dropped; rules CATALOG-001 and 002 (Approved, built in step 4)
in `docs/rules/catalog.md`.
3c is done (Nov 21): `core/catalog.py` with `list_tables` (a tenant's own tables and every active global tenant's,
by source tenant, all zones; filters for zones, scope-only and switched-off rows; 50 per page with the total) and
`scope_001` / `scope_002`, ready for 3d.
3d is split in three (Nov 21, Maaz): 3d1 make and check a scope draft, 3d2 Apply, 3d3 Reject.
3d1 is done (Nov 21): `core/project_change_sets.py` with `make_scope_draft` (saves a draft on the project's current
version; needs CHANGE, the project's tenant lock and an unlocked project) and `check_scope_draft` (every problem at
once: CHANGE-SET-001, 002, 003, 005, SCOPE-001 and 002), and `Problem` in `core/problems.py`.
3d2 is done (Nov 21): `apply_scope_draft` saves the whole draft in one transaction or nothing, using the same
checks as `check_scope_draft`; it returns the problems that stopped it (empty means applied).
3d3 is done (Nov 21): `reject_scope_draft` marks a draft rejected with who and when; nothing in the project
changes. **Step 3 is complete.**
Step 4a is split in four (Nov 21, Maaz): 4a1 demo data, 4a2 web backend, 4a3 `scripts/run_local.py`, 4a4 the
React page. No fake AI or fake Databricks (Nov 21, Maaz). `90_roles.sql` moves to step 5.
4a1 is done (Nov 21): `database/demo/` (its own folder, see its README): tenant ACME with SAP-style ERP,
Salesforce-style CRM and Workday-style HR (22 Source tables), the global data lake tenant GDS, Asha, Ben, Cara and Sam,
project Sales; loaded by `scripts/local_db.py`; `tests/test_demo_data.py`.
4a2 is in two commits (Nov 21, Maaz): first the reads the page needs in `core/`, then the routes.
4a2 part 1 is done (Nov 21): `core/access.py` `find_user` (email to active user) and `my_tenants` (tenants you can read,
role from `require`), `core/projects.py` `list_projects` and `current_scope` (scope rows named by row key, the same
shape as a draft record). All read only, all through `require`.
4a2 part 2 is done (Nov 21): `web_app/backend/app.py` (FastAPI) with `/health`, `/api/me`, and routes for the table
list, the project list, the tenant lock (see, take, release), the project's scope and the scope draft (make, read with
its problems, Apply, Reject); `core.project_change_sets.read_scope_draft` for the review. `tests/test_web_app.py` calls
every route as someone not signed in (401), an outsider (404, ACCESS-001) and a Viewer (403, ACCESS-002 for changes),
and checks every `/api` route is in its list.
4a3 is done (Nov 21): `scripts/run_local.py` starts the web backend on 127.0.0.1:8000 against `gds_local` (builds it
if missing; `--fresh` rebuilds it), restarting on code changes. It listens on this computer only, because locally
anyone who can reach it can claim any user through the sign-in header.
4a4 is split in three (Nov 21, Maaz): 4a4a setup, demo user picker, tenants and projects; 4a4b table list, current
scope and the lock; 4a4c add and remove tables, review the draft, Apply or Reject.
4a4a is done (Nov 21): `web_app/frontend/` with React, Vite and TypeScript only (no other library until a page needs
it, asked first, Maaz). `run_local.py` starts the backend (8000) and the page (http://127.0.0.1:5173, passing `/api`
to the backend). The "Signed in as" picker and the sign-in header exist only in the local dev build.
4a4b is done (Nov 21): the page shows the table list (zone, scope-only and switched-off filters, 50 per page), the
project's current scope, and the tenant lock (take for 15 minutes to 4 hours, start your time over, release; releasing
someone else's asks first). `my_tenants` now also sends each tenant's permissions, so the page offers only what your
role may do without copying the role rules.
4a4c is done (Nov 21): Add and Remove on the page, the changes not saved yet (with Undo), Make draft, and a review
of the draft with each record's problems and rule IDs, then Apply or Reject. Turning clicks into draft records is in
`web_app/frontend/src/scopeChanges.ts`, tested with Node's own test runner (`npm test`, no extra package). The table
list now also names each table's connection tenant, the first part of its row key. **Step 4a is complete.**
How we plan the rest (Nov 21, Maaz): neither every function up front nor one step at a time blind. Before a
workflow is built, it gets an **Operations table**: one line per operation (what it does, who calls it: web, MCP tool
or Bridge, the `core/` function, the permission, the rules), in its own file under `design/operations/`, not in
`docs/design.md`. Maaz reviews it, then the step is built vertically (rules, `core/`, the web route and MCP tool
together). Shared code is pulled out when a pattern repeats, not before (for example the draft, check, Apply and
Reject engine once a second workflow needs it).
Order changed (Nov 21, Maaz): step 4 is finished first, in the plan's order (4b, 4c, 4d), then step 5; the Operations
tables (4-ops) come after step 5, before step 6. They include the full list of MCP tools (for example list tenants,
and list projects in a tenant) and web routes.
**Next: 4b**, the MCP server with one tool (keeping v2's App Service settings, see "How the apps use core/"). Split in
three (Nov 21, Maaz): 4b1 find a user by Microsoft object ID, with made-up IDs for the demo users; 4b2 `mcp_server/`
with `/health` and the tool "see the project's scope" (official `mcp` library, v2's sign-in through App Service);
4b3 run and test it locally. The MCP tool call log waits until the first tool works.
4b1 is done (Nov 21): `core.access.find_user_by_object_id` (active user with that Microsoft object ID), and the demo
users have made-up object IDs ending in their number (Sam 1, Asha 2, Ben 3, Cara 4). Rebuild `gds_local` to get them
(`uv run scripts/local_db.py`).
4b2 is done (Nov 21): `mcp_server/app.py` with the official `mcp` library (added Nov 21, Maaz): `/health`, `/mcp`
(stateless, JSON answers) and one tool, `see_project_scope`, calling `core.projects.current_scope` with
`via_mcp=True`. Sign-in as in v2: App Service's `X-MS-CLIENT-PRINCIPAL` header on Azure (object ID, and the Microsoft
tenant must be `GDS_ENTRA_TENANT_ID`), `GDS_LOCAL_PRINCIPAL_OBJECT_ID` locally. `mcp_server/startup.sh` is v2's,
unchanged. `tests/test_mcp_server.py` calls the tool over HTTP.
4b3 is done (Nov 21): `scripts/run_local.py` also starts the MCP server on http://127.0.0.1:8001/mcp, signed in as Ben
(`--mcp-user sam|asha|ben|cara` to change). Tried by hand: a scope applied on the web shows through the tool; an
unknown project (ACCESS-001), MCP access off (ACCESS-004) and another host (421) are refused. **Step 4b is complete.**
4c and 4d wait (Nov 21, Maaz): the Bridge's design is still being discussed, so the Bridge (4c) and the Local Workbench
inside it (4d) are built later, after that discussion.
**Next: step 5**, build and deploy by hand, in five pieces (Nov 21, Maaz): 5a the MCP server ready for v2's Azure setup,
5b `scripts/build.py mcp` (`dist/mcp.zip`), 5c `scripts/build.py web` (`dist/web/`), 5d `90_roles.sql` and
`scripts/db_install.py`, 5e Maaz uploads and checks. v3 goes into v2's App Service and Databricks App with their setup
unchanged (see `design.md`). `gunicorn` and `uvicorn-worker` may be added for `startup.sh` (Nov 21, Maaz). The plugin
zip waits for the tool list (after step 5).
5a is done (Nov 21): the MCP server answers at v2's `/health/live`, `/health/ready` and
`/.well-known/oauth-protected-resource` (the sign-in page for VS Code, same answer as v2); `/health` is gone.
5b is done (Nov 21): `uv run scripts/build.py mcp` writes `dist/mcp.zip` (`app.py`, `startup.sh`, a copy of `core/`,
`requirements.txt` with exact versions and hashes, `version.txt`). `pyproject.toml` now has one group per app (`web`,
`mcp`), so each upload lists only what it uses. Tried by hand: the zip, installed on Python 3.14 and started with
`startup.sh` (gunicorn), answered `/health/live`, `/health/ready` and the tool against `gds_local`.
5c is done (Nov 21): `uv run scripts/build.py web` writes the folder `dist/web/` (`app.py`, `app.yaml`, a copy of
`core/`, `static/` with the built page, `requirements.txt`, `version.txt`). The backend serves the built page at `/`
when `GDS_WEB_STATIC_DIR` is set, and `python app.py` listens on `DATABRICKS_APP_PORT`. `web_app/app.yaml` keeps v2's
setting names and its `postgres-dsn` App resource. Tried by hand on Python 3.14: `/health`, the page and the scope route
against `gds_local`.
5d is done (Nov 21): `90_roles.sql` gives the app logins `gds_web_runtime` and `gds_mcp_runtime` (v2's names) read and
write on every table; existing logins are kept with their passwords, so only the database name in each DSN changes.
`99_verify_install.sql` checks both logins can read and write every table. `scripts/db_install.py` installs into an
empty database you name (install and seed, never demo data), password from `PGPASSWORD`.
5e waits (Nov 21, Maaz): Maaz installs the database on Azure, uploads `mcp.zip` and `dist/web/`, and checks them later
(checklist: build from a clean main; `db_install.py` into the new database; change only the database name in the App
Service's `GDS_DATABASE_DSN` and the Databricks `postgres-dsn` secret; `az webapp deploy` the zip; check
`/health/live`, `/health/ready`, `/.well-known/oauth-protected-resource`; upload `dist/web/` and check `/health`; try
the tool from VS Code).
**Next: the Operations tables (4-ops)**, with the full list of MCP tools and web routes, before step 6. They start once
the Bridge design discussion is finished (Nov 21, Maaz).

## Database files (same pattern as v2: one schema per area, numbered files)

Every step that adds a schema or table also adds its drop line to `00_preflight.sql` and its name to
`99_verify_install.sql`.

| File | Schema | Holds | Step |
|---|---|---|---|
| `00_preflight.sql` | | commented-out drops for a fresh install; stops unless the database is clean | 1a |
| `01_reference.sql` | `reference` | fixed lists (system types, zones, connection types, ...) | 1b, 1c |
| `02_core.sql` | `core` | lanes, tenants, catalog, pipelines | 1a, 1b, 1c |
| `03_security.sql` | `security` | users, tenant members, tenant locks | 1a |
| `04_project.sql` | `project` | projects, settings, schemas and scope (project lock is a field) | 1d |
| `05_project_context.sql` | `project` | Notes: context groups and context records | 1d |
| `06_workflow_analysis.sql` | `workflow` | profiles, sample values, enrichment, relationships | 1d |
| `07_workflow_subject_area.sql` | `workflow` | subject areas | 1d |
| `08_workflow_operational.sql` | `workflow` | operational model (Silver) | 1e |
| `09_workflow_dimensional.sql` | `workflow` | dimensional model (Gold) | 1e |
| `10_workflow_mapping.sql` | `workflow` | operational and dimensional mapping | 1f |
| `11_workflow_code.sql` | `workflow` | operational and dimensional code | 1f |
| `12_workflow_validation.sql` | `workflow` | operational and dimensional validation groups and checks | 1f |
| `13_application_change_sets.sql` | `application` | change sets (one document per table) and stage chunks | 1g |
| `14_application_prompts.sql` | `application` | prompts (global or per tenant) and prompt versions | 1h |
| `15_application_runs.sql` | `application` | runs, the Run log, AI usage | 1h |
| `90_roles.sql` | | database logins for the web app and MCP server (kept if they exist), and their grants | 5d |
| `99_verify_install.sql` | | checks every expected table exists, nothing extra, every table has a primary key, no functions or triggers | 1a |

## How to run what exists

```
docker run -d --name gds-pg -p 5433:5432 -e POSTGRES_PASSWORD=local postgres:18   # once
uv run scripts/local_db.py                                                         # rebuild the local database
uv run pytest                                                                      # run the tests (own database gds_test)
(cd web_app/frontend && npm test)                                                  # the page's tests
uv run scripts/run_local.py                                                        # web app on http://127.0.0.1:5173, MCP on :8001/mcp (--fresh rebuilds gds_local)
uv run scripts/build.py mcp                                                        # dist/mcp.zip for the MCP server's App Service
uv run scripts/build.py web                                                        # dist/web/ for the Databricks App
PGPASSWORD=... uv run scripts/db_install.py "host=... dbname=... user=... sslmode=require"  # install into an empty database (Azure)
```

## How we work

- One small step per session or pull request. Review before the next one starts.
- Each workflow step goes: rules first (in `docs/rules.md`, approved by Maaz), then code.
- At the end of a session, update "Where we are" and "Next" above.

## Steps

- [x] **0. Setup**: CLAUDE.md, plan, terminology, architecture, design, rules.
- [ ] **1. Schema**, one part at a time, tables only:
  - [x] 1a access (lanes, tenants, users, tenant members, tenant lock), plus `scripts/local_db.py`
  - [x] 1b catalog (systems, connections, tables, columns, ingestion lineage)
  - [x] 1c pipelines (copy groups, members, processes, notebooks, reference lists)
  - [x] 1d projects and scope, notes, profiles, enrichment, relationships, subject areas
  - [x] 1e models (Silver and Gold entities, columns, links)
  - [x] 1f mapping and code
  - [x] 1g change sets
  - [x] 1h prompts, runs, AI usage
  - [x] 1i seed: reference data, AI providers and models (`database/seed/`). Starter prompts move to step 6
    (each workflow), demo data (`database/demo/`) to step 4a
- [x] **2. Rules** for the first loop (access, scope, change sets) in `docs/rules.md`. Maaz approves.
- [x] **3. Core**: `require` (3a), tenant lock (3b), list tables (3c), scope draft, Apply and Reject (3d). Tests.
- [ ] **4. One thin loop**, one piece at a time:
  - [x] 4a demo data (`database/demo/`: demo tenant, one user per role, small sample catalog with the
    reference rows it needs, demo project), web backend route + one web page (list tables, edit scope, review, Apply), plus
    `scripts/run_local.py` with local sign-in (pick a demo user). Split in four (Nov 21, Maaz): 4a1 demo data,
    4a2 web backend, 4a3 `run_local.py`, 4a4 the React page.
    - [x] 4a1 demo data
    - [x] 4a2 web backend
    - [x] 4a3 `run_local.py`
    - [x] 4a4a page setup, user picker, tenants and projects
    - [x] 4a4b table list, current scope, tenant lock
    - [x] 4a4c add and remove, review the draft, Apply or Reject
  - [x] 4b MCP server with one tool (4b1 find a user by object ID, 4b2 server and tool, 4b3 run locally)
  - [ ] 4c Bridge: pull, check, push for scope (waits for the Bridge design discussion, Nov 21, Maaz)
  - [ ] 4d Local Workbench showing local files and check results (waits with 4c)
- [ ] **5. Build and deploy by hand**: `scripts/build.py web|mcp|plugin|bridge` writes zips to `dist/`;
  `scripts/db_install.py` sets up Azure Postgres. Maaz uploads them and checks the web app's `/health` and the MCP server's `/health/live` and `/health/ready`.
- [ ] **Operations tables (4-ops)** after step 5, before step 6 (Nov 21, Maaz) (`design/operations/`, one file per workflow): what each
  operation does, who calls it (web, MCP, Bridge), its `core/` function, permission and rules, and the full
  list of MCP tools and web routes. Reviewed with Maaz before step 6 is built.
- [ ] **6. Workflow steps, one at a time** (each: rules, then core, then starter prompt, then web/MCP/Bridge):
  - [ ] profiling
  - [ ] enrichment
  - [ ] relationships
  - [ ] subject areas
  - [ ] Silver model
  - [ ] Gold model
  - [ ] Silver mapping
  - [ ] Gold mapping
  - [ ] code generation
  - [ ] pipelines screens
  - [ ] prompts page

## Later

- Personal keys table: add when AI tools other than VS Code need MCP.
- AI budgets: add when cost control is built; `run_model_request` has the numbers.
- MCP tool call log (v2 `mcp.tool_call_log`): add with the MCP server and plugin, Nov 19, Maaz; after 4b's first tool works (Nov 21, Maaz).
- Deletes and cleanup in the catalog and in projects: how a person removes things safely, probably a space on the
  Tenant Admin page. To discuss (Nov 20, Maaz).
- Admin page per tenant: members, MCP access, catalog lock, project locks (Nov 20, Maaz).

- Page layout and navigation for many pages: its own design step before the second page is built (Nov 21, Maaz).

## Open questions

- Databricks Apps sign-in: confirm on the real app that Databricks sets `X-Forwarded-Email` itself and replaces one
  a caller sends, before anyone relies on it (step 5).

- Local Workbench as a panel inside VS Code (part of the Bridge extension)? Recommended: yes.
- Bridge "check": ask the server (rules exist once) or run on the laptop? Decide at step 4c.
- VS Code push: the steps (start, send pieces, finish, start over on failure), and whether pieces are needed at all
  or one request per table is enough. Design at step 4c with real sizes (Nov 20, Maaz).
