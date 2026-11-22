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
