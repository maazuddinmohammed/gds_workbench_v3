# Architecture (10,000-foot view)

Words used here are defined in `terminology.md`.

## Components and where they run

```mermaid
flowchart TB
    subgraph LAPTOP["User's laptop"]
        VSC["VS Code + AI<br/>(Copilot)"]
        PLUGIN["Plugin<br/>skills + MCP address"]
        BRIDGE["Bridge<br/>VS Code extension<br/>pull · check · push"]
        WORKBENCH["Local Workbench<br/>review local files"]
        FILES[("Local project files<br/>(JSON)")]
    end

    subgraph BROWSER["Browser"]
        PAGES["Web app pages<br/>Run · review · Apply"]
    end

    subgraph DATABRICKS_APPS["Databricks Apps"]
        WEB["Web app backend<br/>FastAPI + core"]
    end

    subgraph AZURE["Azure"]
        MCP["MCP server<br/>App Service<br/>MCP tools + Bridge endpoints + core"]
        PG[("Postgres<br/>all data, no logic")]
        KV["Key Vault<br/>secrets"]
        FOUNDRY["AI Foundry<br/>models for web Runs"]
    end

    DBX[("Any Databricks workspace<br/>Source and Bronze tables")]

    VSC --> PLUGIN
    VSC -- "MCP tools<br/>(Microsoft sign-in)" --> MCP
    VSC --> BRIDGE
    BRIDGE <--> FILES
    WORKBENCH <--> FILES
    BRIDGE -- "pull · check · push<br/>(HTTPS)" --> MCP

    PAGES -- "HTTPS<br/>(Databricks sign-in)" --> WEB

    WEB --> PG
    MCP --> PG
    WEB --> KV
    MCP --> KV
    WEB -- "Run steps" --> FOUNDRY
    WEB -- "read-only queries" --> DBX
    MCP -- "read-only queries" --> DBX
```

## How it gets built and deployed (by hand)

There is no GitHub Actions and no automatic deploy. `scripts/build.py` runs on your laptop and writes files
into `dist/`. You upload or share them yourself, the same way as v2.

`core/` is not a separate server or a third deployment. It is just a folder of Python code. The build
script copies it into **both** zips, next to the web app code and next to the MCP server code. The repo has
one copy; each zip carries its own copy. When `core/` changes, rebuild and upload both zips.

```mermaid
flowchart LR
    subgraph REPO["Repo: one copy of every file"]
        CORE["core/"]
        WEBCODE["web_app/"]
        MCPCODE["mcp_server/"]
        PLUGINCODE["plugin/"]
        BRIDGECODE["bridge/"]
        DBCODE["database/"]
    end

    subgraph DIST["dist/ made by scripts/build.py"]
        WEBZIP["web.zip<br/>web_app + core"]
        MCPZIP["mcp.zip<br/>mcp_server + core"]
        PLUGINZIP["plugin.zip"]
        VSIX["bridge.vsix"]
    end

    CORE --> WEBZIP
    WEBCODE --> WEBZIP
    CORE --> MCPZIP
    MCPCODE --> MCPZIP
    PLUGINCODE --> PLUGINZIP
    BRIDGECODE --> VSIX

    WEBZIP -- "you upload" --> DBXAPP["Databricks App"]
    MCPZIP -- "you upload" --> APPSVC["Azure App Service"]
    PLUGINZIP -- "you share" --> USERS["Users' VS Code"]
    VSIX -- "you share" --> USERS
    DBCODE -- "you run db_install.py" --> PG[("Azure Postgres")]
```

Each zip gets a `version.txt` (git commit and build time). Both servers show it on their `/health` page,
so you can see at a glance that the web app and the MCP server run the same code.

## How we test locally

Claude never touches the live apps. Everything is tried on a local copy first, on your laptop or in
Claude's cloud session (which has no VS Code, so it tests the web app and MCP server only).

```mermaid
flowchart LR
    subgraph LOCAL["Laptop or Claude's cloud session"]
        BROWSER["Browser"]
        VSC["VS Code<br/>plugin + Bridge<br/>(laptop only)"]
        WEB["Web app<br/>localhost:8000"]
        MCP["MCP server<br/>localhost:8001"]
        PG[("Throwaway Postgres<br/>install + seed + demo data")]
    end
    BROWSER --> WEB
    VSC --> MCP
    WEB --> PG
    MCP --> PG
```

- **Demo data**: demo tenants, one demo user per role, a catalog of three made-up systems (SAP-style ERP,
  Salesforce-style CRM, Workday-style HR, about 22 tables) and a demo project, so every page has something to show.
  It lives in its own folder, `database/demo/`, apart from install and seed, and never goes to Azure.
- **Local sign-in**: you pick a demo user, so each role can be tried.
- **No fake AI or fake Databricks** (Nov 21, Maaz): they bloated v2 and pointed the wrong way. How to try
  Runs and profiling locally is decided when those steps are built.

## How one change flows

Both ways in end in the same `core/` functions and the same kind of draft change set.

```mermaid
flowchart LR
    subgraph WEBWAY["Web app"]
        RUN["Run button<br/>(prompt + AI)"]
    end
    subgraph VSCWAY["VS Code"]
        AI["AI edits local files"] --> PUSH["Bridge push"]
    end
    RUN --> CORE
    PUSH --> CORE
    CORE["core/<br/>check rules"] --> DRAFT["Draft change set"]
    DRAFT --> REVIEW["Person reviews<br/>(web app or Local Workbench)"]
    REVIEW -- "Apply<br/>(all or nothing)" --> PG[("Postgres")]
    REVIEW -- "Reject" --> GONE["Draft discarded"]
```

## What each piece does

| Piece | Runs on | Job |
|---|---|---|
| `core/` | inside the web app and the MCP server | All logic: reads and writes Postgres, checks rules, builds drafts, Apply, SQL generation |
| Web app | Databricks Apps | Pages for every step, Run buttons, review and Apply, prompts, admin, AI cost control |
| MCP server | Azure App Service | Tools for AI in VS Code (and other AI tools); pull, check and push for the Bridge |
| Plugin | laptop | Skills that tell the AI how to do each step; the MCP address |
| Bridge | laptop (VS Code) | Moves project files between laptop and server without passing them through the AI |
| Local Workbench | laptop (VS Code) | Shows local changes and check results; Apply button |
| Postgres | Azure | All data: access, catalog, pipelines, projects, models, mapping, code, change sets, prompts, runs |
| Key Vault | Azure | Database login, Databricks workspace credentials, Foundry access |
| AI Foundry | Azure | AI models for web Runs |
| Databricks workspaces | anywhere the network allows | Source and Bronze data; read-only queries for profiling |
