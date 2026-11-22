# Operations: Databricks tools

Three tools for the work that needs Databricks, which a laptop cannot reach. They take v2's ideas (batch IDs, the
environment, the SQL policy) and none of its hidden checks. They are built with the profiling step, not with the
Bridge. Columns and the rules every call gets are in the [README](README.md). Agreed with Maaz on Nov 21.

## Operations

| # | Operation | Web | MCP tool | `core/` | Needs |
|---|---|---|---|---|---|
| X1 | Start a profiling Run: measure the columns of scope tables with queries the server writes, and save the profiles through a change set | Run button on the profiling page | `start_profiling_run` | `runs.start_run`, then `profiling.run` | `CHANGE` |
| X2 | See a profiling Run: status, how far it is, the change set it applied and the new project version | the Run page | `get_profiling_run` | `runs.get_run` | `READ` |
| X3 | Run a person's own read-only SQL on Databricks | - | `execute_databricks_sql` | `databricks.execute_sql` | `READ` and SQL access (ACCESS-010) |

**Decided (Nov 21, Maaz)**

- **Batch IDs, as in v2.** A table can name a batch column (`core.object.batch_attribute_name`). A profiling Run
  takes one list of batch IDs, 1 to 2000 values. Every chosen table that has a batch column is measured only on rows
  in those batches; a table without one is measured whole. If any chosen table has a batch column and no batch IDs
  are given, the Run is refused. Batch IDs usually belong to one system, so systems with different batches are
  profiled in separate Runs.
- **Environment.** Both tools take `environment_code`, `dev` if left out. It picks which Databricks connection
  values are used.
- **A profiling Run applies its own change set.** When the queries are done, the Run puts the profiles into a draft
  change set and applies it itself. It uses the same Apply as everything else and the project version goes up by one,
  but there is nothing to review or click, because profiles are measurements, not proposals. If that Apply is
  refused (for example the tenant lock ran out during a long Run), the Run is marked failed with the reason and the
  draft stays, so it can be applied or rejected by hand and the measuring is not lost.
- **No masking check.** v2 refused to profile columns that need masking. v3 does not: masking is the ingestion
  process's job.
- **No cancel tool**, as decided for Runs in v3. v2 had one.
- **SQL access switch.** `execute_databricks_sql` is refused unless the person's SQL access is on in that tenant
  (`security.tenant_principal_access.sql_access_enabled`, off by default, set by a Tenant Admin; Super Admins always
  have it). Rule ACCESS-010. The tool is never built without the switch. Any role may use the tool when the switch
  is on, because the switch is the control.
- **SQL policy, as in v2.** Up to 25 statements. Reads, `SHOW`, `DESCRIBE`, and temporary views or tables without a
  schema in the name. Every real table must be written as catalog.schema.table. No other statements and no secret
  functions. The answer is the rows of the last statement, at most 50. The SQL is checked with the `sqlglot`
  library before anything runs (package approved Nov 21). Each part of this policy still gets written as a rule
  before it is built.
- **Values are returned as they are.** v2 also cut long values short; that is left out to keep the code simple.

## The tools

### `start_profiling_run`

**Used for:** getting the column counts and sample values for the tables in scope, which every later step builds on.

```json
Input
{
  "tenant_code": "ACME",
  "project_name": "Sales",
  "environment_code": "dev",
  "batch_ids": ["20261120001", "20261121001"],
  "tables": [
    { "tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
      "object_schema": "bronze_erp", "object_name": "orders" }
  ]
}

Output
{
  "run_id": 981,
  "project_workflow": "profiling",
  "run_status": "running",
  "base_project_version": 7,
  "started_time": "2026-11-21T14:30:00Z",
  "table_count": 1
}
```

- `tables` is optional. Left out, every active table in scope is profiled, which is the usual case and needs no
  list. Given, each table is named by its row key. No ids.
- `batch_ids` and `environment_code` as decided above.
- The server writes the queries. The caller sends no SQL and no numbers.
- Needs the tenant lock. Refused while another Run is running in the tenant.
- The tables, batch IDs and environment are kept on the Run in `run_request_document`. Worked out: `table_count`.

### `get_profiling_run`

**Used for:** waiting for the Run to finish, seeing how far it is or why it failed, and knowing the new project
version when it is done.

```json
Input
{ "run_id": 981 }

Output
{
  "run_id": 981,
  "tenant_code": "ACME",
  "project_name": "Sales",
  "project_workflow": "profiling",
  "run_status": "completed",
  "run_request_document": {
    "environment_code": "dev",
    "batch_ids": ["20261120001", "20261121001"],
    "tables": [
      { "tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
        "object_schema": "bronze_erp", "object_name": "orders" }
    ]
  },
  "table_count": 1,
  "tables_done": 1,
  "base_project_version": 7,
  "started_by_display_name": "Ben",
  "started_time": "2026-11-21T14:30:00Z",
  "completed_time": "2026-11-21T14:33:10Z",
  "failure_message": null,
  "project_change_set_id": 413,
  "project_change_set_status": "applied",
  "project_version": 8
}
```

`run_status` is `running`, `completed` or `failed`. Worked out: `table_count` and `tables_done`, so the AI can say
"14 of 22 tables".

### `execute_databricks_sql`

**Used for:** looking at real data when the profile is not enough, for example to check a join or try a mapping's
query.

```json
Input
{
  "tenant_code": "ACME",
  "system_code": "ERP",
  "connection_code": "erp_prod",
  "environment_code": "dev",
  "sql": "SELECT status, count(*) AS n FROM acme_prod.bronze_erp.orders GROUP BY status"
}

Output
{
  "tenant_code": "ACME",
  "system_code": "ERP",
  "connection_code": "erp_prod",
  "environment_code": "dev",
  "statement_count": 1,
  "row_limit": 50,
  "columns": ["status", "n"],
  "rows": [["OPEN", 1204], ["CLOSED", 88031]],
  "row_count": 2,
  "rows_truncated": false
}
```

- The first three inputs are the row key of one of the tenant's own connections, as in v2. The server finds the
  tenant's data lake connection and that environment's Databricks values itself. The caller never sees a host or a
  token.
- `rows_truncated` says when there were more than 50 rows.
