# Rules: Enrichment and relationships

Enrichment describes each scope table and its columns; relationships are the links between source columns. Both are
owned by the project. How rules are written: [rules.md](../rules.md).

## Checked in core/

### ENRICHMENT-001 · Enrichment is for scope tables and their active columns
*Blocks Apply · Approved*

**What it means.** A table's enrichment is for an active table in the project's scope, and a column's enrichment
is for an active column of that table.

**Why.** The AI names tables and columns by text. A wrong or switched-off name would be saved as enrichment that
nothing uses.

**What happens.** The draft cannot be applied, and the problem names the table or column.

**Example.** Enrichment for `salesforce.Contact.AccountId`: fine. For a column `AccountNumber` that Contact does not
have: stopped.

### RELATIONSHIP-001 · Both ends of a link are active columns of scope tables, and different columns
*Blocks Apply · Approved*

**What it means.** A relationship goes from an active column of a scope table to an active column of a scope table,
and the two are not the same column. Both may be in the same table.

**Why.** A link to a table out of scope cannot be modeled, and a column linked to itself means nothing.

**What happens.** The draft cannot be applied, and the problem names the link.

**Example.** Contact.AccountId to Account.Id: fine. Contact.AccountId to a table not in scope: stopped.

### RELATIONSHIP-002 · Two columns are linked at most once
*Blocks Apply · Approved*

**What it means.** Two columns have at most one relationship between them, in either direction.

**Why.** The Silver model turns each link into something, such as a link attribute. The same pair linked twice, once
each way, would be modeled twice.

**What happens.** The draft cannot be applied, and the problem names both links.

**Example.** Contact.AccountId to Account.Id: fine. Adding Account.Id to Contact.AccountId as well: stopped.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.
