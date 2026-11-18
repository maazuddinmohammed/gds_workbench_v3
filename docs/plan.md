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

The path from subject areas to code was reviewed with Maaz on Nov 18. The decisions are in `docs/design.md`
under "Path review", and the flows are in the new `design/` folder, one short file with a diagram per workflow
and shared part. Details left open on purpose are listed in each file under "Decided when we build it".

## Next

After Maaz reviews 1a to 1c: **Step 1d: projects and scope** in `04_project.sql`. 

## Database files (same pattern as v2: one schema per area, numbered files)

Every step that adds a schema or table also adds its drop line to `00_preflight.sql` and its name to
`99_verify_install.sql`.

| File | Schema | Holds | Step |
|---|---|---|---|
| `00_preflight.sql` | | commented-out drops for a fresh install; stops unless the database is clean | 1a |
| `01_reference.sql` | `reference` | fixed lists (system types, zones, connection types, ...) | 1b, 1c |
| `02_core.sql` | `core` | lanes, tenants, catalog, pipelines | 1a, 1b, 1c |
| `03_security.sql` | `security` | users, tenant members, tenant locks | 1a |
| `04_project.sql` | `project` | projects, scope, notes, project lock | 1d |
| `05_workflow_analysis.sql` | `workflow` | profiles, enrichment, relationships | 1d |
| `06_workflow_subject_area.sql` | `workflow` | subject areas | 1d |
| `07_workflow_silver.sql` | `workflow` | Silver model | 1e |
| `08_workflow_gold.sql` | `workflow` | Gold model | 1e |
| `09_workflow_mapping.sql` | `workflow` | Silver and Gold mapping | 1f |
| `10_workflow_code.sql` | `workflow` | generated code | 1f |
| `11_application_change_sets.sql` | `application` | change sets and their items | 1g |
| `12_application_prompts.sql` | `application` | prompts and prompt versions | 1h |
| `13_application_runs.sql` | `application` | runs, run events, AI usage, budgets | 1h |
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
  - [ ] 1d projects and scope, notes, profiles, enrichment, relationships, subject areas
  - [ ] 1e models (Silver and Gold entities, columns, links)
  - [ ] 1f mapping and code
  - [ ] 1g change sets
  - [ ] 1h prompts, runs, AI usage
  - [ ] 1i seed: reference data and starter prompts (`database/seed/`); demo data for local testing only
    (`database/demo/`: demo tenant, one user per role, small sample catalog, demo project)
- [ ] **2. Rules** for the first loop (access, scope, change sets) in `docs/rules.md`. Maaz approves.
- [ ] **3. Core**: `require_role`, tenant lock, list tables, change set draft and Apply for scope. Tests.
- [ ] **4. One thin loop**, one piece at a time:
  - [ ] 4a web backend route + one web page (list tables, edit scope, review, Apply), plus
    `scripts/run_local.py` with local sign-in (pick a demo user), fake AI and fake Databricks
  - [ ] 4b MCP server with one tool
  - [ ] 4c Bridge: pull, check, push for scope
  - [ ] 4d Local Workbench showing local files and check results
- [ ] **5. Build and deploy by hand**: `scripts/build.py web|mcp|plugin|bridge` writes zips to `dist/`;
  `scripts/db_install.py` sets up Azure Postgres. Maaz uploads them and checks `/health` on both servers.
- [ ] **6. Workflow steps, one at a time** (each: rules, then core, then web/MCP/Bridge):
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

## Open questions

- Local Workbench as a panel inside VS Code (part of the Bridge extension)? Recommended: yes.
- Bridge "check": ask the server (rules exist once) or run on the laptop? Decide at step 4c.
