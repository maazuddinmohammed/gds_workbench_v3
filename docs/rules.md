# Rules and checks

Every check the system enforces is listed here, in plain English. This file is the one place to review them.

## How this works

- Each rule has an **ID** (like `SILVER-001`), a **level** and a **status**.
- **Level**: `Blocks Apply` (must be fixed before Apply) or `Warning` (shown, but Apply is allowed).
- **Status**: `Proposed` (written down, waiting for Maaz) or `Approved` (Maaz said yes, may be built).
- Only `Approved` rules get built. A new rule is added here as `Proposed` first, in its own small change.
- In code, each rule is one small Python function in `core/` named after its ID, with a test for the
  pass and fail examples below. A test checks that code and this file agree, so no rule can be added
  quietly.
- Every problem shown in the web app, Local Workbench or to the AI starts with the rule ID.
- Rules that the database itself enforces (not null, unique) are listed too, marked `Database`.

## Rule format

```
### SILVER-001 · Every Silver entity has exactly one key column
- Step: Silver model
- Level: Blocks Apply
- Why: loads and lookups need one stable key
- Passes: Customer has CustomerID marked as key
- Fails: Customer has no key column, or two
- Status: Proposed
```

The rule above is only an example of the format. It is not approved.

## Access

(none yet)

## Scope

(none yet)

## Change sets

(none yet)

## Profiling

(none yet)

## Enrichment

(none yet)

## Relationships

(none yet)

## Subject areas

### SUBJECT-AREA-001 · A subject area table is in the project's scope
- Step: Subject areas
- Level: Blocks Apply
- Why: a subject area table stores only the area and the table, so the database cannot check this
- Passes: area Sales in project Retail has bronze.orders, and bronze.orders is in Retail's scope
- Fails: area Sales has bronze.payroll, which is not in Retail's scope, or was removed from it
- Status: Proposed

## Operational model

### OPERATIONAL-001 · An entity source table is in the project's scope
- Step: Operational model
- Level: Blocks Apply
- Why: the database no longer checks this (entity sources have no project_id)
- Passes: entity User has source table bronze.users, and bronze.users is in the project's scope
- Fails: entity User has source table bronze.orders, which is not in the scope, or was removed from it
- Status: Approved

### OPERATIONAL-002 · An attribute source column comes from one of the entity's source tables
- Step: Operational model
- Level: Blocks Apply
- Why: an attribute source stores only the two attributes, so the database cannot check this
- Passes: User.UserNumber has source column bronze.users.user_number, and bronze.users is a source of User
- Fails: User.UserNumber has source column bronze.orders.user_number, and bronze.orders is not a source of User
- Status: Approved

### OPERATIONAL-003 · A link's parent entity is in the same project as the child
- Step: Operational model
- Level: Blocks Apply
- Why: a link stores only the child attribute and the parent entity
- Passes: UserDevice.UserID links to User, both in project Sales
- Fails: UserDevice.UserID links to an entity from another project
- Status: Approved

## Dimensional model

### DIMENSIONAL-001 · An entity source is an operational entity of the same project
- Step: Dimensional model
- Level: Blocks Apply
- Why: the database no longer checks this (entity sources have no project_id)
- Passes: DimUser has source User, both in project Sales
- Fails: DimUser has source User from another project
- Status: Approved

### DIMENSIONAL-002 · An attribute source comes from one of the entity's source entities
- Step: Dimensional model
- Level: Blocks Apply
- Why: an attribute source stores only the two attributes, so the database cannot check this
- Passes: DimUser.UserNumber has source User.UserNumber, and User is a source of DimUser
- Fails: DimUser.UserNumber has source Device.UserNumber, and Device is not a source of DimUser
- Status: Approved

### DIMENSIONAL-003 · A link's parent entity is in the same project as the child
- Step: Dimensional model
- Level: Blocks Apply
- Why: a link stores only the child attribute and the parent entity
- Passes: FactLogin.UserKey links to DimUser, both in project Sales
- Fails: FactLogin.UserKey links to an entity from another project
- Status: Approved

## Silver mapping

### MAPPING-001 · An attribute mapping line is for an attribute of the mapping's own entity
- Step: Operational and dimensional mapping
- Level: Blocks Apply
- Why: a mapping line stores only the mapping and the attribute
- Passes: the mapping for User (system CRM) has a line for User.UserNumber
- Fails: the mapping for User has a line for Device.DeviceID
- Status: Proposed

## Gold mapping

(none yet)

## Code generation

### CODE-001 · A source system is in at most one code file of an entity
- Step: Code generation
- Level: Blocks Apply
- Why: a code file lists its systems; two files for the same entity and system would load it twice
- Passes: User has user_crm.sql for CRM and user_erp.sql for ERP
- Fails: User has user_all.sql and user_crm.sql, both listing CRM
- Status: Proposed
