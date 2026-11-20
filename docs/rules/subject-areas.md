# Rules: Subject areas

A subject area is a business group of scope tables, like Sales. It decides which tables a Silver or Gold Run
works on. A table can be in more than one area. How rules are written: [rules.md](../rules.md).

## Checked in core/

### SUBJECT-AREA-001 · A subject area table must be in the project's scope
*Blocks Apply · Approved*

**What it means.** Every table in a subject area must be in that project's scope, now and after the Apply.

**Why.** A subject area table row stores only the area and the table, so the database cannot see the project's
scope. Without this check an area could hold a table the project does not work on.

**What happens.** The draft cannot be applied. This also stops a table from being taken out of scope while an
area still uses it: take it out of the area first, then out of scope.

**Example.** Area Sales in project Retail has `bronze.orders`, which is in Retail's scope: fine. Adding
`bronze.payroll`, which is not in scope, is stopped. So is a draft that takes `bronze.orders` out of scope while
Sales still has it.


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

