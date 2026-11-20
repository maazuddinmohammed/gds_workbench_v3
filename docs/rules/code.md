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


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

