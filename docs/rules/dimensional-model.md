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

### DIMENSIONAL-003 · A link stays inside the project
*Blocks Apply · Approved*

**What it means.** A link's parent entity must be in the same project as the child attribute's entity.

**Why.** A link stores only the child attribute and the parent entity, so the database cannot check this.

**What happens.** The draft cannot be applied.

**Example.** FactLogin.UserKey links to DimUser, both in project Sales: fine. A link to an entity of another
project is stopped.


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

