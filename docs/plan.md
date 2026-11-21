# Plan

## Where we are

Step 0 is done: `CLAUDE.md`, `docs/plan.md`, `docs/terminology.md`, `docs/architecture.md`, `docs/design.md`
and `docs/rules.md` exist. Deploys are by hand from zips (no GitHub Actions), and testing is local with demo
data, fake AI and fake Databricks.

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
| `90_roles.sql` | | database logins for the web app and MCP server, and their grants | before 4a |
| `99_verify_install.sql` | | checks every expected table exists, nothing extra, every table has a primary key, no functions or triggers | 1a |

## How to run what exists

```
docker run -d --name gds-pg -p 5433:5432 -e POSTGRES_PASSWORD=local postgres:18   # once
uv run scripts/local_db.py                                                         # rebuild the local database
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
- [ ] **2. Rules** for the first loop (access, scope, change sets) in `docs/rules.md`. Maaz approves.
- [ ] **3. Core**: `require_role`, tenant lock, list tables, change set draft and Apply for scope. Tests.
- [ ] **4. One thin loop**, one piece at a time:
  - [ ] 4a demo data (`database/demo/`: demo tenant, one user per role, small sample catalog with the other
    reference lists, demo project), web backend route + one web page (list tables, edit scope, review, Apply), plus
    `scripts/run_local.py` with local sign-in (pick a demo user), fake AI and fake Databricks
  - [ ] 4b MCP server with one tool
  - [ ] 4c Bridge: pull, check, push for scope
  - [ ] 4d Local Workbench showing local files and check results
- [ ] **5. Build and deploy by hand**: `scripts/build.py web|mcp|plugin|bridge` writes zips to `dist/`;
  `scripts/db_install.py` sets up Azure Postgres. Maaz uploads them and checks `/health` on both servers.
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
- MCP tool call log (v2 `mcp.tool_call_log`): add with the MCP server and plugin (step 4b), Nov 19, Maaz.
- Deletes and cleanup in the catalog and in projects: how a person removes things safely, probably a space on the
  Tenant Admin page. To discuss (Nov 20, Maaz).
- Admin page per tenant: members, MCP access, catalog lock, project locks (Nov 20, Maaz).

## Open questions

- Local Workbench as a panel inside VS Code (part of the Bridge extension)? Recommended: yes.
- Bridge "check": ask the server (rules exist once) or run on the laptop? Decide at step 4c.
- VS Code push: the steps (start, send pieces, finish, start over on failure), and whether pieces are needed at all
  or one request per table is enough. Design at step 4c with real sizes (Nov 20, Maaz).
