# GDS Workbench v3

A tool to pick source tables, build Silver and Gold data models, map them, and generate SQL.
People use it from VS Code (plugin + Bridge + Local Workbench) and from a web app.

## Start of every session

1. Read `docs/plan.md` (where we are, what's next), `docs/terminology.md` (what words mean),
   `docs/architecture.md` (the big picture), `docs/design.md` (decisions) and `docs/rules.md` (approved rules).
2. Tell me in two or three lines where we are and the next small step.
3. Wait for my OK before building anything.

## Rules for working here

- Never change the old project (the v2 folder and the old GitHub repo). Read it for reference only.
- Small steps. One small change at a time. Never build a whole feature in one go.
- Keep it simple. If dropping or changing something would make it much simpler, tell me before building.
- Before non-trivial work, if a simpler or sturdier way exists, say so once, up front: "Are you sure you want X?
  Y is simpler because Z." Then do what I choose. Challenge the frame, not just the details. Silence means you
  checked and X is the best path.
- Use the words in `docs/terminology.md`. Add new terms there.
- Explain in plain words. I know Python and SQL; I'm newer to web apps, MCP and VS Code extensions.
- No logic in Postgres: tables, keys and simple checks only. Logic lives in Python in `core/`.
- One copy of every rule, in `core/`. The web app, MCP server and Bridge only call `core/`. Never copy code between folders.
- Only build checks that are **Approved** in `docs/rules/` (index: `docs/rules.md`). A new check starts as **Proposed** there and waits for my approval.
- Every check problem names its rule ID (for example `SILVER-001`).
- The AI only proposes. Changes go into a draft change set; a person presses Apply.
- No automatic retries, re-prompting or repair loops unless I ask for them.
- Database scripts run only against the local throwaway database unless I say otherwise.
- A new schema or table also gets its drop line in `00_preflight.sql` and its name in `99_verify_install.sql`.
- Keep the GitHub repo clean: only `main` stays. Delete a branch as soon as its work is merged or done.
- Claude has no access to the live apps and never deploys. Test everything locally (throwaway Postgres,
  demo data, fake AI, fake Databricks). `scripts/build.py` makes the zips in `dist/`; I upload them by hand.

## Layout (filled in step by step)

- `database/install/` numbered table scripts, one schema per area like v2 (list in `docs/plan.md`)
- `database/seed/` reference data and starter prompts, `database/demo/` demo data for local testing only
- `core/` Python logic shared by everything
- `web_app/backend/` FastAPI (Databricks App), `web_app/frontend/` React
- `mcp_server/` MCP server (Azure App Service), also serves the Bridge's pull/check/push
- `plugin/` skills and MCP address
- `bridge/` VS Code extension: pull, check, push, Local Workbench
- `scripts/` local database, run locally, build zips, database install
- `dist/` build output (zips), not saved in git
- `tests/`
- `design/` short flow files with diagrams, one per workflow and shared part (index in `design/README.md`).
  When a decision or a flow changes, change its file in the same pull request.

## End of every session

- Run the tests for what changed.
- Update "Where we are" and "Next" in `docs/plan.md`, and add any decision to `docs/design.md`.
