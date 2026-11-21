-- 02_systems.sql (demo only, see README.md)
-- The reference rows the demo catalog needs, the four systems, and one connection each.
-- ACME's three source systems belong to ACME; the data lake connection gds_us belongs to GDS.

INSERT INTO reference.system_type (system_type_code, system_type_name, system_type_description)
VALUES ('ERP', 'ERP', 'Enterprise resource planning system.'),
       ('CRM', 'CRM', 'Customer relationship management system.'),
       ('HR', 'HR', 'Human resources system.'),
       ('DATA_LAKE', 'Data lake', 'The data lake where Bronze, Silver and Gold tables live.');

INSERT INTO reference.connection_type (connection_type_code, connection_type_name, connection_type_description)
VALUES ('JDBC', 'JDBC', 'A database reached over JDBC.'),
       ('REST_API', 'REST API', 'A software-as-a-service system read through its REST API.'),
       ('DATABRICKS', 'Databricks', 'A Databricks Unity Catalog.');

INSERT INTO reference.object_type (object_type_code, object_type_name, object_type_description)
VALUES ('TABLE', 'Table', 'A relational table.');

INSERT INTO core.system (system_type_id, system_code, system_name, system_description)
SELECT st.system_type_id, s.code, s.name, s.description
  FROM (VALUES ('SAP_ERP', 'SAP ERP', 'ERP', 'Acme''s SAP system: sales, deliveries, billing, materials, purchasing.'),
               ('SALESFORCE_CRM', 'Salesforce CRM', 'CRM', 'Acme''s Salesforce org: accounts, contacts, pipeline, cases.'),
               ('WORKDAY_HR', 'Workday HR', 'HR', 'Acme''s Workday tenant: workers and their organization.'),
               ('GDS_US', 'GDS US', 'DATA_LAKE', 'The US instance of the data lake.')
       ) AS s (code, name, type, description)
  JOIN reference.system_type AS st ON st.system_type_code = s.type;

INSERT INTO core.connection (tenant_id, system_id, connection_type_id, connection_code, connection_name)
SELECT t.tenant_id, s.system_id, ct.connection_type_id, c.code, c.name
  FROM (VALUES ('ACME', 'SAP_ERP', 'JDBC', 'sap_erp', 'SAP ERP'),
               ('ACME', 'SALESFORCE_CRM', 'REST_API', 'salesforce_crm', 'Salesforce CRM'),
               ('ACME', 'WORKDAY_HR', 'REST_API', 'workday_hr', 'Workday HR'),
               ('GDS', 'GDS_US', 'DATABRICKS', 'gds_us', 'GDS US')
       ) AS c (tenant, system, type, code, name)
  JOIN core.tenant AS t ON t.tenant_code = c.tenant
  JOIN core.system AS s ON s.system_code = c.system
  JOIN reference.connection_type AS ct ON ct.connection_type_code = c.type;

-- ACME's Bronze tables live in the data lake (CATALOG-001).
UPDATE core.tenant
   SET data_lake_connection_id = (SELECT connection_id FROM core.connection WHERE connection_code = 'gds_us')
 WHERE tenant_code = 'ACME';
