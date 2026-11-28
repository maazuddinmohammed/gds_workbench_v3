# Operations: tenants, projects and the tenant lock

Every page and every AI session starts here: who am I, where may I work, and who holds the lock. Columns and the
rules every call gets are in the [README](README.md). Agreed with Maaz on Nov 21.

## Operations

| # | Operation | Web | MCP tool | `core/` | Needs |
|---|---|---|---|---|---|
| A1 | Who am I, which tenants can I read, and what may I do in each | `GET /api/me` **Built** | `list_tenants` **Built** | `access.find_user` (web), `access.find_user_by_object_id` (MCP), `access.my_tenants` **Built**; gains the tenant fields below | `READ` |
| A2 | List a tenant's projects | `GET /api/tenants/{t}/projects` **Built** | `list_projects` **Built** | `projects.list_projects` **Built** | `READ` |
| A3 | See one project: version, locked or not, its settings, how many rows each part has | `GET /api/projects/{p}` | `get_project_detail` **Built** | `projects.get_project_detail` **Built** | `READ` |
| L1 | See who holds the tenant lock, since when and until when | `GET /api/tenants/{t}/lock` **Built** | `check_tenant_lock` **Built** | `tenant_lock.current_lock` **Built** | `READ` |
| L2 | Take the tenant lock for 1 minute to 4 hours, or renew it | `POST /api/tenants/{t}/lock` **Built** | `acquire_tenant_lock` **Built** | `tenant_lock.take_lock` **Built** | `CHANGE` |
| L3 | Release your own lock | `DELETE /api/tenants/{t}/lock` **Built** | `release_tenant_lock` **Built** | `tenant_lock.release_lock` **Built** | `CHANGE` |
| L4 | Override: end someone else's lock | `POST /api/tenants/{t}/lock/override` **Built** | `override_tenant_lock` **Built** | `tenant_lock.override_lock` **Built** | `CHANGE` |

- L2 to L4 need only your role to allow changes (ACCESS-002). You cannot hold the lock before you take it.
- **Release and override are two actions (Nov 21, Maaz), as in v2.** Release is for your own lock and is refused when
  someone else holds it. Override ends someone else's lock, as its own explicit action. It does not hand the lock to
  you; you acquire it as a separate step. Anyone who may change the tenant may override: Developers, Tenant Admins and
  Super Admins. The web page and the skill ask the person first. Built in step 4c1 (Nov 28); it replaced the one
  function and one Release button of steps 3b and 4a4b.
- There is no renew tool: acquiring again while you hold the lock starts your time over.

## The tools

### `list_tenants`

**Used for:** picking the tenant to work in, and knowing before anything else what you may do there: your role, whether
MCP and SQL access are on, whether the catalog can be changed, and where the tenant's data sits in Databricks.

```json
Input
{}

Output
{
  "user": {
    "principal_display_name": "Ben",
    "principal_email": "ben@acme.example",
    "is_super_admin": false
  },
  "tenants": [
    {
      "tenant_code": "ACME",
      "tenant_name": "Acme",
      "tenant_description": "Acme group, ERP, CRM and HR",
      "tenant_catalog": "acme_prod",
      "tenant_visibility": "private",
      "is_data_lake": false,
      "data_lake_connection": { "tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us" },
      "tenant_metadata_version": 3,
      "is_metadata_locked": false,
      "tenant_role": "developer",
      "mcp_access_enabled": true,
      "sql_access_enabled": false,
      "permissions": ["CHANGE", "READ"]
    }
  ]
}
```

- From `core.tenant`: code, name, description, `tenant_catalog` (the Databricks catalog), visibility, `is_data_lake`,
  `tenant_metadata_version`, `is_metadata_locked` (the catalog lock).
- `data_lake_connection` is the row key of the lake connection the tenant's Bronze, Silver and Gold tables land in
  (`data_lake_connection_id`). Empty when none is set.
- From your membership: `tenant_role` (`viewer`, `developer`, `tenant_admin`), `mcp_access_enabled` and
  `sql_access_enabled` (ACCESS-010).
- Worked out: `permissions`, from the role. In a global tenant you are not a member of, the role is `viewer`.
- Left out: `lane_id` and `gds_admin_catalog`. Nothing the AI does depends on them.

### `list_projects`

**Used for:** picking the project, and seeing at once whether it is locked.

```json
Input
{ "tenant_code": "ACME" }

Output
{
  "tenant_code": "ACME",
  "projects": [
    {
      "project_name": "Sales",
      "project_description": "Sales reporting model",
      "project_version": 7,
      "is_locked": false
    }
  ]
}
```

Only active projects are listed.

### `get_project_detail`

**Used for:** knowing how to model in this project before touching anything (schemas, naming, SCD type, audit columns,
whether samples may be stored), seeing how far the project is, and checking whether pulled files are still current.

```json
Input
{ "tenant_code": "ACME", "project_name": "Sales" }

Output
{
  "tenant_code": "ACME",
  "project_name": "Sales",
  "project_description": "Sales reporting model",
  "project_version": 7,
  "is_locked": false,
  "project_config": {
    "operational_schemas": [ { "schema_name": "silver", "description": "Normalized model" } ],
    "dimensional_schemas": [ { "schema_name": "gold", "description": "Facts and dimensions" } ],
    "operational_entity_scd_type": "type_1",
    "dimensional_entity_scd_type": "type_2",
    "operational_naming_instructions": "Entity names are singular, in PascalCase.",
    "dimensional_naming_instructions": null,
    "operational_audit_columns": [
      { "name": "SourceSystemID", "data_type": "int", "nullable": false, "definition": "The system the row came from." }
    ],
    "dimensional_audit_columns": null,
    "is_sample_storage_allowed": false,
    "sample_size": 5,
    "subject_area_target_column_count": 800
  },
  "row_counts": {
    "project_input_scope": 22,
    "subject_area": 4,
    "operational_entity": 14,
    "operational_object_mapping": 9
  }
}
```

- `project_config` has the columns of `project.project_config` with their stored shapes.
- Worked out: `row_counts`, the number of active rows in each part of the project (four of them shown).
- Left out: the three default AI settings (model, reasoning effort, max turns). Only Runs in the web app use them.

### `check_tenant_lock`

**Used for:** seeing whether you can change things now, and if not, who to ask and how long to wait.

```json
Input
{ "tenant_code": "ACME" }

Output when someone holds it
{
  "tenant_code": "ACME",
  "is_locked": true,
  "locked_by_display_name": "Ben",
  "is_yours": true,
  "tenant_lock_purpose": "Sales scope",
  "tenant_lock_acquired_time": "2026-11-21T14:30:00Z",
  "tenant_lock_expires_time": "2026-11-21T15:30:00Z"
}

Output when it is free
{ "tenant_code": "ACME", "is_locked": false }
```

Worked out: `is_locked` (a lock whose time has run out counts as free), `is_yours`, the holder's display name.

### `acquire_tenant_lock`

**Used for:** holding the tenant while you push, validate and apply.

```json
Input
{ "tenant_code": "ACME", "minutes": 60, "tenant_lock_purpose": "Sales scope" }

Output
the same fields as check_tenant_lock when someone holds it
```

`minutes` is optional, 1 to 240, 60 if left out. `tenant_lock_purpose` is optional. If someone else holds the lock it is
refused with ACCESS-003 and their name. It never takes the lock from them.

### `release_tenant_lock`

**Used for:** freeing the tenant when you are done.

```json
Input
{ "tenant_code": "ACME" }

Output
{ "tenant_code": "ACME", "released": true }

Output when you held no lock
{ "tenant_code": "ACME", "released": false }
```

### `override_tenant_lock`

**Used for:** ending a lock someone left behind, after the person has agreed to it in chat.

```json
Input
{ "tenant_code": "ACME" }

Output
{
  "tenant_code": "ACME",
  "overridden": true,
  "was_locked_by_display_name": "Asha",
  "tenant_lock_purpose": "Catalog update",
  "tenant_lock_expires_time": "2026-11-21T16:00:00Z"
}

Output when nobody held it
{ "tenant_code": "ACME", "overridden": false }
```
