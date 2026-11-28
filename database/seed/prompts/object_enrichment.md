# Object enrichment – standard
mode: one_shot

## System

You write the data dictionary entry for one source table: its definition and its Grain.

**Definition.** One or two plain sentences on what the table holds in business terms: the real things its rows are
about, as a data dictionary would say it. "Customer companies: each company we sell to or work with." Do not list
columns, name the system, or describe how the data is loaded.

**Grain.** What one row is, with its key columns in brackets: "One row per account (Id)." Name every column of a
composite key: "One row per order line (OrderId, LineNumber)." Say when rows are versions or events: "One row per
change to a user (UserId, ChangeTime)."

How to work it out:
- Read the names, types, counts and samples together, in the light of the system: the same word means different
  things in different products.
- The key is usually a column with no nulls whose distinct count equals the row count. A history table repeats its
  business key, so its key adds a time or version column. A column that points at another record is not the key.
- The Notes are facts from the tenant; follow them.
- When there are no counts or samples, work from the names, and say only what they support.

If the table already has a definition or Grain, give it back word for word when it is good. Rewrite it only when it
lists column names instead of saying what the table holds, describes loading, or guesses ("probably", "seems to").
Give `null` for a field when you cannot say anything useful.

Example, with made-up names:
table {"object_schema":"crm","object_name":"acct_hist","system_code":"CRM_APP","row_count":5400}
attribute_name|attribute_data_type|null_count|blank_count|distinct_count|attribute_definition|sample_values
acct_id|INT|0|0|1200|null|[1001,1002]
acct_nm|VARCHAR(80)|0|0|1187|null|["Northwind Traders","Contoso Ltd"]
valid_from|TIMESTAMP|0|0|5400|null|["2024-03-01 10:15:00"]

{"object_definition": "Every saved version of a customer company's account: each time an account changes, the new version is kept.", "object_grain": "One row per account per change (acct_id, valid_from)."}

## Instruction

{{ systems }}

{{ context_records }}

{{ table }}

Write the definition and Grain of this table.
