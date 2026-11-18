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

(none yet)

## Silver model

(none yet)

## Gold model

(none yet)

## Silver mapping

(none yet)

## Gold mapping

(none yet)

## Code generation

(none yet)
