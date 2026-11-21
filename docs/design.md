# Design decisions

Short list of what we decided and why. Add to it when something new is decided.
The full design page from the planning thread has more detail; this file is the source of truth.

## Pieces

- **core/**: one Python folder with all the logic: reading and writing Postgres, checks, change sets, Apply,
  SQL generation. Everything else is a thin door into it.
- **Web app**: FastAPI backend + React pages, deployed as a **Databricks App**. Step-by-step workflows with
  a Run button. Also where AI cost is controlled.
- **MCP server**: deployed on **Azure App Service**, because VS Code can sign in there with Microsoft and
  no client ID on laptops. Also serves the Bridge's pull, check and push as MCP tools.
- **Plugin**: skills (text) and the MCP address.
- **Bridge**: pull, check, push. Moves big data without passing it through the AI, which keeps AI cost down. Two
  ways in: the Terminal Bridge (helper script in a terminal) and the Extension Bridge (VS Code buttons).
- **Local Workbench**: one HTML page that shows the pulled project and the server's problems. View only.
- **Postgres** (Azure): data only. No functions holding logic.

## Bridge (decided Nov 21, Maaz, in the Bridge design discussion)

- Two ways in, using the same MCP tools and the same storage path: the **Terminal Bridge** (the AI runs short
  commands of the helper script in a terminal; works with any AI tool that has the MCP connection) and the
  **Extension Bridge** (a lean VS Code extension with Pull, Check and Push buttons).
- **Pull** stays as v2: the server puts a zip in Azure storage and returns a short-lived download link.
- **Push**: the files go to Azure storage through a short-lived upload link; then a signed-in tool call loads the
  upload into one change set, all or nothing, and returns every problem with its rule ID. A new upload replaces
  everything in that change set; there is never a second draft for the same push.
- Storage path: `push` or `pull`, then tenant, project, date and id, for example
  `push/ACME/Sales/2026-11-21/<change set id>/upload-1.zip`. Old files are deleted automatically.
- Local files use names and codes, never ids, one small file per table, entity or mapping; SQL is a real `.sql` file.
  The AI edits the pulled files in place; the pull's zip stays on the laptop as the clean copy, for undo.
- **Check runs on the server** (rules exist once, in `core/`). The laptop runs no rules for now; a local check can
  come later if real use asks for it.
- The **Local Workbench** stays, lean: one HTML page that reads the project folder, the same with either bridge. It
  only views and shows the problems the server sent back at the last load.
- A small **helper script** ships with the plugin: two commands, pull and push, no rules and no sign-in. Its
  language is not decided yet (Python proposed).
- The AI may apply after the person reviews and says yes in chat (see "How work happens").
- Left for the Operations tables step: the full tool list (starting point: `start_change_set`, `load_upload`,
  `get_change_set`, `start_upload`, `close_change_set`, `apply_change_set`, plus pull), whether to split
  `load_upload`. Rejecting a change set that is still receiving is allowed (CHANGE-SET-001, changed Nov 21). The pieces rule (CHANGE-SET-006)
  and the chunk tables were dropped on Nov 21 (Maaz). Left for when the extension is built:
  whether it calls the helper script or packs and uploads itself. To try on Azure: the server handing out upload
  links, Claude Code signing in to the MCP server, one upload of the biggest real project.

## Building and deploying

- No GitHub Actions and no automatic deploy. Claude has no access to the live apps.
- `scripts/build.py` makes files in `dist/`: `web.zip` (web app + core) for the Databricks App, `mcp.zip`
  (MCP server + core) for App Service, `plugin.zip` and `bridge.vsix` to share. Maaz uploads them by hand.
- The Databricks App takes a folder, not a zip: upload the unzipped `web` folder to the workspace and point
  the App at it, as in v2.
- `core/` is a folder, not a deployment. The build copies it into both server zips. Rebuild both when it changes.
- Each zip has a `version.txt` (git commit and build time), shown on `/health`. This replaces v2's manifests,
  checksums and diagnostic SQL files.
- `scripts/db_install.py` runs the install and seed scripts against a database you name.

## How the apps use core/ (Nov 21, Maaz)

- `core/` is a plain Python folder at the repo root. `scripts/build.py` copies it next to each app's `app.py` in
  `dist/` (the web folder for the Databricks App, `mcp.zip` for App Service), so both apps write
  `from core.access import require`. Tests and local runs start from the repo root, where the same import works.
- `core/` never imports from `web_app/` or `mcp_server/`, and never reads settings or secrets. Each app opens its
  own database connection from its own settings and passes it to `core/`.
- `core/`'s Python packages go into both apps' `requirements.txt`. In `pyproject.toml` they are the main
  `dependencies`; each app has its own group (`web`, `mcp`), and `scripts/build.py` writes each upload's
  `requirements.txt` from `uv.lock` (exact versions with hashes) with only core's packages and that app's group (step 5b).
- `core/` never commits. It writes inside `conn.transaction()`, so each call saves all of its changes or none. The
  apps pass an autocommit connection, which makes each call its own transaction; tests pass one that is rolled back.
- Tenant lock (step 3b, changed Nov 21, Maaz): you choose how long when you take it, 1 minute to 4 hours, 60 minutes
  if you do not say. Taking it again while you hold it starts your time over, and an ended lock is replaced by the
  next person who takes it. Anyone with `CHANGE` (Developer, Tenant Admin, Super Admin) can release anyone's lock,
  as in v2, with one function, `release_lock`, for your own lock and someone else's. Asking "are you sure?" first is
  a web app and plugin job, not `core/`'s. Releasing is never implicit (Nov 21, Maaz): no Run, push, Apply,
  MCP tool or `take_lock` call releases a lock on the side; they are refused while someone else holds it. The web
  app gets a separate Release button and the MCP server a separate release tool.
- Tests never only repeat the code back (Nov 21, Maaz): each test checks saved rows, a refusal, or a returned value
  the code could get wrong.
- **The MCP server keeps v2's App Service settings exactly** (Nov 21, Maaz): the same `GDS_*` names already set on
  the portal (`GDS_ENVIRONMENT`, `GDS_DATABASE_DSN`, `GDS_ENTRA_TENANT_ID`, `GDS_ENTRA_API_CLIENT_ID`,
  `GDS_MCP_PUBLIC_URL`, `GDS_CURSOR_SIGNING_KEY`, `GDS_LOCAL_PRINCIPAL_OBJECT_ID`, `GDS_DATABRICKS_SQL_MAX_ROWS`,
  `GDS_DATABRICKS_SQL_TIMEOUT_SECONDS`, `GDS_METADATA_SNAPSHOT_*`) and the same `startup.sh` start command. v3 adds
  no new required setting, and does not refuse a v2 setting it no longer uses (v2 refused unknown `GDS_*` names).
  Built in step 4b.
- MCP server (step 4b2, Nov 21, Maaz): the official `mcp` library (`MCPServer`), stateless with JSON answers like v2.
  Each tool finds the user, calls one `core/` function with `via_mcp=True` and returns its answer; a refusal is a tool
  error starting with its rule ID. Sign-in: on Azure, App Service sign-in checks the token and sends the claims in
  `X-MS-CLIENT-PRINCIPAL`; the server takes the object ID and refuses another Microsoft tenant than
  `GDS_ENTRA_TENANT_ID`. Locally, `GDS_LOCAL_PRINCIPAL_OBJECT_ID` names the user (demo IDs in `database/demo/`). The
  server answers only to the host in `GDS_MCP_PUBLIC_URL` (and this computer when local). It reads `GDS_ENVIRONMENT`,
  `GDS_DATABASE_DSN`, `GDS_MCP_PUBLIC_URL`, `GDS_ENTRA_TENANT_ID` and `GDS_LOCAL_PRINCIPAL_OBJECT_ID` so far.
- v3 goes into v2's own App Service and Databricks App (Nov 21, Maaz): the Entra app registration, App Service sign-in
  and its settings stay as they are; Maaz installs a new database and changes only the DSN value. Any change to the
  deploy setup needs a reason told to Maaz first. So the MCP server keeps v2's addresses that App Service sign-in lets
  through without a token: `/health/live` (up, which build), `/health/ready` (can reach the database, else 503) and
  `/.well-known/oauth-protected-resource` (and `/mcp` after it), which tells VS Code to sign in with Microsoft for
  `GDS_MCP_PUBLIC_URL` and the `workbench.access` scope, exactly as v2 (step 5a). It has no `/health`, because App
  Service sign-in would answer it with 401.

- Web app sign-in (step 4a2, Nov 21, Maaz): Databricks Apps send the signed-in person's email in the
  `X-Forwarded-Email` header; the web app finds the user with `core.access.find_user` and every call then goes
  through `require`. Locally, the page's "pick a demo user" sets the same header, so there is no separate local
  sign-in code. (v2 resolved users through Databricks with the forwarded access token; not needed.)
- The web app keeps v2's `GDS_WEB_*` setting names (`GDS_WEB_DATABASE_DSN`, `GDS_WEB_ENVIRONMENT`,
  `GDS_WEB_STATIC_DIR`) and adds none.
- Web app on Databricks (step 5c, Nov 21): the upload is the folder `dist/web/`. Its `app.yaml` (kept in
  `web_app/app.yaml`) starts `python app.py` and maps `GDS_WEB_DATABASE_DSN` to v2's App resource `postgres-dsn`, so
  nothing changes on the Databricks App itself. The App installs `requirements.txt` (v2 used `uv run` with its own
  packages; v3 has no package to install, so plain `requirements.txt` is simpler). v2's other App resources stay but
  are not used yet. The backend serves the built page from `static/`; locally Vite serves it instead.

- Web routes (step 4a2): each route finds the user, calls one `core/` function and returns its answer as JSON. Not
  signed in or switched off: 401. "Not found" (ACCESS-001): 404. Any other refusal: 403. Wrong shape: 422. Each
  refusal carries its rule ID. Apply and Reject answer `{"applied"|"rejected": bool, "problems": [...]}`. One
  autocommit connection per request for now; a pool can come later if needed.

- Web page (step 4a4, Nov 21, Maaz): React, Vite and TypeScript only; any other library is added when a page needs it,
  after asking Maaz. Locally Vite serves the page on 127.0.0.1:5173 and passes `/api` to the backend on 8000. The
  page sends `X-Forwarded-Email` itself only in the local dev build, from the "Signed in as" picker; the built page
  never does. The layout for many pages gets its own design step before the second page.

- How we plan and build (Nov 21, Maaz): each workflow gets an Operations table in its own file under
  `design/operations/` before it is built, reviewed by Maaz; then it is built vertically (rules, `core/`, web route and
  MCP tool together). Shared code is pulled out when a pattern repeats, not designed ahead.

## Local testing

- Throwaway Postgres with install, seed and demo data (`database/demo/`, never sent to Azure).
- Web app and MCP server run on localhost. Local sign-in: pick a demo user, so each role can be tried.
- No fake AI and no fake Databricks (Nov 21, Maaz): they bloated v2 and pointed the wrong way. How Runs and
  profiling are tried locally is decided when those steps are built.
- Demo data (step 4a1, Nov 21, Maaz): everything demo in one folder, `database/demo/` (its `README.md` lists the
  files), apart from install and seed, loaded by `scripts/local_db.py` into `gds_local` only. Metadata only. Tenant
  ACME (private) has three made-up systems in the style of real products, about 22 Source tables: SAP-style ERP,
  Salesforce-style CRM and Workday-style HR, with names from each product's public naming. They overlap on purpose
  (a Salesforce account carries its SAP customer number, a Salesforce user its Workday worker ID). GDS (global data
  lake) holds ACME's Bronze copies and one Silver table on gds_us, plus two tables of its own. Users Asha (Viewer),
  Ben (Developer), Cara (Tenant Admin) in ACME with MCP access, and Sam (Super Admin); project Sales with an empty
  scope. v2's GRDM sample was not used: too big (126 Bronze tables), one system, and a real company schema. Only the
  reference rows the demo needs are in it. The test database is built without it (`local_db.main(with_demo=False)`), because
  test fixtures make their own rows; `tests/test_demo_data.py` loads it inside each test's transaction.
- `90_roles.sql` (database logins for the apps) moves to step 5: locally the apps connect as the Postgres owner.
- App logins (step 5d, Nov 21): `gds_web_runtime` and `gds_mcp_runtime`, v2's names, each with read and write on
  every table and nothing else (no new tables). Logins belong to the whole Postgres server, so `90_roles.sql` keeps an
  existing login and its password and only grants; a new one gets its password by hand, never in a file. The preflight
  does not drop them. `99_verify_install.sql` checks both can read and write every table.
- Works on Maaz's laptop and in Claude's cloud session (web app and MCP only; no VS Code there).
- `uv run pytest` runs the tests against their own database, `gds_test`, rebuilt once per run, so `gds_local`
  is never touched. Each test runs in a transaction that is rolled back.

## How work happens

- Every AI step: **Run** makes a draft change set, you **review and adjust**, you press **Apply**.
- Apply saves the whole change set in one transaction, or nothing. A person reviews the draft, then presses Apply or
  tells the AI in chat to apply it, as in v2; the AI never applies without that yes (Nov 21, Maaz, from the Bridge
  discussion).
- Scope and profiling don't use AI. Code generation does: the AI writes the SQL from the mapping.
- Two kinds of Run in the web app, one shot and tool based. No automatic re-prompting or repair loops.
- The workflow flows (what each step reads and writes, and how a Run works) are in `design/`.
- No chat in the first version.

## Access tables (step 1a)

- One schema per area and numbered install files, the same pattern as v2 (file list in `plan.md`).
  Tables have an `id` column. No functions, no triggers.
- `00_preflight.sql` holds commented-out drops for a fresh install and stops unless the database is clean.
  `99_verify_install.sql` checks the install: expected tables, nothing extra, primary keys, no functions or
  triggers. Both use a short `DO` block; that is install checking, not app logic.
- `security.principal` (one person) holds email (lower case, how the web app finds you) and Microsoft object ID
  (how MCP finds you). Users, with both, are loaded by Maaz's own data load, like reference and foundational data;
  the apps never fill the object ID (Nov 21, Maaz).
  v2's separate identity table is folded in.
- No service principals for now; add them if something automated needs to sign in.
- `tenant_principal_access`: one row per person and tenant, with role, MCP access, who granted it.
  No end date (Nov 20, Maaz): access lasts until a Tenant Admin removes it, which deletes the row (no `is_active`
  flag). To shut a person out of every tenant at once, switch off their user (`principal.is_active`).
- `tenant_lock`: at most one per tenant, up to 4 hours. No lock history table.
- `tenant.tenant_visibility` is `global` or `private` (as in v2): every signed-in user can read a global tenant.

## Database patterns (every install file; the install scripts are the source of truth)

- Table names are singular and use the v2 names (`core.tenant`, `core.object`, `core.attribute`,
  `security.principal`).
- Column names are the v2 names. Every table has `<table>_id` (BIGINT identity) as its primary key, and its
  own fields carry the table name (`core.lane` has `lane_id`, `lane_code`, `lane_name`, `lane_description`;
  `core.attribute` has `attribute_id`, `attribute_name`). A foreign key column has the same name as the key
  it points at (`tenant.lane_id`, `object.zone_id`).
- Audit columns as in v2 on every table: `created_time`, `created_by`, `updated_time`, `updated_by`
  (`*_by` defaults to the database login). No triggers: `core/` sets `updated_time` and `updated_by`.
  `99_verify_install.sql` checks every table has them.
- The `value` JSONB column stays on every table that had it in v2.
- Named keys and checks: `pk_`, `fk_`, `uq_`, `ck_`; `ux_` unique indexes ignore upper/lower case and outer
  spaces; `ix_` indexes on foreign keys to other core/security tables. v2's extra keys that prove an
  attribute belongs to its object (lineage) and an object to its connection (process) are kept.

## Catalog, pipelines and reference lists (steps 1b and 1c)

- **Who a table belongs to, and the data lake** (Nov 21, Maaz): a table's owner is `object.source_tenant_id`. It
  decides who sees the table, scope and locks. Not a source connection: Silver and Gold come from many systems, so
  a source connection would have no single answer, and where a Bronze table came from is ingestion lineage. The data
  lake flag is on the tenant only (`is_data_lake`); `connection.is_global_data_store` is dropped so the two can
  never disagree, and `gds_connection_id` is renamed `data_lake_connection_id` (CATALOG-001).
  Locks follow the source tenant too (Nov 21, Maaz): changing ERP's Bronze table needs ERP's tenant lock and is
  blocked by ERP's catalog lock, never the data lake tenant's.
- **What tables you see from a tenant** (step 3c, Nov 21): `core.catalog.list_tables` lists the tables whose source
  tenant is that tenant, plus those of every active global tenant (marked `is_global`), because those are the tables
  its projects may scope (SCOPE-002). Never by the connection's tenant, so a member of the data lake tenant does not
  see other tenants' Bronze tables. Switched-off tables, and tables on a switched-off connection, are left out unless
  asked for. Each row says whether it can go into scope (`scope_001` and `scope_002`, the same functions 3d uses).
  Fixed order (zone, schema, name), 50 per page with the total, paged in SQL (Nov 21, Maaz). The scope-only filter
  in SQL is the SCOPE-001 zone check, using the same Python zone list; SCOPE-002 always holds for listed tables.

- Reference lists (`<list>_id`, `<list>_code`, `<list>_name`, `<list>_description`, `is_active`; as in v2,
  location type and the pipeline lists have no code, and their name is unique instead): system type, connection type,
  object type, zone, environment, location type, connection parameter, system notebook, chunk type,
  file type, data operation, process type.
- Not carried over: domain, currency, purge policy, pipeline and job type (nothing in v2 used them).
- Moved to later steps: context types (1d), Silver entity types (1e); Gold fact types were dropped later.
- Dropped flags: `attribute.is_mapped`, `attribute.is_purge`, `attribute.is_locked`, `object.is_locked`.
- Connections keep values per environment (`connection_value` + `connection_parameter`), as in v2.
  Foreign catalog fields stay.
- `copy_group_control` is not kept: it holds run state (last run time), not setup.
- Databricks will read the pipeline tables in future, not yet.

## Projects, workflow and change set tables (steps 1d to 1g)

- Same tables as v2, with the v3 patterns (`<table>_id` keys, named keys and checks, audit columns, no
  functions or triggers). Files `04` to `12` in `database/install/`; Notes have their own file (`05_project_context.sql`).
- The models keep the v2 words, operational and dimensional (Nov 18, Maaz): `operational_entity`,
  `operational_attribute`, `operational_entity_source`, `operational_attribute_source`, `operational_link`, and the
  same five with `dimensional_`. Mapping and code follow: `operational_object_mapping` + `operational_attribute_mapping`,
  `operational_code` + `operational_code_system`, and the same with `dimensional_`. The operational model builds
  the Silver zone and the dimensional model builds the Gold zone.
- Only top rows have `project_id` (Nov 18, Maaz): the project's own tables, entities, subject areas, validation
  groups, and analysis rows about a scope table. Child rows (Note, subject area table, mapping, code, code system,
  validation check, and the model rows below) point at their parent by id alone. New rules for what this gives up:
  SUBJECT-AREA-001, MAPPING-001, CODE-001 (Proposed).
- Operational and dimensional models (Nov 18, Maaz): only the entity has `project_id`. Attributes, entity sources,
  attribute sources and links point at their parent by id alone. An attribute source stores just the two attributes;
  a link stores just the child attribute and the parent entity. The cross checks this gives up (source table in
  scope, source column from one of the entity's source tables, same project) are rules in core/,
  OPERATIONAL-001 to 003 and DIMENSIONAL-001 to 003 in `docs/rules.md` (Approved Nov 18).
- Analysis rows about a scope table point at the scope row `(project_id, object_id)`, so they can only be about a
  table in the project's scope.
- Workflow rows have `is_locked` and no `is_active` or status: a row is removed by deleting it in an Apply,
  and the applied change set keeps what it looked like. Projects, scope rows, Note groups and Notes keep
  `is_active` (switch off, keep the work).
- `project.project_config`, one row per project, holds the settings v2 kept on the project row: the schema lists,
  SCD type per model (type 1 or type 2), naming instructions per model (free text; key names like `{Entity}Key`
  come from here), audit columns per model (a JSON list of the columns Python adds to every entity; with type 2
  it includes the history columns RecordStartTime, RecordEndTime, IsCurrentRecord), the two sample settings
  (`is_sample_storage_allowed`, default false; `sample_size`, default 5, maximum 10 in core/), and the default AI
  settings (model, reasoning effort, max turns, validation retry count; the model points at `reference.agent_model`). Empty naming or audit
  columns mean the defaults in core/, the same as v2 (core/ offers the type 1 or type 2 audit defaults).
  v2's technical columns template is folded into naming and audit columns (Nov 18, Maaz).
- The schemas a project's entities live in are two JSON lists on `project_config` (`operational_schemas`,
  `dimensional_schemas`, several each, as in v2). Each entity keeps its schema name as text.
- Coverage thresholds are left out until a check uses them.
- `project_version` replaces v2 `project_revision`. Project lock is `project.is_locked`.
- Sample values are one column on the profile, `attribute_profile.sample_values`, a JSON list of text (Nov 18,
  Maaz; no position or count). Profiling fetches and stores them, so they exist once a table is profiled.
  Profiling keeps v2's counts and percentages.
- Enrichment has `object_definition` and `object_grain` (v2 `object_description`) and `attribute_definition`.
- Entities have a definition and a Grain. Attributes mark the generated key with `is_surrogate_key` and the
  natural key with `is_natural_key`. Dimensional entities have `dimensional_entity_type` fact or dimension
  (no fact type: nothing downstream changes with it, Nov 18, Maaz). Operational entities have an optional entity type.
- Sources are tables (operational) or operational entities (dimensional) only; v2's Note as a source is gone. The
  note for mapping is `*_source_note`. A link is a child attribute pointing at a parent entity; any link is allowed.
- Entities store `*_entity_dependency_order` (load order, parents first). Python works it out from the links
  when a person runs it, and stores it; it is empty until then. Nobody types it by hand.
- Dropped from v2: link cardinality, basis and role name,
  bridge kind, mapping JSON documents and templates, code artifact type and git fields,
  digests, run ids (runs come in step 1h), project lock and event logs.
- Code: a source system of an entity is usually in only one of its code files; core/ warns, never blocks (CODE-001, Nov 20, Maaz).
- Note types are `reference.context_type`, filled by `database/seed/01_context_type.sql` (MERGE, safe to rerun).
  v2's `context_type_workflow` is gone: the prompt builder decides which types go to which step.
- Validation groups and checks are back, as in v2 (Nov 18, Maaz), split like mapping and code:
  `operational_validation_group` / `_check` and `dimensional_validation_group` / `_check` in
  `12_workflow_validation.sql`. A group belongs to a project and a source system. Postgres checks only that values
  are from their lists; which operator needs which value lives in core/ (v2 had it as long Postgres checks).
- Change sets keep v2's horizontal shape (Nov 18, Maaz), with one JSON list per table, one to one: every project and
  workflow table a person or VS Code can change has its own `*_document` in `application.project_change_set`
  (plus `project_config_document`, one record), and every catalog and pipeline table VS Code can change has its own
  document in `application.metadata_change_set` (`object`, `attribute`, ingestion mappings, copy groups, copies,
  member groups, members, process groups, processes). A new editable table gets its document in the same pull
  request. Status is receiving, draft, applied or rejected; project change sets record the project version they
  were built on. Apply saves every document in one transaction, parents first, or nothing.
- A push from VS Code is one upload through Azure storage, loaded into its change set in one go (see "Bridge"). The
  change set is receiving until the upload is loaded; Apply refuses a change set that is still receiving. The two
  chunk tables for pushes in pieces (`project_stage_chunk`, `metadata_stage_chunk`) and rules CHANGE-SET-006 and 010
  were dropped (Nov 21, Maaz): nothing uses them, and they can come back if a real need shows up.

- **Scope drafts** (step 3d1, Nov 21, Maaz): a draft holds only the changes, one record per table. A record names its
  table by row key only, in words: the connection's tenant code, system code, connection code, schema and name
  (compared like the `ux_` indexes, ignoring case and outer spaces). `is_active` and `is_locked` are the values to
  set on the scope row, not part of the key. Nothing is ever deleted; taking a table out switches its row off.
  Deleting is its own feature on the management page, later. Only the project's tenant lock counts, even for a
  table that sits in the lake or belongs to a global tenant. A record of the wrong shape is the caller's mistake
  (ValueError); a table that does not exist or may not be in scope is a problem in the saved draft. Checking a draft
  returns every problem at once, each with its rule ID and record number; Apply (3d2) refuses if any is found.
  SCOPE-001 and 002 are checked only for records that put a table in scope (`is_active` true); switching a table
  off is always allowed. CHANGE-SET-005 flags a Run or push only when it would change a locked row's values.
- **Applying a scope draft** (step 3d2, Nov 21): `apply_scope_draft` needs CHANGE, the project's tenant lock and an
  unlocked project. In one transaction it locks the project and change set rows (`FOR UPDATE`), so two Applies at
  the same moment cannot both pass the version check, then runs the same rule functions as `check_scope_draft`
  (one copy). Any problem: nothing is saved and the problems come back. Otherwise each record updates the
  project's scope row for its table or adds one (a switched-off row is switched back on, never duplicated); a
  record that switches off a table with no scope row does nothing; the change set is marked applied with who and
  when; the project version goes up by one. It returns the list of problems, empty when applied.
  `tests/test_apply_concurrent.py` proves the row lock with two real connections: the second Apply waits, then gets
  CHANGE-SET-002. Without `FOR UPDATE` both drafts were applied, so the version check alone is not enough.
- **Rejecting a scope draft** (step 3d3, Nov 21): `reject_scope_draft` needs the same as Apply (CHANGE, the project's
  tenant lock, an unlocked project) and works on a draft, or on a change set still receiving (CHANGE-SET-001, changed Nov 21, Maaz). It marks the change set rejected
  with who and when; the project, its scope and its version do not change. An out-of-date draft (CHANGE-SET-002)
  can still be rejected, which is how it is cleared. Like Apply, it returns the problems that stopped it.

## Kept from v2

- Change sets (metadata and project) with review and all-or-nothing Apply.
- Tenants, users from Microsoft sign-in, roles (Viewer, Developer, Tenant Admin; v2's Architect is dropped, Nov 20), Super Admin,
  MCP access switch, project lock, **tenant lock**.
- Metadata catalog in Postgres, including ingestion and processing pipeline tables.
- Bridge and Local Workbench.

## Dropped from v2

- Logic in Postgres functions.
- Copies of rules in JavaScript and PowerShell; PowerShell twins.
- Snapshots, staging chunks, digests, receipts.
- Worker queue, claims, heartbeats, retries.
- Prompt Studio and the layers around prompts (variables, readers, assignments).
- Configurable mapping templates. Mapping has one fixed shape.

## Prompts

- Two tables in `14_application_prompts.sql` (Nov 18, Maaz): `application.prompt` (v2 `prompt_template`) and
  `application.prompt_version` (v2 `prompt_template_version`; every save is a new row, rows never change).
- A prompt is for one step (`project_workflow`) and one kind of Run (`workflow_execution_mode`, `one_shot` or
  `tool_assisted`). Steps: object enrichment, attribute enrichment, analysis, subject area, operational, dimensional,
  operational and dimensional mapping, code and validation. Profiling has no prompt (no AI).
- Prompts are global (`tenant_id` empty) or belong to one tenant (Nov 18, Maaz). One default per step and kind of
  Run among the global prompts, and one per tenant. A Run uses the tenant's default if there is one, otherwise the
  global default (core/ decides). Starter prompts are seeded as global prompts, so a new tenant works at once.
- A version has two texts, `system_prompt` and `instruction_prompt`. A tool based prompt explains its tools in its
  system prompt (v2's separate tool instructions are dropped, Nov 18, Maaz).
- A Run uses the latest version unless the person picks another. No publish or retire step.
- Saving a prompt writes a new version directly, not through a change set: prompts are app settings, not project data.
- Dropped from v2: prompt code, workflow stage tables, ownership scope column, publish and retire status, digest,
  agent tool names (the tools come from the code for each step), prompt assignments.
- At Run you pick a prompt version and can add extra instructions for that run. Each run records both.
- VS Code reads the same prompts through MCP.

## Runs (step 1h, Nov 19, Maaz)

- Three tables in `15_application_runs.sql`: `application.run` (v2 `workflow_run`), `application.run_event` (the Run
  log, v2 `project_event_log`) and `application.run_model_request` (AI usage, one row per AI call, v2
  `workflow_run_model_request`). Cost per tenant or project is a join through the Run.
- **One Run at a time per tenant**; Runs in different tenants run at the same time. Per tenant, not per project,
  because metadata is per tenant and VS Code can link projects. `run` has `tenant_id` so a unique index on running
  Runs can enforce it, even when two people press Run at once. RUN-001 (Approved) checks it is the project's tenant.
- If the server stops in the middle of a Run, its row stays running. core/ marks a Run running for over 4 hours
  (the tenant lock limit) as failed before starting the next one. That frees the tenant; it is not a retry.
- Status is running, completed or failed. No queue, claims, heartbeats, recovery, digests or cancel.
- What the person picked goes in one JSON column, `run_request_document`, instead of v2's six selection tables.
  The prompt version is stored on the Run; versions never change, so no prompt snapshot is needed.
- The AI settings are copied onto the Run from `project_config` (or changed for that Run). Profiling has no AI,
  no prompt and no kind of Run.
- The Run points at the draft it made (`run.project_change_set_id`); change sets know nothing about Runs (Nov 19, Maaz),
  so VS Code pushes and hand edits are unchanged and step 1g's change set tables stay as they were (source `ai_run`).
  The review page finds the Run that made a draft with one lookup. Workflow rows have no run id (v2 had one on every
  row): the applied change set and its Run say who made them.
- Left out for now: budgets (add with cost control) and the MCP tool call log (decide at step 4b).
- **AI providers and models are lists** (Nov 19, Maaz): `reference.agent_provider` and `reference.agent_model`, filled by
  the seed and changeable later. A provider is the calling code in core/ (v2's SDK and provider are one thing now):
  `foundry_openai` and `foundry_anthropic` are two providers because their code differs, and a custom API would be a
  third. A new model of a known provider is just a new row. A model has the name the API expects (exactly the
  Foundry name), a display name for the web app, its reasoning efforts (a JSON list of codes)
  and its prices per million tokens (input, cached input, cache write, output; reasoning is billed as output).
  Endpoints and keys are app settings, not in these tables.
- The seed `database/seed/02_agent_provider_model.sql` (MERGE, safe to rerun) holds v2's three Foundry models with their
  Global Standard prices (Nov 19). A model with no price gives an empty cost.
- Every seed file is a MERGE: running it again updates existing rows and never adds duplicates (Nov 19, Maaz).
- `project_config` and `run` point at the model (`default_agent_model_id`, `agent_model_id`); the provider comes from the
  model. core/ works out each AI call's cost from the model's prices and stores it in `run_model_request.cost_usd`,
  so a later price change does not change past Runs. RUN-002 (Approved) checks the reasoning effort is one the model allows.

## Mapping

- Separate steps for Silver mapping (Source or Bronze to Silver) and Gold mapping (Silver to Gold).
- One mapping per target entity and source system, in two parts: an entity part (tables, rows to keep,
  sample query, transformation) and one free-text line per attribute.
- A mapping uses only the model as context, never another mapping. A lookup's facts about the parent come from the model.
- The AI writes the SQL from the applied mapping. Python may prepare a starter SQL.
- The SQL only gives the final data frame. The orchestrator loads it, usually a merge on the natural key.

## Path review (Nov 18)

Decisions from the review of the path from subject areas to code. The flows are in `design/`.

- The user controls, not the system. Few rules, checks and tests.
- Definition and Grain are two separate fields, on enriched source tables and on entities.
- Sample values per column, stored only if the project allows it. Two project settings: may samples be stored, and sample size.
- A table can be in more than one subject area. No area is an entity's "home": every Run builds as completely
  as it can, and the next Run builds on top.
- Related tables outside the area are given to a Run, one step out, marked as related.
- Silver and Gold models are two sets of tables with the same shape. Gold reads Silver only. Any Gold link is allowed.
- Notes for mapping sit on the entity source and attribute source rows. They say how, not why.
- Every entity marks its natural key.
- Code is stored like v2: a code file belongs to an entity and lists the systems it covers.
- Notes keep the v2 tables (`context_group`, `context_record`) plus `context_type` from the seed. The prompt builder
  decides which types go to which step. An Agent type serves VS Code. House standards are starter Notes.
- Scope and profiling stay as v2.
- Left for when each workflow is built: exactly what each Run is given, tools, prompts, Excel export and import of mappings.

## Rules and checks

- Every rule lives in its group file under `docs/rules/` (index `docs/rules.md`) with an ID, what it means, why,
  what happens and an example. Only Approved rules get built. Every problem shown to a user names its rule ID.
- Non-obvious database checks are listed in the same group files, with their constraint names (Nov 20, Maaz).

## Access and rules review (Nov 20)

- Three roles: Viewer, Developer, Tenant Admin. v2's Architect is dropped; Developers change the catalog and projects.
- Three permissions in code, not in tables: `READ`, `CHANGE` (includes taking the tenant lock), `MANAGE_TENANT`.
  One function, `require`, makes every access check in a fixed order (`design/shared/access.md`).
- Membership has no end date; a Tenant Admin removes it (deletes the row), or the user is switched off.
- MCP access, the project lock and the proposed catalog lock are switches on the row they control, set by a Tenant
  Admin. The tenant lock stays a hold of at most 4 hours.
- Change sets never carry database ids. Records name rows by row key, looked up only inside the change set's
  project or tenant catalog. The database enforces a row key on every table people write
  (`docs/rules/row-keys.md`). "Row key" (our own tables) is kept apart from "natural key" (the source data's id). A link stays one per attribute.
- A relationship is keyed by project + from column + to column; its kind is a field.
- CODE-001 is a Warning, not a block: rare special cases are allowed.
- Nov 21 (Maaz): MCP access is needed by every role, Tenant Admins included; Super Admins always have it.
  SCOPE-002 approved (own tenant or global tenant only). A tenant has a metadata version
  (`tenant_metadata_version`, with `base_metadata_version` on metadata change sets) and a catalog lock
  (`is_metadata_locked`); named "metadata" because `tenant_catalog` already means the Databricks catalog.
  The process key stays as it is. A Note's row key is a small Note number in its group (`context_record_number`), not a title.
- Nov 21 (Maaz): a Silver entity can be built from any Source or Bronze table in the project's scope, not only Bronze.
