# Rules: Operational model

The operational model (the Silver model): entities, their attributes, the Source and Bronze tables and columns they come
from, and links between entities. Only the entity row has the project; the rest point at their parent by id.
How rules are written: [rules.md](../rules.md).

## Checked in core/

### OPERATIONAL-001 · An entity's source table must be in the project's scope
*Blocks Apply · Approved*

**What it means.** Every table an entity is built from (Source or Bronze zone) must be in the project's scope.

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

### OPERATIONAL-003 · A link stays inside the project
*Blocks Apply · Approved*

**What it means.** A link's parent entity must be in the same project as the child attribute's entity.

**Why.** A link stores only the child attribute and the parent entity, so the database cannot check this.

**What happens.** The draft cannot be applied.

**Example.** UserDevice.UserID links to User, both in project Sales: fine. A link to an entity of another
project is stopped.


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

