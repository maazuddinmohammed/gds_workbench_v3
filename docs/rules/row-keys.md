# Rules: Row keys

A row key is what names a row of the Workbench's own Postgres tables in words, for example an entity by its schema
and name. It is not the same as a natural key, which is the source data's own identifier, like UserNumber. Change sets never carry
database ids: each record names its row by row key, and `core/` looks the key up only inside the change set's
project (or tenant catalog). If the key matches a row, the record changes it; if not, the record adds a row.
How rules are written: [rules.md](../rules.md).

## ROW-KEY-001 · Every table that people or change sets write has a row key, enforced by the database
*Database · In the schema (except the gaps at the end)*

**What it means.** For each table below, no two rows can have the same row key. The database refuses the
second one, as a safety layer under `core/`. Names compare ignoring upper and lower case and spaces around them
(marked *name* below), so `Customer` and ` customer ` are the same.

**Why.** If two rows could share a row key, a change set record could not tell which one it means, and
looking it up would pick one at random.

**What happens.** A draft that would create a second row with the same key fails at Apply, and nothing is saved.

**How a child row is named.** In the database a child points at its parent by id (an attribute has its entity's
id). In a change set the record names the parent by the parent's own row key instead, so an operational
attribute is project + entity schema + entity name + attribute name.

## The keys

Reference lists: every list is keyed by its code, or by its name for the lists that have no code (location type,
chunk type, file type, data operation, process type, system notebook). An AI model is keyed by provider + model name.

**Catalog and pipelines (`core`)**

| Table | Natural key | Constraint |
|---|---|---|
| lane | code | `ux_lane_code` |
| tenant | code | `ux_tenant_code` |
| system | code | `ux_system_code` |
| connection | tenant + system + code | `ux_connection_tenant_system_code` |
| connection_value | connection + parameter + environment | `uq_connection_value_parameter_environment` |
| connection_location | connection + location type + environment | `uq_connection_location_type_environment` |
| system_notebook_path | system + notebook | `uq_system_notebook_path_system_notebook` |
| object (table) | connection + *schema* + *name* | `ux_object_connection_schema_name` |
| attribute (column) | table + *name* (and table + position) | `ux_attribute_object_name`, `uq_attribute_object_ordinal` |
| ingestion_object_mapping | source table + target table | `uq_ingestion_object_mapping_source_target` |
| ingestion_attribute_mapping | table mapping + source column + target column | `uq_ingestion_attribute_mapping_source_target` |
| copy_group | tenant + system + *name* | `ux_copy_group_tenant_system_name` |
| copy | copy group + table mapping | `uq_copy_group_mapping` |
| member_group | tenant + system + *name* | `ux_member_group_tenant_system_name` |
| member | member group + *code* | `ux_member_group_code` |
| process_group | tenant + system + zone + *name* | `ux_process_group_tenant_system_zone_name` |
| process | process group + order + location + executable | `uq_process_group_order_location_executable` (see the gaps) |

**Access (`security`)**

| Table | Natural key | Constraint |
|---|---|---|
| principal (user) | email; also Microsoft object ID | `uq_principal_email`, `uq_principal_entra_object_id` |
| tenant_principal_access | tenant + user | `uq_tenant_principal_access_tenant_principal` |
| tenant_lock | tenant | `uq_tenant_lock_tenant` |

**Projects and Notes (`project`)**

| Table | Natural key | Constraint |
|---|---|---|
| project | tenant + *name* | `ux_project_tenant_name` |
| project_config | project | `uq_project_config_project` |
| project_input_scope | project + table | `uq_project_input_scope_project_object` |
| context_group (Note group) | project + *name* | `ux_context_group_project_name` |
| context_record (Note) | Note group + Note number (`#3`) | `uq_context_record_group_number` |

**Workflow (`workflow`).** Operational and dimensional tables have the same keys; only operational is shown.

| Table | Natural key | Constraint |
|---|---|---|
| attribute_profile, attribute_enrichment | project + table + column | `uq_attribute_profile_project_attribute`, `uq_attribute_enrichment_project_attribute` |
| object_enrichment | project + table | `uq_object_enrichment_project_object` |
| analysis_result (relationship) | project + from table and column + to table and column (one relationship per pair; the kind is a field) | `uq_analysis_result_project_from_to` |
| subject_area | project + *name* | `ux_subject_area_project_name` |
| subject_area_table | subject area + table | `uq_subject_area_table_area_object` |
| operational_entity | project + *schema* + *name* | `ux_operational_entity_project_schema_name` |
| operational_attribute | entity + *name* | `ux_operational_attribute_entity_name` |
| operational_entity_source | entity + source table | `uq_operational_entity_source_entity_source` |
| operational_attribute_source | attribute + source column | `uq_operational_attribute_source_attribute_source` |
| operational_link | child attribute: one link per attribute, so a lookup always knows its parent; a second parent gets its own key attribute (Nov 20, Maaz) | `uq_operational_link_operational_attribute` |
| operational_object_mapping | entity + source system | `uq_operational_object_mapping_entity_system` |
| operational_attribute_mapping | mapping + attribute | `uq_operational_attribute_mapping_mapping_attribute` |
| operational_code | entity + *file name* | `ux_operational_code_entity_file_name` |
| operational_code_system | code file + system | `uq_operational_code_system_code_system` |
| operational_validation_group | project + system + *name* | `ux_operational_validation_group_system_name` |
| operational_validation_check | group + *name* | `ux_operational_validation_check_group_name` |

**Prompts (`application`)**

| Table | Natural key | Constraint |
|---|---|---|
| prompt | *name* among global prompts; tenant + *name* among a tenant's prompts | `ux_prompt_global_name`, `ux_prompt_tenant_name` |
| prompt_version | prompt + version number | `uq_prompt_version_number` |

**No row key, on purpose.** Change sets and their pieces, Runs, the Run log and AI usage are records of
something that happened. They are created once, found by their id, and never written through a change set.

## Decided exceptions

- **Note (`context_record`)**: a small Note number instead of a title (Nov 21, Maaz). `core/` gives the next
  number in the group when a Note is added; it stays when the text changes and is never reused. A pushed Note
  without a number is new; one with a number updates that Note.
- **Process (`core.process`)**: decided (Nov 21, Maaz) to keep the key as group + order + location + executable.
  Processes are changed from VS Code; later, the push check can tell the person when a change moves a process to
  another position, so they can fix it before it is applied.
