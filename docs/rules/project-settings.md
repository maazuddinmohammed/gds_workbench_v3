# Rules: Project settings

The settings of one project (`project.project_config`): its schemas, SCD types, naming instructions, audit columns,
sample settings and default AI settings. How rules are written: [rules.md](../rules.md).

## Checked in core/

### PROJECT-001 · Scope, Silver and Gold schemas never share a name
*Blocks Apply · Approved*

**What it means.** A project's Silver schemas, its Gold schemas and the schemas of its scope tables are three sets
of names with nothing in common. Names compare ignoring upper and lower case.

**Why.** Prompts, mappings, code and checks name tables and entities by schema and name. A Silver schema named like a
source schema would make `sap.Customer` mean two things.

**What happens.** The draft cannot be applied, and the problem names the schema.

**Example.** Silver schema `silver_sales` and scope tables in `sap`: fine. A Silver schema named `sap`: stopped.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.
