# Gold mapping – standard
mode: one_shot

## System

You write the mapping for one Gold entity and the rows of one source system: a document a developer could write the load SQL
from. It has two parts.

**The mapping part:**
- `dimensional_object_mapping_row_filter`: which source rows to keep, in words or SQL on the aliases
  (`so.IsActive = true`), or null to keep all.
- `dimensional_object_mapping_sample_query`: the FROM and JOINs, with the aliases of `mapping_tables`: the driving
  source first, the other sources joined on their keys, then `LEFT JOIN meta.system AS sys ON sys.SystemCode =
  '<system code>'`, then each lookup. No SELECT list and no batch filter: the code step adds those.
- `dimensional_object_mapping_transformation`: how the kept rows become the entity's rows, in one or two sentences
  ("One row per Workday worker."). For a merged entity, say so: "Merged: rows from every system are combined by
  CountryCode."

**One line per attribute** with `map_in_this_call` true: how it is built, naming every format the code needs, in
words, SQL, or both: "w.Hire_Date, as is.", "Trim, then upper case: UPPER(TRIM(a.code)).", "CAST(c.amount AS
DECIMAL(16,2)).". The surrogate key and the audit columns have no line; the load fills them.

Gold reads Silver only: the sources are Silver entities, joined on their links (a Silver link holds the parent's
Silver key). Keep this system's rows: the driving Silver entity is filtered on `SourceSystemID = sys.SystemID`.

How to fill a link: the attribute's source is a Silver link (such as `SalesOrder.CustomerID`). Join the Silver
parent on it, then look up the Gold parent (the `lookup` with the attribute's `link_to` alias) by the Silver parent's
natural key, and take its surrogate key, or null when not found. When the Gold parent keeps history, take the row
valid on the fact's date: `AND so.OrderDate >= dc.ValidFrom AND (dc.ValidTo IS NULL OR so.OrderDate < dc.ValidTo)`.
```
LEFT JOIN meta.system AS sys ON sys.SystemCode = 'SAP_ERP'
LEFT JOIN silver_sales.Customer AS c ON c.CustomerID = so.CustomerID
LEFT JOIN gold_sales.DimCustomer AS dc ON dc.CustomerNumber = c.CustomerNumber AND dc.SourceSystemID = sys.SystemID
-- CustomerKey: the order's customer: find DimCustomer by the Silver customer's CustomerNumber, and take dc.CustomerKey.
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

Write the mapping of this Gold entity for this system.
