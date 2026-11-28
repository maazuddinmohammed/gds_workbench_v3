# Rules: Dimensional model

The dimensional model (the Gold model): facts and dimensions built from operational entities. Same shape as the
operational model; only the entity row has the project. How rules are written: [rules.md](../rules.md).

## Checked in core/

### DIMENSIONAL-001 · An entity's source is an operational entity of the same project
*Blocks Apply · Approved*

**What it means.** A Gold entity is built only from Silver entities of its own project.

**Why.** An entity source row has no project, so the database cannot check this. Gold reads Silver only, and
only its own project's.

**What happens.** The draft cannot be applied.

**Example.** DimUser from User, both in project Sales: fine. DimUser from a User of another project: stopped.

### DIMENSIONAL-002 · An attribute's source comes from one of its entity's source entities
*Blocks Apply · Approved*

**What it means.** If DimUser.UserNumber is fed by an operational attribute, that attribute's entity must be one
of DimUser's source entities.

**Why.** An attribute source stores only the two ids, so the database cannot check this.

**What happens.** The draft cannot be applied. Add the entity as a source, or pick another attribute.

**Example.** DimUser.UserNumber from User.UserNumber, with User a source of DimUser: fine. From
Device.UserNumber, when Device is not a source of DimUser: stopped.

### DIMENSIONAL-003 · A link's parent is an active entity of the same project
*Blocks Apply · Approved (wording Nov 28, Maaz: the parent must be active)*

**What it means.** A link's parent entity must be switched on, and in the same project as the child attribute's
entity.

**Why.** A link stores only the child attribute and the parent entity, so the database cannot check this.

**What happens.** The draft cannot be applied.

**Example.** FactLogin.UserKey links to DimUser, both in project Sales: fine. A link to an entity of another
project, or to a DimUser that was switched off, is stopped.

### DIMENSIONAL-004 · An entity's schema is one of the project's Gold schemas
*Blocks Apply · Proposed*

**What it means.** Every dimensional entity's schema is one of the schemas in `project_config.dimensional_schemas`.
OPERATIONAL-004 says the same for Silver.

**Why.** The schema names where the entity is loaded. An unlisted schema would not exist in the lake.

**What happens.** The draft cannot be applied, and the problem names the entity and the schema.

**Example.** `gold_sales.DimCustomer` when `gold_sales` is listed: fine. When it is not: stopped.

### DIMENSIONAL-005 · An entity has exactly one surrogate key, with no source and no link
*Blocks Apply · Proposed*

**What it means.** As OPERATIONAL-005, for Gold: one active attribute marked `is_surrogate_key`, with no sources and
no link, such as `CustomerKey`.

**Why.** Every fact's link takes the dimension's surrogate key.

**What happens.** The draft cannot be applied, and the problem names the entity.

**Example.** DimCustomer with `CustomerKey`: fine. DimCustomer with no surrogate key: stopped.

### DIMENSIONAL-006 · An entity has a natural key
*Blocks Apply · Proposed*

**What it means.** As OPERATIONAL-006, for Gold: at least one active attribute marked `is_natural_key`.

**Why.** A fact finds its dimension row by the dimension's natural key, and the orchestrator merges on it.

**What happens.** The draft cannot be applied, and the problem names the entity.

**Example.** DimCustomer with `CustomerNumber` as its natural key: fine. With none: stopped.

### DIMENSIONAL-007 · No attribute has an audit column's name
*Blocks Apply · Proposed*

**What it means.** As OPERATIONAL-007, with the project's dimensional audit columns, including the history columns
with type 2.

**Why.** The load adds the audit columns. An attribute with the same name would clash with them.

**What happens.** The draft cannot be applied, and the problem names the attribute.

**Example.** An attribute `IsCurrentRecord` when it is a history column: stopped.

### DIMENSIONAL-008 · A Gold source points at active Silver rows
*Warning · Proposed*

**What it means.** A dimensional entity's source entities, and an attribute's source attributes, are switched on.

**Why.** A Silver row that was switched off is no longer loaded, so the Gold entity would read nothing from it.

**What happens.** The draft can be applied. The warning names the source.

**Example.** DimCustomer from Silver Customer: fine. From a Silver entity that was switched off: a warning.

### DIMENSIONAL-009 · An attribute's type is a valid Databricks type
*Warning · Proposed*

**What it means.** As OPERATIONAL-008, for Gold attributes.

**Why.** The code creates columns with this type. A broken type fails only when the load runs.

**What happens.** The draft can be applied. The warning names the attribute and its type.

**Example.** `DECIMAL(16,2)`: fine. `DECIMAL(16,2`: a warning.

### DIMENSIONAL-010 · A dimension loads before the facts that point at it
*Warning · Proposed*

**What it means.** As OPERATIONAL-009, for Gold: when both have a load order, an entity loads after every entity its
links point at.

**Why.** A fact finds its dimension's key only if the dimension has loaded first.

**What happens.** The draft can be applied. The warning names both entities.

**Example.** DimCustomer loads before FactSales: fine. FactSales before DimCustomer: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

