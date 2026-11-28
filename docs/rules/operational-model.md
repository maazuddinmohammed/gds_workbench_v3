# Rules: Operational model

The operational model (the Silver model): entities, their attributes, the Source and Bronze tables and columns they come
from, and links between entities. Only the entity row has the project; the rest point at their parent by id.
How rules are written: [rules.md](../rules.md).

## Checked in core/

### OPERATIONAL-001 · An entity's source table must be in the project's scope
*Blocks Apply · Approved (wording Nov 28, Maaz: only active rows count)*

**What it means.** Every table an active entity is built from (Source or Bronze zone) must be in the project's
scope. Only active rows count: a switched-off entity or entity source never stops a table from leaving scope.

**Why.** An entity source row has no project, so the database cannot check this. Without it an entity could be
built from a table the project does not work on, which has no profile or enrichment.

**What happens.** The draft cannot be applied. Like SUBJECT-AREA-001, it also stops a used table from being taken
out of scope.

**Example.** Entity User has source table `bronze.users`, which is in scope: fine. Source table `bronze.orders`,
not in scope (or just taken out), is stopped.

### OPERATIONAL-002 · An attribute's source column comes from one of its entity's source tables
*Blocks Apply · Approved*

**What it means.** If attribute User.UserNumber is fed by a column, that column's table must be one of
User's source tables.

**Why.** An attribute source stores only the two ids, so the database cannot check this. Otherwise the mapping
and code would read a table the entity does not list.

**What happens.** The draft cannot be applied. Add the table as a source of the entity, or pick another column.

**Example.** User.UserNumber from `bronze.users.user_number`, with `bronze.users` a source of User: fine. From
`bronze.orders.user_number`, when `bronze.orders` is not a source of User: stopped.

### OPERATIONAL-003 · A link's parent is an active entity of the same project
*Blocks Apply · Approved (wording Nov 28, Maaz: the parent must be active)*

**What it means.** A link's parent entity must be switched on, and in the same project as the child attribute's
entity.

**Why.** A link stores only the child attribute and the parent entity, so the database cannot check this.

**What happens.** The draft cannot be applied.

**Example.** UserDevice.UserID links to User, both in project Sales: fine. A link to an entity of another
project, or to a User that was switched off, is stopped.

### OPERATIONAL-004 · An entity's schema is one of the project's Silver schemas
*Blocks Apply · Proposed*

**What it means.** Every operational entity's schema is one of the schemas in `project_config.operational_schemas`.

**Why.** The schema names where the entity is loaded. An unlisted schema would not exist in the lake.

**What happens.** The draft cannot be applied, and the problem names the entity and the schema.

**Example.** Entity `silver_sales.Contact` when `silver_sales` is listed: fine. `silver_crm.Contact` when it is not:
stopped.

### OPERATIONAL-005 · An entity has exactly one surrogate key, with no source and no link
*Blocks Apply · Proposed*

**What it means.** Each active entity has exactly one active attribute marked `is_surrogate_key`. That attribute has
no source columns and no link, because the load fills it as an identity column.

**Why.** Every lookup takes the parent's surrogate key, so an entity with none, or two, cannot be linked to. A
source on it would be ignored by the load.

**What happens.** The draft cannot be applied, and the problem names the entity.

**Example.** Contact with `ContactID` as its one surrogate key: fine. Contact with `ContactID` and `ContactKey` both
marked: stopped.

### OPERATIONAL-006 · An entity has a natural key
*Blocks Apply · Proposed*

**What it means.** Each active entity has at least one active attribute marked `is_natural_key`. Several attributes
can form one key.

**Why.** Lookups to the entity match on its natural key, and the orchestrator merges on it.

**What happens.** The draft cannot be applied, and the problem names the entity.

**Example.** Contact with `SourceContactID` as its natural key: fine. Contact with no natural key: stopped.

### OPERATIONAL-007 · No attribute has an audit column's name
*Blocks Apply · Proposed*

**What it means.** No attribute is named like one of the project's operational audit columns, ignoring upper and
lower case.

**Why.** The load adds the audit columns to every entity. An attribute with the same name would clash with them.

**What happens.** The draft cannot be applied, and the problem names the attribute.

**Example.** An attribute `CreatedAt` when the audit columns are `SourceSystemID` and `CreatedDate`: fine. An
attribute `createddate`: stopped.

### OPERATIONAL-008 · An attribute's type is a valid Databricks type
*Warning · Proposed*

**What it means.** An attribute's data type reads as a Databricks type, such as `STRING`, `INT`, `DECIMAL(16,2)`,
`DATE` or `TIMESTAMP`.

**Why.** The code casts and creates columns with this type. A broken type fails only when the load runs.

**What happens.** The draft can be applied. The warning names the attribute and its type.

**Example.** `DECIMAL(16,2)`: fine. `DECIMAL(16,2`: a warning.

### OPERATIONAL-009 · A parent entity loads before its children
*Warning · Proposed*

**What it means.** When both have a load order, an entity's load order comes after the load order of every entity
its links point at. A link from an entity to itself is ignored.

**Why.** A child's lookup finds its parent's key only if the parent has loaded first. The order is worked out by a
separate step, and a person can edit it.

**What happens.** The draft can be applied. The warning names the parent and the child.

**Example.** Customer loads 1 and Contact 2: fine. Contact loads before Customer: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

