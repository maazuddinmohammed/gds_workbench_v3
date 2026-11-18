# Code

The AI writes the SQL for an entity, reading only the applied mapping. The SQL gives the final data frame.
Loading it is the orchestrator's job.

## Flow

```mermaid
flowchart TD
    START(["Run code for an entity"]) --> A{"One file for all systems,<br/>or one file per system?"}
    A --> B["Take the applied mapping<br/>for each system the file covers"]
    B --> C["Python may prepare a starter SQL"]
    C --> D["AI writes the SQL<br/>reads only the mapping"]
    D --> E["SQL: temporary views if needed,<br/>then one final query"]
    E --> F["Draft"]
    F --> G{"Person reviews"}
    G -- Apply --> H[("Code file<br/>belongs to an entity,<br/>lists the systems it covers")]
    H -.-> I["Orchestrator runs it,<br/>reads the final query as a data frame,<br/>and loads it"]
```

## Decided

- **The AI writes the code.** Python may prepare a starter SQL and hand it to the AI.
- **Code reads only the mapping.**
- **The SQL only gives the final data frame.** It may have several temporary views, but the last query is what gets read.
- **The orchestrator decides how to load it** (merge, replace, keep history). Most of the time it is a merge
  on the natural key. So an entity has no "how it is loaded" field.
- **The orchestrator replaces the batch ID at run time.**
- **Stored like v2.** A code file belongs to an entity and lists the systems it covers. So it can be one file
  for all systems, or one file per system.

## Decided when we build it

- What the starter SQL looks like.
- The prompt, and which house standard Notes it is given.
