# Operations: Runs

Pressing Run on an AI step, following it, and the models it can use (design/overview/run.md). Built in step 6 (Nov 28,
by Claude overnight). Columns and the rules every call gets are in the [README](README.md).

| # | Operation | Web | MCP tool | `core/` | Needs |
|---|---|---|---|---|---|
| R1 | Press Run on a step: check it (RUN-001 to 005), save it as running, and do it in the background | `POST /api/projects/{p}/runs` **Built** | - (`start_profiling_run` for profiling) | `runs.start_run`, then `runs.execute` | `CHANGE` |
| R2 | One Run: status, settings, the draft it made, its log and what its AI calls cost | `GET /api/runs/{r}` **Built** | - (`get_profiling_run`) | `runs.get_run` | `READ` |
| R3 | The Run log | `GET /api/runs/{r}/events` **Built** | - | `runs.get_run` | `READ` |
| R4 | The project's latest Runs, newest first (added: the Overview and step pages show the latest Run of each step) | `GET /api/projects/{p}/runs` **Built** | - | `runs.list_runs` | `READ` |
| R5 | The models and the efforts each allows | `GET /api/models` **Built** | - | `runs.list_models` | signed in |

The request (`POST /runs`) names the step (`project_workflow`) and what the person picked in `request`, such as
`{"tables": [{"object_schema": "...", "object_name": "..."}]}` (every scope table when left out). It may change the
prompt version, model, effort, turn limit and add extra instructions for this Run; otherwise the project's defaults
are used. Each step's file in `design/workflows/` says what it picks.
