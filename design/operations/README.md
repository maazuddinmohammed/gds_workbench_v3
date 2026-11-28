# Operations

One line per operation, so the web app, the MCP server and the Bridge share one function in `core/` for each thing
the product does (Nov 21, Maaz). A workflow gets its file here before it is built, Maaz reviews it, then it is built
vertically: rules, `core/`, the web route and the MCP tool together.

The MCP tools below were gone over with Maaz one by one on Nov 21 and are agreed: **20 tools in three groups**.
Each file also holds the exact input and output of its tools.

## Files

| File | Holds | Tools |
|---|---|---|
| [shared.md](shared.md) | Tenants, projects and the tenant lock | 7 |
| [change-sets.md](change-sets.md) | Snapshots (pull) and change sets (push, validate, apply, reject): the one engine every workflow uses | 10 |
| [databricks.md](databricks.md) | Profiling runs and running SQL on Databricks | 3 |
| [scope.md](scope.md) | Scope, the one workflow built so far | none of its own |

Not written yet. Each gets its file before it is built: catalog and pipelines pages, project settings and Notes, Runs
and prompts in the web app, each workflow step (enrichment to validation), the admin page.

## The columns

| Column | What it says |
|---|---|
| # | A short name for the line, so we can say "C4". |
| Operation | What it does, in plain words. |
| Web | The web route. |
| MCP tool | The tool name for the AI in VS Code. |
| `core/` | The one function behind every door. |
| Needs | `READ`, `CHANGE` or `MANAGE_TENANT` (see [access.md](../shared/access.md)). |

**Built** means it exists on main with tests. Everything else is planned. A dash means that door does not use the
operation. Names of web routes that are not built yet are proposals; they are settled when their page is designed.

## Rules every call gets

So the tables do not repeat them. All come from `require`.

- Every call: ACCESS-001 (you can read the tenant, otherwise "not found").
- Every MCP call: ACCESS-004 (your MCP access is on).
- Every change: ACCESS-002 (your role may change), ACCESS-003 (you hold the tenant lock), and CHANGE-SET-004
  (project not locked) or CHANGE-SET-011 (catalog not locked).

## How a tool's fields are chosen

1. **Each tool has a job.** Its answer carries what the AI needs for that job and its next step, and nothing else.
   Each tool starts with a "Used for" line.
2. **A stored value keeps its exact column name**, in inputs and outputs: `tenant_code`, `tenant_metadata_version`,
   `project_change_set_status`. Never a short alias.
3. **A value that is worked out, not stored, is named as such** under the tool (`permissions`, `is_yours`, `counts`).
4. **Left out of every tool:** database ids (a change set and a Run are the exceptions, because their id is how you
   name them), the four audit columns, the free-form `value` column, and rows that are switched off.
5. **Explicit over clever.** A tool never guesses what you mean from a missing input. Actions that differ in intent are
   separate tools (release your lock, override someone else's).
6. **No checks that are not Approved rules.** v2's hidden checks are not carried over.

## What every tool shares

- A refusal is a tool error that starts with the rule ID, for example
  `ACCESS-003: Asha holds the lock on ACME until 14:30.`
- Times are written like `2026-11-21T14:30:00Z`.
- A **row key** names a row without ids. A table's row key is five fields: `tenant_code`, `system_code`,
  `connection_code`, `object_schema`, `object_name`.
- Nothing is ever deleted by a tool. A row is switched off (`is_active` false). Deleting for good is a separate
  process on the management screen.

## All operations: web routes and MCP tools (agreed Nov 28, Maaz)

One `core/` function behind each line. A dash means that door does not have it. ✓ means built. 37 web routes and
20 MCP tools. Creating a project is web only and saved directly (one row). Exports are not in v1 (Nov 28, Maaz).

**1. Session, projects, tenant lock**

| # | Operation | Web route | MCP tool |
|---|---|---|---|
| 1.1 | Who am I, my tenants, what I may do | `GET /api/session` (built as `/api/me`) | `list_tenants` |
| 1.2 | Home tiles: systems, projects, drafts, the Run going | `GET /api/tenants/{tenant_id}/summary` | - |
| 1.3 | List projects | `GET /api/tenants/{tenant_id}/projects` ✓ | `list_projects` ✓ |
| 1.4 | Create a project | `POST /api/tenants/{tenant_id}/projects` | - |
| 1.5 | One project: version, lock, settings, counts | `GET /api/projects/{project_id}` | `get_project_detail` |
| 1.6 | Who holds the lock | `GET /api/tenants/{tenant_id}/lock` ✓ | `check_tenant_lock` |
| 1.7 | Take or renew the lock | `POST /api/tenants/{tenant_id}/lock` ✓ | `acquire_tenant_lock` |
| 1.8 | Release your own lock | `DELETE /api/tenants/{tenant_id}/lock` ✓ (today it releases anyone's) | `release_tenant_lock` |
| 1.9 | End someone else's lock | `POST /api/tenants/{tenant_id}/lock/override` | `override_tenant_lock` |

**2. Snapshots and change sets**

| # | Operation | Web route | MCP tool |
|---|---|---|---|
| 2.1 | Make a snapshot (pull) | - | `create_snapshot` |
| 2.2 | Open a change set for a push | - | `start_change_set` |
| 2.3 | Get an upload link | - | `start_change_set_upload` |
| 2.4 | Load the upload | - | `load_upload_into_change_set` |
| 2.5 | Save a hand edit as a project draft | `POST /api/projects/{project_id}/change-sets` (built as `/scope-drafts`) | - |
| 2.6 | Save a hand edit as a metadata draft | `POST /api/tenants/{tenant_id}/change-sets` | - |
| 2.7 | List change sets, both kinds, newest first | `GET /api/tenants/{tenant_id}/change-sets` | `list_change_sets` |
| 2.8 | One change set: status and counts | `GET /api/change-sets/{kind}/{change_set_id}` (built for scope) | `get_change_set` |
| 2.9 | What it adds, changes or switches off | `GET /api/change-sets/{kind}/{change_set_id}/changes` | `list_change_set_changes` |
| 2.10 | Problems, worked out fresh | `GET /api/change-sets/{kind}/{change_set_id}/problems` | `validate_change_set` |
| 2.11 | Apply | `POST /api/change-sets/{kind}/{change_set_id}/apply` (built for scope) | `apply_change_set` |
| 2.12 | Reject | `POST /api/change-sets/{kind}/{change_set_id}/reject` (built for scope) | `reject_change_set` |

**3. Reading the catalog and a project** (web only: in VS Code the snapshot holds this)

| # | Operation | Web route |
|---|---|---|
| 3.1 | Tables list | `GET /api/tenants/{tenant_id}/tables` ✓ |
| 3.2 | One table in full | `GET /api/tenants/{tenant_id}/tables/{object_id}` |
| 3.3 | Other metadata records, paged | `GET /api/tenants/{tenant_id}/records/{part}` |
| 3.4 | One fixed list, for a dropdown | `GET /api/reference/{list}` |
| 3.5 | The scope | `GET /api/projects/{project_id}/scope` ✓ |
| 3.6 | The records of one project part | `GET /api/projects/{project_id}/records/{part}` |

**4. Runs**

| # | Operation | Web route | MCP tool |
|---|---|---|---|
| 4.1 | Press Run on any step | `POST /api/projects/{project_id}/runs` | `start_profiling_run` (profiling only) |
| 4.2 | One Run: status (running, completed, stopped, failed) and its draft | `GET /api/runs/{run_id}` | `get_profiling_run` |
| 4.3 | The Run log | `GET /api/runs/{run_id}/events` | - |
| 4.4 | Models and the efforts each allows | `GET /api/models` | - |

**5. Prompts** (web only)

| # | Operation | Web route |
|---|---|---|
| 5.1 | List prompts | `GET /api/tenants/{tenant_id}/prompts` |
| 5.2 | One prompt with its versions | `GET /api/prompts/{prompt_id}` |
| 5.3 | Save a new version | `POST /api/prompts/{prompt_id}/versions` |
| 5.4 | Set the default | `PUT /api/prompts/{prompt_id}/default` |

**6. Admin, and the rest**

| # | Operation | Web route | MCP tool |
|---|---|---|---|
| 6.1 | List members | `GET /api/tenants/{tenant_id}/members` | - |
| 6.2 | Find a person to add | `GET /api/users` | - |
| 6.3 | Add a member, or set role and switches | `PUT /api/tenants/{tenant_id}/members/{principal_id}` | - |
| 6.4 | Remove a member | `DELETE /api/tenants/{tenant_id}/members/{principal_id}` | - |
| 6.5 | Lock or unlock the catalog | `PUT /api/tenants/{tenant_id}/metadata-lock` | - |
| 6.6 | Lock or unlock a project | `PUT /api/projects/{project_id}/lock` | - |
| 6.7 | Run SQL on Databricks | - | `execute_databricks_sql` |
| 6.8 | Health | `GET /health` ✓ | - |

The exact inputs and outputs of each route are written in its group's file when it is built.

## All 20 MCP tools

| # | Tool | File | Changes anything? |
|---|---|---|---|
| 1 | `list_tenants` | shared | no |
| 2 | `list_projects` | shared | no |
| 3 | `get_project_detail` | shared | no |
| 4 | `check_tenant_lock` | shared | no |
| 5 | `acquire_tenant_lock` | shared | the lock |
| 6 | `release_tenant_lock` | shared | the lock |
| 7 | `override_tenant_lock` | shared | the lock |
| 8 | `create_snapshot` | change-sets | no (writes a zip to storage) |
| 9 | `start_change_set` | change-sets | opens a change set |
| 10 | `start_change_set_upload` | change-sets | no |
| 11 | `load_upload_into_change_set` | change-sets | fills the change set |
| 12 | `validate_change_set` | change-sets | no |
| 13 | `get_change_set` | change-sets | no |
| 14 | `list_change_set_changes` | change-sets | no |
| 15 | `list_change_sets` | change-sets | no |
| 16 | `apply_change_set` | change-sets | saves the change set |
| 17 | `reject_change_set` | change-sets | closes the change set |
| 18 | `start_profiling_run` | databricks | starts a Run that saves profiles |
| 19 | `get_profiling_run` | databricks | no |
| 20 | `execute_databricks_sql` | databricks | no |

**Not tools, on purpose (Nov 21, Maaz).** There are no tools that list tables, describe a table, read the scope, read
a project's records, read Notes or read prompts. A snapshot holds all of that as files, which the AI can search
without tool calls. In VS Code the plugin's skills are the instructions; the prompts in the database are for Runs in
the web app. The one tool built in step 4b, `see_project_scope`, goes away once `create_snapshot` exists.

**Logging of MCP tool calls** is its own topic, to be studied from v2 and designed as its own step.
