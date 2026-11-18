# Design decisions

Short list of what we decided and why. Add to it when something new is decided.
The full design page from the planning thread has more detail; this file is the source of truth.

## Pieces

- **core/**: one Python folder with all the logic: reading and writing Postgres, checks, change sets, Apply,
  SQL generation. Everything else is a thin door into it.
- **Web app**: FastAPI backend + React pages, deployed as a **Databricks App**. Step-by-step workflows with
  a Run button. Also where AI cost is controlled.
- **MCP server**: deployed on **Azure App Service**, because VS Code can sign in there with Microsoft and
  no client ID on laptops. Also serves the Bridge's pull, check and push.
- **Plugin**: skills (text) and the MCP address.
- **Bridge**: VS Code extension. Pull, check, push. Moves big data without passing it through the AI,
  which keeps AI cost down.
- **Local Workbench**: review and edit local files before pushing.
- **Postgres** (Azure): data only. No functions holding logic.

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

## Local testing

- Throwaway Postgres with install, seed and demo data (`database/demo/`, never sent to Azure).
- Web app and MCP server run on localhost. Local sign-in: pick a demo user, so each role can be tried.
- Fake AI gives a saved answer per step. Fake Databricks reads small sample tables from files.
- Works on Maaz's laptop and in Claude's cloud session (web app and MCP only; no VS Code there).

## How work happens

- Every AI step: **Run** makes a draft change set, you **review and adjust**, you press **Apply**.
- Apply saves the whole change set in one transaction, or nothing. Only a person applies, never the AI.
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
  (how MCP finds you).
  v2's separate identity table is folded in.
- No service principals for now; add them if something automated needs to sign in.
- `tenant_principal_access`: one row per person and tenant, with role, MCP access, who granted it, and an
  optional expiry.
  Removing access deletes the row (no `is_active` flag).
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

- Reference lists (`<list>_id`, `<list>_code`, `<list>_name`, `<list>_description`, `is_active`; as in v2,
  location type and the pipeline lists have no code, and their name is unique instead): system type, connection type,
  object type, zone, environment, location type, connection parameter, system notebook, chunk type,
  file type, data operation, process type.
- Not carried over: domain, currency, purge policy, pipeline and job type (nothing in v2 used them).
- Moved to later steps: context types (1d), Silver entity types and Gold fact types (1e).
- Dropped flags: `attribute.is_mapped`, `attribute.is_purge`, `attribute.is_locked`, `object.is_locked`.
- Connections keep values per environment (`connection_value` + `connection_parameter`), as in v2.
  Foreign catalog fields stay.
- `copy_group_control` is not kept: it holds run state (last run time), not setup.
- Databricks will read the pipeline tables in future, not yet.

## Kept from v2

- Change sets (metadata and project) with review and all-or-nothing Apply.
- Tenants, users from Microsoft sign-in, roles (Viewer, Developer, Architect, Tenant Admin), Super Admin,
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

- Two tables: `prompts` (per step, one default) and `prompt_versions` (every save is a new version).
- At Run you pick a prompt version and can add extra instructions for that run. Each run records both.
- VS Code reads the same prompts through MCP.

## Mapping

- Separate steps for Silver mapping (Bronze to Silver) and Gold mapping (Silver to Gold).
- One mapping per target entity and source system, in two parts: an entity part (source tables, joins, rows to
  keep, one row per entity, transformation) and one free-text line per attribute.
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

- Every rule lives in `docs/rules.md` with an ID, plain-English text and an example. Only Approved rules
  get built. Every problem shown to a user names its rule ID.
