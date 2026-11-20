# Rules: Scope

Scope is the list of tables a project works on. "In scope" means the project has a scope row for the table and
that row is switched on (`is_active` true). Switching a row off takes the table out of scope but keeps its
profile and enrichment, so nothing is lost if it comes back. How rules are written: [rules.md](../rules.md).

## Checked in core/

### SCOPE-001 · Only Source and Bronze tables can be in scope
*Blocks Apply · Approved*

**What it means.** A table can be added to a project's scope only if its zone is Source or Bronze.

**Why.** The project builds its Silver and Gold models from the scope tables. A Silver or Gold table in scope
would feed the model its own output. v2 had the same limit.

**What happens.** A draft that adds a Silver or Gold table cannot be applied until that table is taken out of it.

**Example.** Retail can scope `bronze.orders` (zone Bronze) and `sap.VBAK` (zone Source). A draft that adds
`silver.Customer` is stopped.

### SCOPE-002 · A scope table belongs to the project's tenant or to a global tenant
*Blocks Apply · Proposed (to discuss)*

**What it means.** A project can scope tables of its own tenant and of any global tenant, but not tables of
another private tenant, even if the person adding them can read that tenant.

**Why.** Profiling and Runs show a scope table's columns and sample values to everyone working on the project.
A table of another private tenant would show its data to people who have no access to that tenant. v2 allowed
any tenant's table here.

**What happens.** The draft cannot be applied until the table is taken out. To share tables across tenants, put
them in a global tenant.

**Example.** Retail (tenant Contoso) can scope a Contoso table, or a table of the global tenant Shared. A draft
that adds a table of Fabrikam, which is private, is stopped.

**Taking a table out of scope.** There is no separate rule for this. If a subject area or an entity source still
uses the table, that row's own rule stops the Apply (SUBJECT-AREA-001, OPERATIONAL-001), because Apply checks
the project as it will be afterwards. Take the table out of the subject area first, then out of scope.

## Checked by the database

Obvious checks (required fields, keys) are not listed.

### SCOPE-003 · A table is in a project's scope at most once
*Database (`uq_project_input_scope_project_object`) · In the schema*

A project has one scope row per table. Taking a table out and putting it back switches the same row off and on.

### SCOPE-004 · A scope row that has work on it cannot be deleted
*Database (the `fk_*_scope` keys in `06_workflow_analysis.sql`) · In the schema*

Profiles, enrichment and relationships point at the scope row. While any of them exist, the database will not
let the scope row be deleted; switch it off instead. This keeps that work, and stops it from pointing at nothing.
