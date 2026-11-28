# Rules: Code

Code is the SQL the AI writes from an applied mapping. A code file belongs to an entity and lists the source
systems it covers. How rules are written: [rules.md](../rules.md).

## Checked in core/

### CODE-001 · A source system is usually in only one code file of an entity
*Warning · Approved (changed from Blocks Apply, Nov 20, Maaz)*

**What it means.** For one entity, each source system normally appears in only one of its code files. If it is
in two, the draft shows a warning, but it can still be applied: there are rare special cases where this is right.

**Why.** A code file lists its systems, and the orchestrator runs the code by system. Two files for the same
entity and system would load that system's data twice.

**What happens.** The review shows a warning naming the entity, the system and both files. The person checks it
and either fixes it or applies anyway.

**Example.** User has `user_crm.sql` for CRM and `user_erp.sql` for ERP: fine. `user_all.sql` and
`user_crm.sql` both listing CRM: warning.

### CODE-002 · The SQL only reads, and parses
*Blocks Apply · Approved*

**What it means.** A code file's SQL, and a validation check's query, hold only temporary views and one final SELECT.
Nothing writes, drops or changes anything, and the SQL parses as Databricks SQL.

**Why.** The orchestrator reads the final query as a data frame and does the loading itself. SQL that writes would
change the lake outside every review.

**What happens.** The draft cannot be applied, and the problem says what was found.

**Example.** `CREATE OR REPLACE TEMPORARY VIEW temp_employee_workday_hr AS (...); SELECT ... FROM
temp_employee_workday_hr`: fine. `DELETE FROM silver_people.Employee`: stopped.

### CODE-003 · The final SELECT returns every attribute, with SourceSystemID last
*Warning · Approved*

**What it means.** The final SELECT returns every active attribute of the entity except the surrogate key, by
name, and `SourceSystemID` as its last column.

**Why.** The orchestrator loads the columns by name. A missing column loads as empty, and the fixed conventions put
`SourceSystemID` last.

**What happens.** The draft can be applied. The warning names what is missing or out of place.

**Example.** `SELECT WorkerID, HireDate, JobProfileID, IsContractor, SourceSystemID`: fine. HireDate missing: a
warning.

### CODE-004 · A column is left as a NOT MAPPED placeholder
*Warning · Approved*

**What it means.** The SQL has a column written as `CAST(NULL AS <type>) AS <name> -- NOT MAPPED: <reason>`.

**Why.** The placeholder marks a column the AI could not write, so a person finishes it.

**What happens.** The draft can be applied. The warning names the column and the reason.

**Example.** `CAST(NULL AS BOOLEAN) AS IsContractor, -- NOT MAPPED: no mapping line`: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

