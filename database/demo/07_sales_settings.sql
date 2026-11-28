-- 07_sales_settings.sql
-- Demo data: the settings of project Sales (project.project_config), so its Silver and Gold Runs can be tried
-- locally. Made up for the demo, in the style of the design files' examples.

INSERT INTO project.project_config
    (project_id, operational_schemas, dimensional_schemas, operational_entity_scd_type, dimensional_entity_scd_type,
     operational_naming_instructions, dimensional_naming_instructions, operational_audit_columns,
     dimensional_audit_columns, is_sample_storage_allowed, sample_size)
SELECT p.project_id,
       '[{"schema_name": "silver_sales", "description": "Customers, orders, deliveries and billing."},
         {"schema_name": "silver_people", "description": "Workers, positions and organizations."}]',
       '[{"schema_name": "gold_sales", "description": "Facts and dimensions for sales reporting."}]',
       'type_1', 'type_2',
       'Entity and attribute names are singular, in PascalCase, in full English words.',
       'Dimensions are named Dim<Name> and facts Fact<Name>, in PascalCase; attributes in PascalCase.',
       '[{"name": "CreatedDate", "data_type": "TIMESTAMP", "nullable": false, "definition": "When the load first wrote the row."},
         {"name": "UpdatedDate", "data_type": "TIMESTAMP", "nullable": false, "definition": "When the load last changed the row."},
         {"name": "BatchID", "data_type": "BIGINT", "nullable": false, "definition": "The load batch that last wrote the row."}]',
       '[{"name": "CreatedDate", "data_type": "TIMESTAMP", "nullable": false, "definition": "When the load first wrote the row."},
         {"name": "UpdatedDate", "data_type": "TIMESTAMP", "nullable": false, "definition": "When the load last changed the row."},
         {"name": "ValidFrom", "data_type": "TIMESTAMP", "nullable": false, "definition": "When this version of the row became valid."},
         {"name": "ValidTo", "data_type": "TIMESTAMP", "nullable": true, "definition": "When this version stopped being valid; empty for the current one."},
         {"name": "IsCurrent", "data_type": "BOOLEAN", "nullable": false, "definition": "True for the current version."}]',
       FALSE, 5
  FROM project.project AS p WHERE p.project_name = 'Sales';
