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
| Role | Per tenant: **Viewer**, **Developer**, **Architect**, **Tenant Admin**. Each includes the one before. |
| Super Admin | A user with access to all tenants. Still follows locks. |
| Tenant member | A user's role in one tenant (table `security.tenant_principal_access`). |
| `core` schema | Postgres schema for lanes, tenants, catalog and pipelines (same name as v2). Not the `core/` Python folder. |
| Global tenant | A tenant every signed-in user can read, without being a member. |
| MCP access | A switch on a user's tenant membership that allows using the MCP server. |
| Tenant lock | A timed lock one user holds on a tenant. Needed to change drafts and Apply. Others see who holds it. |
| Project lock | Makes a whole project read-only. |
| Personal key | A key a user makes in the web app so an AI tool without Microsoft sign-in can use MCP. |

## Catalog (metadata)

| Term | Meaning |
|---|---|
| Catalog | All registered metadata: systems, connections, tables, columns, lineage, pipelines. |
| System | Where data comes from, for example SAP or Workday. |
| Connection | How to reach one Databricks workspace and catalog. Stores the secret's name, never the secret. |
| Zone | **Source** (original system), **Bronze** (ingested), **Silver** (modeled), **Gold** (dimensional). |
| Table / Column | A registered physical table and its columns (tables `core.object` / `core.attribute`, as in v2). |
| Ingestion lineage | Which Bronze table and column came from which Source table and column. |
| Pipeline tables | Ingestion and processing setup: copy groups, members, processes, notebooks and their reference lists. |

## Projects and workflow steps

| Term | Meaning |
|---|---|
| Project | One modeling effort inside a tenant. |
| Scope | The tables a project works on (v2: Project Input Scope). |
| Step | One part of the workflow: profiling, enrichment, relationships, subject areas, Silver model, Gold model, Silver mapping, Gold mapping, code. |
| Run | Pressing Run on a step. It ends in a draft. Two kinds in the web app: **one shot** and **tool based**. |
| One shot Run | A Run with one AI call. Everything the AI needs is in the prompt. |
| Tool based Run | A Run where the AI works with tools. The tools only look things up in the ledger. |
| Ledger | The indexed, fixed-format copy of the information that Python builds before a tool based Run. |
| Sample values | A few real values per column (default 5), shown to the AI. Stored only if the project allows it. |
| Profiling | Measuring columns with queries (counts, nulls, distinct values). No AI. |
| Enrichment | AI-written descriptions, keys and PII flags for tables and columns, owned by the project. |
| Relationship | A link between two source columns, found by the relationships step (v2: Analysis Result). |
| Subject area | A business group of tables, like Sales. Decides which tables a Silver or Gold Run works on. A table can be in more than one. |
| Related table | A table outside the subject area that one of the area's tables points at. Given to the Run, marked as related. |
| Note | A requirement, rule or decision written for a project (v2: Context Record; table `context_record`). |
| Note group | A named set of Notes with one type, for one system or the whole project (table `context_group`). |
| Note type | What a Note is for, like Silver model requirements or Agent. Decides which steps read it (table `context_type`, from the seed). |
| House standards | How this project writes things: trim text, how a lookup is joined, the batch filter, naming. Kept as starter Notes. |

## Models, mapping and code

| Term | Meaning |
|---|---|
| Silver model | Normalized model built from Bronze tables (v2: Operational model). |
| Gold model | Dimensional model built from the Silver model: dimensions, facts, bridges (v2: Dimensional model). |
| Entity | A modeled table in the Silver or Gold model. |
| Attribute | A column of an entity. |
| Link | A child entity's foreign-key attribute pointing at a parent entity (v2: relationship between entities). |
| Definition | A normal data dictionary description of a table, column, entity or attribute. Separate from Grain. |
| Grain | What one row means. Its own field on enriched source tables and on entities. |
| Key | The column that identifies a row. Python adds generated keys. |
| Natural key | The source's own identifier for a row, for example UserNumber. Every entity marks it. Lookups match on it and the orchestrator merges on it. |
| Note for mapping | A short instruction on an entity source or attribute source, saying how to map it (v2: rationale). |
| Audit columns | Standard columns Python adds to every entity (SourceSystemID, CreatedDate and so on). |
| Mapping | Where each attribute of one target entity comes from, for one source system. Two parts: an entity part (source tables, joins, rows to keep, one row per entity, transformation) and one free-text line per attribute. **Silver mapping** reads Bronze; **Gold mapping** reads Silver. They are stored apart. |
| Source system | The system a mapping reads from. One mapping per target entity and source system. |
| Lookup | Finding a parent's key by its natural key, for example CustomerID from CustomerNumber. The facts about the parent come from the model, never from the parent's mapping. |
| Code | SQL that the AI writes from an applied mapping. Python may prepare a starter SQL. It only gives the final data frame; the orchestrator loads it. |
| Orchestrator | The pipeline framework outside the Workbench. It runs the code by tenant and system, replaces the batch ID, and decides how to load the result. |
| Load order | The order entities must load in, parents before children. Python works it out. |

## Changes and rules

| Term | Meaning |
|---|---|
| Change set | A group of changes that are reviewed together and saved together. Two kinds: **metadata** (catalog) and **project**. |
| Draft | A change set that is not saved yet. Runs, pushes and hand edits all make drafts. |
| Item | One change inside a change set: add, change or remove one record. |
| Apply | Saving a whole draft to Postgres in one go, or nothing if something fails. Only a person applies. |
| Reject | Throwing a draft away. |
| Project version | A number that goes up on every Apply. Apply refuses a draft built on an older version. |
| Rule | One check, written in `docs/rules.md` with an ID like `SILVER-001`. |
| Level | **Blocks Apply** (must be fixed) or **Warning** (shown, Apply still allowed). |
| Status | **Proposed** (waiting for Maaz) or **Approved** (may be built). |
| Problem | A rule that failed on a draft. Always shown with its rule ID. |

## Prompts

| Term | Meaning |
|---|---|
| Prompt | Instructions for one step, for example "Silver model – standard". One per step is the default. |
| Prompt version | One saved text of a prompt. Every save makes a new version. |
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
| Demo data | Made-up tenant, users, catalog and project for local testing only (`database/demo/`). Never goes to Azure. |
| Local sign-in | When running locally, you pick a demo user instead of signing in with Microsoft or Databricks. |
| Fake AI | Local stand-in for Foundry that returns a saved answer for each step. |
| Fake Databricks | Local stand-in for a Databricks workspace: small sample tables in files. |

## Old v2 words and their v3 words

| v2 | v3 |
|---|---|
| Atlas, Atlas Platform, Atlas MCP | GDS Workbench, web app, MCP server |
| Object / Attribute (physical) | Table / Column (table names stay `object` / `attribute`) |
| Operational / Dimensional | Silver / Gold |
| Context Record, Context Group | Note |
| Analysis Result | Relationship |
| Project Input Scope | Scope |
| Snapshot | Pull |
| Stage | Push |
| Workflow Run | Run |
| Output Template | (gone: mapping has one fixed shape) |
| Prompt Studio, Prompt Template, Prompt Assignment | Prompts page, Prompt, default prompt |
