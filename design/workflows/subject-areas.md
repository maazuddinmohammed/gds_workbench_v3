# Subject areas

The AI groups the scope tables into business areas, like Sales or HR. An area decides which tables a
Silver or Gold Run works on.

## Flow

```mermaid
flowchart TD
    START(["Run subject areas"]) --> AI["AI groups the scope tables into areas"]
    AI --> DRAFT["Draft"]
    DRAFT --> REVIEW{"Person reviews<br/>can move tables"}
    REVIEW -- Apply --> EACH{"Where is each table?"}
    EACH -- "in one area" --> ONE["Modeled in that area's Run"]
    EACH -- "in several areas" --> MANY["Modeled in each of those Runs<br/>the same entity is built on,<br/>never copied"]
    EACH -- "in no area" --> NONE["Unassigned<br/>not modeled"]
```

## Decided

- The AI groups the tables. The person can change the groups.
- A table can be in more than one area.
- A table that fits no area stays unassigned and is not modeled.
- No area is a table's "home". See [silver-model.md](silver-model.md).
- The step can be run again, with no restrictions.
- No sample values are used here.

## Decided when we build it

- What the AI is shown for each table.
