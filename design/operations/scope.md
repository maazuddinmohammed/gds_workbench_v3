# Operations: scope

Scope is the list of Source and Bronze tables a project works on. It is the one workflow built so far, on the web
side (steps 3 and 4a). Columns and the rules every call gets are in the [README](README.md).

## Operations

| # | Operation | Web | MCP tool | `core/` | Needs |
|---|---|---|---|---|---|
| S1 | List the tables you may put in scope: your tenant's and every global tenant's, 50 per page, with filters | `GET /api/tenants/{t}/tables` **Built** | - (a metadata snapshot holds them) | `catalog.list_tables` **Built** | `READ` |
| S2 | See the project's current scope | `GET /api/projects/{p}/scope` **Built** | - (`scope.json` in a project snapshot). `see_project_scope` is **Built** and goes away once `create_snapshot` exists | `projects.current_scope` **Built** | `READ` |
| S3 | Change the scope: add a table, switch one off or on, lock or unlock one | a draft with scope records (C1) **Built** | - (edit `scope.json` and push) | the scope part of the change set engine: its record shape, SCOPE-001 and 002, and how a record is saved **Built** | `CHANGE` |

- Validate, review, Apply and Reject are the change set operations in [change-sets.md](change-sets.md). Scope has none
  of its own.
- Rules for S3: SCOPE-001 (zone), SCOPE-002 (own tenant or a global one), CHANGE-SET-005 (a Run or push cannot change
  a locked row or switch it off), and the database's SCOPE-003 and 004.
- From VS Code there is no "change scope" tool on purpose. The AI edits `scope.json` and pushes, like every other
  change.

## One scope record

The same shape in a web draft, in `scope.json` and in a change set:

```json
{ "tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
  "object_schema": "bronze_erp", "object_name": "orders",
  "is_active": true, "is_locked": false }
```

The first five fields are the table's row key. `is_active` false takes the table out of scope; nothing is deleted.
