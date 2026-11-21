# Rules: Catalog

The catalog is all registered metadata: systems, connections, tables and columns. Every table belongs to one tenant,
its **source tenant** (`core.object.source_tenant_id`), whose data it is. A **data lake tenant** (`is_data_lake`) is a
tenant whose connections are all lake instances, such as GDS US or GDS Canada. Each tenant's Bronze, Silver and Gold
tables sit on its **data lake connection** (`core.tenant.data_lake_connection_id`), but still belong to that tenant.
How rules are written: [rules.md](../rules.md).

## Checked in core/

### CATALOG-001 · A tenant's data lake connection belongs to a data lake tenant
*Blocks Apply · Approved (Maaz, Nov 21; built with metadata push, step 4)*

**What it means.** When a tenant's `data_lake_connection_id` is set, it must point to a connection whose tenant has
`is_data_lake` switched on. It can be left empty, for example on a data lake tenant itself.

**Why.** The data lake connection says where a tenant's Bronze, Silver and Gold tables land. Pointing it at an
ordinary source connection, such as ERP's own database, would put lake tables in the wrong place.

**What happens.** The change is not applied until the tenant points to a connection of a data lake tenant.

**Example.** GDS is a data lake tenant with connections GDS US and GDS Canada. ERP can point to GDS US. ERP cannot
point to its own connection `erp_prod`, because ERP is not a data lake tenant.

### CATALOG-002 · A Source table's source tenant is its connection's tenant
*Blocks Apply · Approved (Maaz, Nov 21; built with metadata push, step 4)*

**What it means.** For a table in the Source zone, its source tenant must be the tenant that owns its connection.
Bronze, Silver and Gold tables sit on a data lake connection and keep their own source tenant, so this rule does not
apply to them.

**Why.** A Source table is read straight from its own system, so its owner and its connection's owner are the same.
If they differed, the table would show up under one tenant while its data came from another.

**What happens.** The change is not applied until the source tenant and the connection's tenant match.

**Example.** ERP's table `VBAK` on ERP's connection `erp_prod` has source tenant ERP: fine. The same table registered
with source tenant Contoso is stopped.

## Checked by the database

None yet. Both rules above compare two tables, which `core/` checks; Postgres only holds keys and simple checks.
