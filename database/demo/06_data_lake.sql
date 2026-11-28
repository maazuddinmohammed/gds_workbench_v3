-- 06_data_lake.sql (demo only, see README.md)
-- Tables on the data lake connection gds_us (owned by GDS). Who a table belongs to is its source tenant, not the
-- connection: the Bronze copies and the Silver table are ACME's, the calendar and currency tables are GDS's own.

INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema, object_name,
                         object_description)
SELECT c.connection_id, t.tenant_id, ot.object_type_id, z.zone_id, o.schema, o.name, o.description
  FROM (VALUES
    ('ACME', 'bronze', 'bronze_sap', 'kna1', 'Raw copy of sap.KNA1.'),
    ('ACME', 'bronze', 'bronze_sap', 'vbak', 'Raw copy of sap.VBAK.'),
    ('ACME', 'bronze', 'bronze_sap', 'vbap', 'Raw copy of sap.VBAP.'),
    ('ACME', 'bronze', 'bronze_salesforce', 'account', 'Raw copy of salesforce.Account.'),
    ('ACME', 'silver', 'silver_sales', 'sales_order', 'Cleaned sales orders.'),
    ('GDS', 'bronze', 'bronze_gds', 'calendar', 'One row per day, with fiscal periods.'),
    ('GDS', 'bronze', 'bronze_gds', 'currency', 'Currencies and their ISO codes.')
  ) AS o (tenant, zone, schema, name, description)
  JOIN core.tenant AS t ON t.tenant_code = o.tenant
  JOIN reference.zone AS z ON z.zone_code = o.zone
  JOIN core.connection AS c ON c.connection_code = 'gds_us'
  JOIN reference.object_type AS ot ON ot.object_type_code = 'TABLE';

-- A Bronze copy has its source table's columns in lower case, landed as text.
INSERT INTO core.attribute (object_id, attribute_name, attribute_ordinal_position, attribute_data_type,
                            attribute_nullability, attribute_description)
SELECT b.object_id, lower(a.attribute_name), a.attribute_ordinal_position, 'STRING', TRUE, a.attribute_description
  FROM (VALUES ('bronze_sap', 'kna1', 'sap', 'KNA1'),
               ('bronze_sap', 'vbak', 'sap', 'VBAK'),
               ('bronze_sap', 'vbap', 'sap', 'VBAP'),
               ('bronze_salesforce', 'account', 'salesforce', 'Account')) AS m (b_schema, b_name, s_schema, s_name)
  JOIN core.object AS b ON b.object_schema = m.b_schema AND b.object_name = m.b_name
  JOIN core.object AS s ON s.object_schema = m.s_schema AND s.object_name = m.s_name
  JOIN core.attribute AS a ON a.object_id = s.object_id;

-- Ingestion lineage: each Bronze copy came from its Source table, column by column. Python uses it to give a Bronze
-- table its source's system (an AI Run shows the Bronze copy with that system's code).
INSERT INTO core.ingestion_object_mapping (source_object_id, target_object_id)
SELECT s.object_id, b.object_id
  FROM (VALUES ('bronze_sap', 'kna1', 'sap', 'KNA1'),
               ('bronze_sap', 'vbak', 'sap', 'VBAK'),
               ('bronze_sap', 'vbap', 'sap', 'VBAP'),
               ('bronze_salesforce', 'account', 'salesforce', 'Account')) AS m (b_schema, b_name, s_schema, s_name)
  JOIN core.object AS b ON b.object_schema = m.b_schema AND b.object_name = m.b_name
  JOIN core.object AS s ON s.object_schema = m.s_schema AND s.object_name = m.s_name;

INSERT INTO core.ingestion_attribute_mapping (ingestion_object_mapping_id, source_object_id, target_object_id,
                                              source_attribute_id, target_attribute_id)
SELECT m.ingestion_object_mapping_id, m.source_object_id, m.target_object_id, sa.attribute_id, ba.attribute_id
  FROM core.ingestion_object_mapping AS m
  JOIN core.attribute AS sa ON sa.object_id = m.source_object_id
  JOIN core.attribute AS ba ON ba.object_id = m.target_object_id AND ba.attribute_name = lower(sa.attribute_name);

INSERT INTO core.attribute (object_id, attribute_name, attribute_ordinal_position, attribute_data_type,
                            attribute_nullability, attribute_description)
SELECT o.object_id, a.name, a.position, a.data_type, a.nullable, a.description
  FROM (VALUES
    ('silver_sales', 'sales_order', 'sales_order_number', 1, 'STRING', FALSE, 'Sales order number.'),
    ('silver_sales', 'sales_order', 'customer_number', 2, 'STRING', FALSE, 'SAP customer number.'),
    ('silver_sales', 'sales_order', 'order_date', 3, 'DATE', FALSE, 'Date the order was created.'),
    ('silver_sales', 'sales_order', 'net_value', 4, 'DECIMAL(15,2)', TRUE, 'Net value of the order.'),
    ('silver_sales', 'sales_order', 'currency_code', 5, 'STRING', TRUE, 'Currency of the order.'),
    ('bronze_gds', 'calendar', 'calendar_date', 1, 'DATE', TRUE, 'The day.'),
    ('bronze_gds', 'calendar', 'fiscal_year', 2, 'INT', TRUE, 'Fiscal year.'),
    ('bronze_gds', 'calendar', 'fiscal_period', 3, 'INT', TRUE, 'Fiscal period, 1 to 12.'),
    ('bronze_gds', 'currency', 'currency_code', 1, 'STRING', TRUE, 'ISO currency code.'),
    ('bronze_gds', 'currency', 'currency_name', 2, 'STRING', TRUE, 'Currency name.')
  ) AS a (table_schema, table_name, name, position, data_type, nullable, description)
  JOIN core.object AS o ON o.object_schema = a.table_schema AND o.object_name = a.table_name;
