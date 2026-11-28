# Rules: Validation

Validation groups and checks: the checks that test one entity's loaded table for one system, after the code has run.
How rules are written: [rules.md](../rules.md).

## Checked in core/

### VALIDATION-001 · A check's pass condition fits together
*Blocks Apply · Proposed*

**What it means.** A check's result type, operator, value type and expected value fit each other: for example `in`
needs a list of values, `is_null` needs no value, and a value type `query` needs a comparison query. A check the AI
writes always counts rows, so Python sets `integer`, `equal`, `literal` and `0`. This rule is for hand edits.

**Why.** A pass condition that does not fit can never be worked out when the check runs.

**What happens.** The draft cannot be applied, and the problem names the check.

**Example.** Operator `equal` with the value `0`: fine. Operator `in` with one value and no list: stopped.

### VALIDATION-002 · A check reads the loaded table, and only tables it may read
*Warning · Proposed*

**What it means.** A check's query reads the entity's loaded table, and no table outside the mapping's tables, the
lookup entities and `meta.system`.

**Why.** A check that never reads the loaded table cannot fail when the code is wrong, and one that reads other
tables tests something else.

**What happens.** The draft can be applied. The warning names the check and the table.

**Example.** A query on `silver_people.Employee` and `workday.Worker`: fine. `SELECT 0`: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.
