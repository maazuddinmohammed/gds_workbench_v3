# Rules: Subject areas

A subject area is a business group of scope tables, like Sales. It decides which tables a Silver or Gold Run
works on. A table can be in more than one area. How rules are written: [rules.md](../rules.md).

## Checked in core/

### SUBJECT-AREA-001 · A subject area table must be in the project's scope
*Blocks Apply · Approved (wording Nov 28, Maaz: only active rows count)*

**What it means.** Every table in an active subject area must be in that project's scope, now and after the Apply.
Only active rows count: a switched-off area, or a table switched off in an area, never stops a table from leaving
scope.

**Why.** A subject area table row stores only the area and the table, so the database cannot see the project's
scope. Without this check an area could hold a table the project does not work on.

**What happens.** The draft cannot be applied. This also stops a table from being taken out of scope while an
area still uses it: take it out of the area first, then out of scope.

**Example.** Area Sales in project Retail has `bronze.orders`, which is in Retail's scope: fine. Adding
`bronze.payroll`, which is not in scope, is stopped. So is a draft that takes `bronze.orders` out of scope while
Sales still has it.

### SUBJECT-AREA-002 · Every scope table is in an area
*Warning · Proposed*

**What it means.** Every active scope table is in at least one active subject area.

**Why.** Only tables in an area are modeled. A table in no area is easy to miss.

**What happens.** The draft can be applied. The warning names each table in no area.

**Example.** Salesforce's Case table in area Service: fine. Case in no area: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

