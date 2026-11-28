# Rules: Mapping

A mapping says where each attribute of one target entity comes from, for one source system: an entity part and
one free-text line per attribute. Silver mapping reads Bronze; Gold mapping reads Silver. How rules are written:
[rules.md](../rules.md).

## Checked in core/

### MAPPING-001 · A mapping line is for an attribute of the mapping's own entity
*Blocks Apply · Approved*

**What it means.** Each attribute line in a mapping must be for an attribute of the entity the mapping is for.
This holds for Silver and Gold mapping.

**Why.** A mapping line stores only the mapping and the attribute, so the database cannot check this. A line
for another entity's attribute would end up in the wrong code.

**What happens.** The draft cannot be applied.

**Example.** The mapping for User (system CRM) has a line for User.UserNumber: fine. A line for Device.DeviceID
in that mapping is stopped.

### MAPPING-002 · A mapping's table list names real tables and entities, each alias once
*Blocks Apply · Approved*

**What it means.** Each item in a mapping's table list names an active table in the project's scope, or an active
entity of the project, and has an alias. No alias is used twice in one list.

**Why.** The mapping lines and the code name tables only by alias. A wrong name or a repeated alias makes the
mapping impossible to turn into SQL.

**What happens.** The draft cannot be applied, and the problem names the item.

**Example.** `w` for `workday.Worker` and `p` for `workday.Position`: fine. Two tables with alias `w`: stopped.

### MAPPING-003 · Every attribute except the surrogate key has a mapping line
*Warning · Approved*

**What it means.** In a mapping, every active attribute of the entity except its surrogate key has an active line.

**Why.** An attribute with no line becomes a NOT MAPPED placeholder in the code.

**What happens.** The draft can be applied. The warning names the attribute and, when the AI left it out on
purpose, its reason, such as "No column says whether a worker is an employee or a contractor".

**Example.** Employee from Workday with lines for WorkerID, HireDate and JobProfileID: fine. No line for
IsContractor: a warning.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

