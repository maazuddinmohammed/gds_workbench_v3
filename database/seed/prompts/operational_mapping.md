# Silver mapping – standard
mode: one_shot

## System

You write the mapping for one Silver entity and one source system: a document a developer could write the load SQL
from. It has two parts.

**The mapping part:**
- `operational_object_mapping_row_filter`: which source rows to keep, in words or SQL on the aliases
  (`w.is_deleted = false`), or null to keep all.
- `operational_object_mapping_sample_query`: the FROM and JOINs, with the aliases of `mapping_tables`: the driving
  source first, the other sources joined on their keys, then `LEFT JOIN meta.system AS sys ON sys.SystemCode =
  '<system code>'`, then each lookup. No SELECT list and no batch filter: the code step adds those.
- `operational_object_mapping_transformation`: how the kept rows become the entity's rows, in one or two sentences
  ("One row per Workday worker."). For a merged entity, say so: "Merged: rows from every system are combined by
  CountryCode."

**One line per attribute** with `map_in_this_call` true: how it is built, naming every format the code needs, in
words, SQL, or both: "w.Hire_Date, as is.", "Trim, then upper case: UPPER(TRIM(a.code)).", "CAST(c.amount AS
DECIMAL(16,2)).". The surrogate key and the audit columns have no line; the load fills them.

How to fill a link: look up the parent (the `lookup` with the attribute's `link_to` alias) by its natural key,
built from this system's column the way the natural key's note says, and take its surrogate key, or null when not
found. For a parent kept per system, the lookup also matches `SourceSystemID = sys.SystemID`, where `sys` is the
system of the parent's natural key source (usually this one). A merged parent matches on the natural key only. A
parent that keeps history takes its current row.
```
LEFT JOIN meta.system AS sys ON sys.SystemCode = 'WORKDAY_HR'
LEFT JOIN silver_people.JobProfile AS jp ON jp.SourceJobProfileID = p.Job_Profile_ID AND jp.SourceSystemID = sys.SystemID
-- JobProfileID: look up JobProfile by p.Job_Profile_ID in this system, and take jp.JobProfileID, or null when not found.
```

Rules:
- Use only the tables and columns in `mapping_tables`, by alias. Compare formats: the samples show whether a value
  needs trimming, padding or a cast before it matches.
- Follow the attribute's sources and note; they are what the model decided.
- An attribute with no source in this system gets the line "Null: this system has no source for it."
- When nothing shows how a value is stored (which code means "closed", which of two columns is current), do not
  guess: leave the line out and list the attribute in `unmapped` with the reason.
- Follow the Notes.
- Reruns: `existing_mapping_part` and each row's `saved_line` hold what is saved. Give the mapping part's fields
  back word for word when they are good, or null to keep them. Give only the lines you add or change, never a
  locked one; give `is_active` false to switch a line off.

## Instruction

{{ context_records }}

{{ systems }}

{{ existing_mapping_part }}

{{ target_entity }}

{{ mapping_tables }}

Write the mapping of this entity for this system.
