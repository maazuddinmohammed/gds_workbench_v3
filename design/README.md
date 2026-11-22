# Design

Short flow files that show how each part of GDS Workbench v3 works: what happens, in what order, and why.
Read these to follow the code. Each file has one diagram and a few short lists.

- `docs/design.md` is the list of decisions.
- `docs/terminology.md` is what the words mean.
- This folder is the flows.

## Where to look

| Folder | File | What it shows |
|---|---|---|
| `overview/` | [path.md](overview/path.md) | The whole path from scope to code, and what each step reads and writes |
| `overview/` | [run.md](overview/run.md) | What happens when a person presses Run |
| `shared/` | [access.md](shared/access.md) | Roles, permissions, tenant lock and MCP access |
| `shared/` | [table-details.md](shared/table-details.md) | The one piece of code that describes a table |
| `shared/` | [samples.md](shared/samples.md) | How sample values are fetched, stored and used |
| `shared/` | [notes-and-prompt-builder.md](shared/notes-and-prompt-builder.md) | Notes, their types, and how the prompt builder puts them in a prompt |
| `workflows/` | [analysis.md](workflows/analysis.md) | Profiling, enrichment and relationships |
| `workflows/` | [subject-areas.md](workflows/subject-areas.md) | Grouping tables into subject areas |
| `workflows/` | [silver-model.md](workflows/silver-model.md) | Building the Silver model |
| `workflows/` | [gold-model.md](workflows/gold-model.md) | Building the Gold model |
| `workflows/` | [mapping.md](workflows/mapping.md) | Silver mapping and Gold mapping |
| `workflows/` | [code.md](workflows/code.md) | Writing the SQL |
| `vscode/` | [agent-notes.md](vscode/agent-notes.md) | Shared knowledge for AI sessions in VS Code |
| `operations/` | [README.md](operations/README.md) | One line per operation, and the exact input and output of all 20 MCP tools |

## How each file is laid out

1. One line saying what the part does.
2. **Flow**: one diagram.
3. **Decided**: what is settled.
4. **Decided when we build it**: details we left open on purpose.

## Keeping it true

- When a decision changes, change the file in the same pull request.
- When a workflow is built, fill in its "Decided when we build it" list and say where the code lives.
- Keep every file short. If a file needs two diagrams, it is probably two files.

## Ideas that hold everywhere

- **The user controls, not the system.** If they do not want a change, they do not run it, or they lock the item.
- **Few rules.** Only checks that are Approved in `docs/rules.md` are built.
- **A step reads only the step before it, plus Notes.** Mapping never reads another mapping. Code reads only
  the mapping. Gold never reads Bronze.
- **The AI only proposes.** Every Run ends in a draft. A person reviews it, then presses Apply or tells the AI in chat
  to apply it.
- **One copy of everything in `core/`.** The web app, the MCP server and the Bridge only call it.
