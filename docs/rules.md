# Rules and checks

Every check the system makes is written down, in plain English, in the files under `docs/rules/`, one file per
group. Nothing is checked that is not listed there. This page says how rules work and where each group is.

## How this works

- Each rule has an **ID** (like `SCOPE-001`), a **level** and a **status**.
- **Level**:
  - `Blocks Apply`: must be fixed before Apply.
  - `Warning`: shown, but Apply is allowed.
  - `Refuses the request`: the action is not done at all, for example a read or a Run.
  - `Database`: Postgres refuses the row itself (a key, unique or check constraint).
- **Status**: `Proposed` (written down, waiting for Maaz), `Approved` (Maaz said yes, may be built) or
  `In the schema` (a database rule that came with the reviewed install scripts).
- Only `Approved` rules get built. A new rule is added as `Proposed` first, in its own small change.
- Each group file has two parts: **Checked in core/** and **Checked by the database**.
- In code, each core/ rule is one small Python function named after its ID, with a test for the pass and fail
  examples. A test checks that code and these files agree, so no rule can be added quietly.
- Database rules are listed only when they are not obvious. Obvious ones (required fields, names not blank,
  values from a fixed list, primary and foreign keys) are not listed. Each listed one names its constraint.
- Every problem shown in the web app, Local Workbench or to the AI starts with the rule ID.
- Apply runs the `Blocks Apply` rules on the project (or tenant catalog) as it would be after Apply, not only on
  the rows in the draft. So a draft that takes a table out of scope is stopped if a subject area still uses it.

## How a rule is written

Each rule is written so that someone reading it alone knows what it is, what it means and why it is there:

```
### SILVER-001 · Every Silver entity has exactly one key column
*Blocks Apply · Proposed*

**What it means.** The rule in full, in plain words, with any edge cases.

**Why.** What goes wrong without it.

**What happens.** What the person sees when it fails, and what they do about it.

**Example.** One case that passes and one that fails.
```

Add other short paragraphs when a rule needs them (for example, how it works with another rule). Database rules
are shorter: the heading, the line with the constraint name and status, and a few sentences. Their status is
`In the schema` (reviewed with the install scripts).

The rule above is only an example of the layout. It is not approved.

## Groups

| Group | File | Covers |
|---|---|---|
| Access | [access.md](rules/access.md) | reading, roles, tenant lock, MCP access |
| Scope | [scope.md](rules/scope.md) | the tables a project works on |
| Change sets | [change-sets.md](rules/change-sets.md) | drafts, Apply, Reject, versions, locks, pushes |
| Natural keys | [natural-keys.md](rules/natural-keys.md) | what names each row, and the database keys that enforce it |
| Runs | [runs.md](rules/runs.md) | pressing Run |
| Subject areas | [subject-areas.md](rules/subject-areas.md) | grouping tables into areas |
| Operational model | [operational-model.md](rules/operational-model.md) | the Silver model |
| Dimensional model | [dimensional-model.md](rules/dimensional-model.md) | the Gold model |
| Mapping | [mapping.md](rules/mapping.md) | Silver and Gold mapping |
| Code | [code.md](rules/code.md) | the SQL |

Still to come, each in its own small step: the database checks of the groups above that say "Not listed yet",
and new groups for the catalog and pipelines, project settings, Notes, profiling, enrichment and relationships,
validation groups, prompts, and the install itself (audit columns, what `99_verify_install.sql` checks).
