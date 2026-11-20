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


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

