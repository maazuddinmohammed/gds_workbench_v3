# Terminology

Use these words, with these meanings, in code, docs and conversation.
If a new term comes up, add it here.

## The product and its pieces

| Term | Meaning |
|---|---|
| GDS Workbench (v3) | This product. The tool for scoping tables, building models, mapping and code. |
| v2 | The old project (`gds_workbench`). Reference only, never changed. v2 called the product "Atlas". |
| core | The Python folder `core/` with all the logic. Everything else calls it. |
| Web app | Browser pages plus the FastAPI backend. Runs as a Databricks App. |
| MCP server | Server that gives AI tools (Copilot and others) their tools. Runs on Azure App Service. Also serves the Bridge. |
| Plugin | Skills (text instructions for the AI) plus the MCP address. Installed in VS Code. |
| Skill | One instruction file in the plugin for one step, for example "Silver model". |
| Bridge | VS Code extension that moves project files between laptop and server: **pull**, **check**, **push**. |
| Local Workbench | Review screen for local project files, inside VS Code. |
| Local files | The project, pulled to the laptop as JSON files, one per table, entity or mapping. |
| Step runner | The part of the web app that does a Run: prepares the context, calls the AI (one shot or tool based), checks, makes a draft. |
| Prompt builder | The one place in `core/` that puts a prompt together, including which Notes go into it. |
| Foundry | Azure AI Foundry, where the web app's AI models come from. |

## People and access

| Term | Meaning |
|---|---|
| Lane | A group of tenants. |
| Tenant | Owns metadata and projects. Access is given per tenant. |
| User | One person, from Microsoft (Entra) sign-in (table `security.principal`). |
| Role | Per tenant: **Viewer**, **Developer**, **Tenant Admin**. Each includes the one before. (v2 also had Architect; dropped Nov 20.) |
| Permission | What a role may do: `READ`, `CHANGE`, `MANAGE_TENANT`. Table in `design/shared/access.md`. |
| Super Admin | A user with access to all tenants. Still follows locks. |
| Tenant member | A user's role in one tenant (table `security.tenant_principal_access`). |
| `core` schema | Postgres schema for lanes, tenants, catalog and pipelines (same name as v2). Not the `core/` Python folder. |
| Global tenant | A tenant every signed-in user can read, without being a member. |
| MCP access | A switch on a user's tenant membership that allows using the MCP server and the Bridge. Every role needs it; Super Admins always have it. |
| Tenant lock | A timed lock one user holds on a tenant, for 1 minute to 4 hours as they choose. Needed to change drafts and Apply. Others see who holds it. |
| Release the lock | End a tenant lock now. Anyone who may change the tenant can release anyone's lock, after confirming. |
| Project lock | Makes a whole project read-only. Set by a Tenant Admin. |
| Catalog lock | Makes a tenant's catalog read-only (`core.tenant.is_metadata_locked`). Set by a Tenant Admin. |
| Personal key | A key a user makes in the web app so an AI tool without Microsoft sign-in can use MCP. |

## Catalog (metadata)

| Term | Meaning |
|---|---|
| Catalog | All registered metadata: systems, connections, tables, columns, lineage, pipelines. |
| System | Where data comes from, for example SAP or Workday. |
| Connection | How to reach one Databricks workspace and catalog. Stores the secret's name, never the secret. |
| Zone | **Source** (original system), **Bronze** (ingested), **Silver** (modeled), **Gold** (dimensional). |
| Table / Column | A registered physical table and its columns (tables `core.object` / `core.attribute`, as in v2). |
| Source tenant | The tenant a table belongs to: whose data it is (`core.object.source_tenant_id`). Decides who sees it, scope and locks. A Bronze copy of ERP's table is ERP's even though it sits in the lake. |
| Data lake tenant | A tenant with `is_data_lake`. All its connections are lake instances, such as GDS US or GDS Canada. |
| Data lake connection | The lake instance a tenant's Bronze, Silver and Gold tables land in (`core.tenant.data_lake_connection_id`). |
| Ingestion lineage | Which Bronze table and column came from which Source table and column. |
| Pipeline tables | Ingestion and processing setup: copy groups, members, processes, notebooks and their reference lists. |

## Projects and workflow steps

| Term | Meaning |
|---|---|
| Project | One modeling effort inside a tenant. |
| Scope | The tables a project works on (v2: Project Input Scope). |
| Step | One part of the workflow: profiling, enrichment, relationships, subject areas, Silver model, Gold model, Silver mapping, Gold mapping, code. |
| Run | Pressing Run on a step. It ends in a draft. Two kinds in the web app: **one shot** and **tool based**. Only one Run at a time per tenant. |
| Run log | The stages of a Run, shown while it runs (`application.run_event`). |
| Provider | How the app calls a group of AI models: one piece of calling code in `core/`, for example `foundry_openai`. Replaces v2's SDK. |
| Model | One AI model of a provider: the name its API expects, a display name,  the reasoning efforts it allows and its prices per million tokens. |
| AI usage | Tokens and cost of each AI call in a Run (`application.run_model_request`). |
| One shot Run | A Run with one AI call. Everything the AI needs is in the prompt. |
| Tool based Run | A Run where the AI works with tools. The tools only look things up in the ledger. |
| Ledger | The indexed, fixed-format copy of the information that Python builds before a tool based Run. |
| Sample values | A few real values per column (default 5), shown to the AI. Stored only if the project allows it. |
| Project settings | Per project, in `project.project_config`: schemas, SCD type per model, naming instructions and audit columns per model, sample settings (may samples be stored, sample size), and default AI settings. |
| Project schema | A database schema a project's operational or dimensional entities live in. A project can have several (lists on `project.project_config`). |
| Profiling | Measuring columns with queries (counts, nulls, distinct values). No AI. |
| Enrichment | AI-written descriptions, keys and PII flags for tables and columns, owned by the project. |
| Relationship | A link between two source columns, found by the relationships step (v2: Analysis Result). |
| Subject area | A business group of tables, like Sales. Decides which tables a Silver or Gold Run works on. A table can be in more than one. |
| Related table | A table outside the subject area that one of the area's tables points at. Given to the Run, marked as related. |
| Note | A requirement, rule or decision written for a project (v2: Context Record; table `context_record`). Each has a Note number (`#3`), unique in its Note group. |
| Note group | A named set of Notes with one type, for one system or the whole project (table `context_group`). |
| Note type | What a Note is for, like Silver model requirements or Agent. Decides which steps read it (table `context_type`, from the seed). |
| House standards | How this project writes things: trim text, how a lookup is joined, the batch filter. Kept as starter Notes. Naming and audit columns are project settings. |

## Models, mapping and code

| Term | Meaning |
|---|---|
| Operational model | Normalized model built from the Source and Bronze tables in scope, loaded into the Silver zone. Tables `operational_*`. Also called the Silver model. |
| Dimensional model | Facts and dimensions built from the operational model, loaded into the Gold zone. Tables `dimensional_*`. Also called the Gold model. |
| Entity | A modeled table in the Silver or Gold model. |
| Attribute | A column of an entity. |
| Link | A child entity's foreign-key attribute pointing at a parent entity (v2: relationship between entities). |
| Definition | A normal data dictionary description of a table, column, entity or attribute. Separate from Grain. |
| Grain | What one row means. Its own field on enriched source tables and on entities. |
| Key | The column that identifies a row. Python adds generated keys. |
| Natural key | The source's own identifier for a row, for example UserNumber. Every entity marks it. Lookups match on it and the orchestrator merges on it. |
| Entity source | A Source or Bronze table in scope (operational) or operational entity (dimensional) that feeds an entity (table `operational_entity_source` / `dimensional_entity_source`; v2: entity source mapping). |
| Attribute source | A column of one of those tables (operational) or operational attribute (dimensional) that feeds an attribute (table `operational_attribute_source` / `dimensional_attribute_source`). |
| Silver key | The key Python generates for an operational entity, marked `is_surrogate_key`. Dimensional entities have one the same way. |
| Note for mapping | A short instruction on an entity source or attribute source, saying how to map it (v2: rationale). |
| Audit columns | Standard columns Python adds to every entity (SourceSystemID, CreatedDate and so on). |
| Mapping | Where each attribute of one target entity comes from, for one source system. Two parts: an entity part (tables, rows to keep, sample query, transformation) and one free-text line per attribute. **Silver mapping** reads Bronze; **Gold mapping** reads Silver. They are stored apart. |
| Source system | The system a mapping reads from. One mapping per target entity and source system. |
| Row key | What names a row of the Workbench's own tables in a change set, for example an entity by project, schema and name. Change sets use it instead of ids. Not the same as a natural key. List in `docs/rules/row-keys.md`. |
| Lookup | Finding a parent's key by its natural key, for example CustomerID from CustomerNumber. The facts about the parent come from the model, never from the parent's mapping. |
| Code | SQL that the AI writes from an applied mapping. Python may prepare a starter SQL. It only gives the final data frame; the orchestrator loads it. |
| Orchestrator | The pipeline framework outside the Workbench. It runs the code by tenant and system, replaces the batch ID, and decides how to load the result. |
| Load order | The order entities must load in, parents before children. Python works it out from the links and stores it (`*_entity_dependency_order`). |

## Changes and rules

| Term | Meaning |
|---|---|
| Validation group | A set of checks (queries and the result each must give) that test one system's loaded operational or dimensional tables. |
| Change set | A group of changes that are reviewed together and saved together. Two kinds: **metadata** (catalog) and **project**. |
| Draft | A change set that is not saved yet. Runs, pushes and hand edits all make drafts. |
| Section | One part of a change set: the JSON list of records for one table (for example `operational_object_mapping`). |
| Stage chunk | One piece of a large push from VS Code, joined into its section before review. |
| Apply | Saving a whole draft to Postgres in one go, or nothing if something fails. A person applies, or tells the AI in chat to apply after reviewing the draft. |
| Reject | Throwing a draft away. |
| Project version | A number that goes up on every Apply (`project.project_version`; v2: project revision). Apply refuses a draft built on an older version. |
| Metadata version | The same for a tenant's catalog: goes up on every metadata Apply (`core.tenant.tenant_metadata_version`). |
| Rule | One check, written in its group file under `docs/rules/` with an ID like `SILVER-001`. |
| Level | **Blocks Apply** (must be fixed), **Warning** (shown, Apply still allowed), **Refuses the request** (the action is not done) or **Database** (Postgres refuses the row). |
| Status | **Proposed** (waiting for Maaz) or **Approved** (may be built). |
| Problem | A rule that failed on a draft. Always shown with its rule ID. |

## Prompts

| Term | Meaning |
|---|---|
| Prompt | Instructions for one step, for example "Silver model – standard". One per step is the default. |
| Prompt version | One saved text of a prompt. Every save makes a new version. |
| Global prompt | A prompt for every tenant. Starter prompts are global. |
| Tenant prompt | A prompt that belongs to one tenant. The tenant's default comes before the global default. |
| Extra instructions | Text added for one Run only, without changing the prompt. |

## Deployment

| Term | Meaning |
|---|---|
| Databricks App | Where the web app runs. |
| App Service | Azure App Service, where the MCP server runs. |
| Key Vault | Azure Key Vault, where secrets live. |
| Build | Running `scripts/build.py` to make the files in `dist/`. Done by hand, no GitHub Actions. |
| `dist/` | Build output: `web.zip`, `mcp.zip`, `plugin.zip`, `bridge.vsix`. Not saved in git. |
| Deploy | Maaz uploading a zip by hand: `web.zip` to the Databricks App, `mcp.zip` to App Service. |
| `version.txt` | Git commit and build time inside each zip, shown on `/health`. |
| Local database | A throwaway Postgres on the laptop or in Claude's cloud session, for development and tests only. |
| Seed data | Data every install needs: reference lists and starter prompts (`database/seed/`). |
| Demo data | Made-up tenants, users, catalog (three systems) and project for local testing only, all in `database/demo/`. Never goes to Azure. |
| Local sign-in | When running locally, you pick a demo user instead of signing in with Microsoft or Databricks. |

## Old v2 words and their v3 words

| v2 | v3 |
|---|---|
| Atlas, Atlas Platform, Atlas MCP | GDS Workbench, web app, MCP server |
| Object / Attribute (physical) | Table / Column (table names stay `object` / `attribute`) |
| Context Record, Context Group | Note |
| Analysis Result | Relationship |
| Project Input Scope | Scope |
| Snapshot | Pull |
| Stage | Push |
| Workflow Run | Run |
| Output Template | (gone: mapping has one fixed shape) |
| Prompt Studio, Prompt Template, Prompt Assignment | Prompts page, Prompt, default prompt |
