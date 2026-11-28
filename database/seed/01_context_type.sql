-- 01_context_type.sql
-- Seed: the Note types. Safe to run again: MERGE adds new types and updates names and descriptions.
-- Which steps read which type is decided by the prompt builder in core/, not here.

MERGE INTO reference.context_type AS t
USING (VALUES
    ('operational_model_requirement', 'Operational model requirements', 'Requirements for the operational (Silver) model: entities, keys, Grain, links.'),
    ('dimensional_model_requirement', 'Dimensional model requirements', 'Requirements for the dimensional (Gold) model: facts, dimensions, Grain, measures.'),
    ('mapping_requirement',      'Mapping requirements',      'Requirements for operational and dimensional mapping: filters, joins, lookups, transformations.'),
    ('kpi_requirement',          'KPI requirements',          'The KPIs the models must support and how they are worked out.'),
    ('reporting_requirement',    'Reporting requirements',    'Reports the data must serve, and what they need.'),
    ('source_information',       'Source information',        'Facts about a source system, such as which fields are custom fields.'),
    ('enrichment_requirement',   'Enrichment requirements',   'How tables and columns should be defined and marked.'),
    ('analysis_requirement',     'Analysis requirements',     'Rules for finding links between tables, such as columns never to link on.'),
    ('subject_area_requirement', 'Subject area requirements', 'How tables should be grouped into subject areas.'),
    ('code_requirement',         'Code requirements',         'How the load SQL is written, such as its layout and house standards.'),
    ('validation_requirement',   'Validation requirements',   'Business rules the loaded data must meet, such as every order has a customer.'),
    ('agent',                    'Agent',                     'Shared knowledge for AI sessions in VS Code, such as terminology or working instructions.')
) AS s (context_type_code, context_type_name, context_type_description)
ON lower(btrim(t.context_type_code)) = lower(btrim(s.context_type_code))
WHEN MATCHED THEN UPDATE SET
    context_type_name        = s.context_type_name,
    context_type_description = s.context_type_description,
    updated_time             = CURRENT_TIMESTAMP,
    updated_by               = CURRENT_USER
WHEN NOT MATCHED THEN INSERT (context_type_code, context_type_name, context_type_description)
    VALUES (s.context_type_code, s.context_type_name, s.context_type_description);
