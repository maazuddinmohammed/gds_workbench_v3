-- 03_sap_erp.sql (demo only, see README.md)
-- SAP-style ERP on connection sap_erp, Source zone, schema sap. Table and column names follow SAP's public naming.

INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema, object_name,
                         object_description, is_active)
SELECT c.connection_id, c.tenant_id, ot.object_type_id, z.zone_id, 'sap', o.name, o.description, o.active
  FROM (VALUES
    ('KNA1', 'Customer master: one row per customer.', TRUE),
    ('KNVV', 'Customer sales data: one row per customer and sales area.', TRUE),
    ('VBAK', 'Sales order headers.', TRUE),
    ('VBAP', 'Sales order items.', TRUE),
    ('LIKP', 'Delivery headers.', TRUE),
    ('LIPS', 'Delivery items, each pointing at a sales order item.', TRUE),
    ('VBRK', 'Billing document headers (invoices).', TRUE),
    ('MARA', 'Material master: one row per material.', TRUE),
    ('MAKT', 'Material descriptions, one per material and language.', TRUE),
    ('LFA1', 'Vendor master: one row per vendor.', TRUE),
    ('EKKO', 'Purchase order headers.', TRUE),
    ('EKPO', 'Purchase order items.', TRUE),
    ('ZOLD_ORDERS', 'Old custom orders table, no longer used.', FALSE)
  ) AS o (name, description, active)
  JOIN core.connection AS c ON c.connection_code = 'sap_erp'
  JOIN reference.zone AS z ON z.zone_code = 'source'
  JOIN reference.object_type AS ot ON ot.object_type_code = 'TABLE';

INSERT INTO core.attribute (object_id, attribute_name, attribute_ordinal_position, attribute_data_type,
                            attribute_nullability, attribute_description)
SELECT o.object_id, a.name, a.position, a.data_type, a.nullable, a.description
  FROM (VALUES
    ('KNA1', 'KUNNR', 1, 'CHAR(10)', FALSE, 'Customer number.'),
    ('KNA1', 'NAME1', 2, 'CHAR(35)', TRUE, 'Customer name.'),
    ('KNA1', 'LAND1', 3, 'CHAR(3)', TRUE, 'Country key.'),
    ('KNA1', 'ORT01', 4, 'CHAR(35)', TRUE, 'City.'),
    ('KNA1', 'PSTLZ', 5, 'CHAR(10)', TRUE, 'Postal code.'),
    ('KNA1', 'ERDAT', 6, 'DATS', TRUE, 'Date the customer was created.'),
    ('KNVV', 'KUNNR', 1, 'CHAR(10)', FALSE, 'Customer number.'),
    ('KNVV', 'VKORG', 2, 'CHAR(4)', FALSE, 'Sales organization.'),
    ('KNVV', 'VTWEG', 3, 'CHAR(2)', FALSE, 'Distribution channel.'),
    ('KNVV', 'SPART', 4, 'CHAR(2)', FALSE, 'Division.'),
    ('KNVV', 'KDGRP', 5, 'CHAR(2)', TRUE, 'Customer group.'),
    ('VBAK', 'VBELN', 1, 'CHAR(10)', FALSE, 'Sales order number.'),
    ('VBAK', 'AUART', 2, 'CHAR(4)', TRUE, 'Sales order type.'),
    ('VBAK', 'ERDAT', 3, 'DATS', TRUE, 'Date the order was created.'),
    ('VBAK', 'KUNNR', 4, 'CHAR(10)', TRUE, 'Sold-to customer number.'),
    ('VBAK', 'VKORG', 5, 'CHAR(4)', TRUE, 'Sales organization.'),
    ('VBAK', 'NETWR', 6, 'CURR(15,2)', TRUE, 'Net value of the order.'),
    ('VBAK', 'WAERK', 7, 'CUKY(5)', TRUE, 'Currency of the order.'),
    ('VBAP', 'VBELN', 1, 'CHAR(10)', FALSE, 'Sales order number.'),
    ('VBAP', 'POSNR', 2, 'NUMC(6)', FALSE, 'Item number.'),
    ('VBAP', 'MATNR', 3, 'CHAR(18)', TRUE, 'Material number.'),
    ('VBAP', 'KWMENG', 4, 'QUAN(15,3)', TRUE, 'Ordered quantity.'),
    ('VBAP', 'VRKME', 5, 'UNIT(3)', TRUE, 'Sales unit.'),
    ('VBAP', 'NETWR', 6, 'CURR(15,2)', TRUE, 'Net value of the item.'),
    ('VBAP', 'WERKS', 7, 'CHAR(4)', TRUE, 'Plant.'),
    ('LIKP', 'VBELN', 1, 'CHAR(10)', FALSE, 'Delivery number.'),
    ('LIKP', 'LFART', 2, 'CHAR(4)', TRUE, 'Delivery type.'),
    ('LIKP', 'KUNNR', 3, 'CHAR(10)', TRUE, 'Ship-to customer number.'),
    ('LIKP', 'WADAT_IST', 4, 'DATS', TRUE, 'Actual goods issue date.'),
    ('LIPS', 'VBELN', 1, 'CHAR(10)', FALSE, 'Delivery number.'),
    ('LIPS', 'POSNR', 2, 'NUMC(6)', FALSE, 'Delivery item number.'),
    ('LIPS', 'VGBEL', 3, 'CHAR(10)', TRUE, 'Sales order number this item delivers.'),
    ('LIPS', 'VGPOS', 4, 'NUMC(6)', TRUE, 'Sales order item number this item delivers.'),
    ('LIPS', 'MATNR', 5, 'CHAR(18)', TRUE, 'Material number.'),
    ('LIPS', 'LFIMG', 6, 'QUAN(13,3)', TRUE, 'Delivered quantity.'),
    ('VBRK', 'VBELN', 1, 'CHAR(10)', FALSE, 'Billing document number.'),
    ('VBRK', 'FKART', 2, 'CHAR(4)', TRUE, 'Billing type.'),
    ('VBRK', 'FKDAT', 3, 'DATS', TRUE, 'Billing date.'),
    ('VBRK', 'KUNAG', 4, 'CHAR(10)', TRUE, 'Sold-to customer number.'),
    ('VBRK', 'NETWR', 5, 'CURR(15,2)', TRUE, 'Net value of the invoice.'),
    ('VBRK', 'WAERK', 6, 'CUKY(5)', TRUE, 'Currency of the invoice.'),
    ('MARA', 'MATNR', 1, 'CHAR(18)', FALSE, 'Material number.'),
    ('MARA', 'MTART', 2, 'CHAR(4)', TRUE, 'Material type.'),
    ('MARA', 'MATKL', 3, 'CHAR(9)', TRUE, 'Material group.'),
    ('MARA', 'MEINS', 4, 'UNIT(3)', TRUE, 'Base unit of measure.'),
    ('MARA', 'BRGEW', 5, 'QUAN(13,3)', TRUE, 'Gross weight.'),
    ('MAKT', 'MATNR', 1, 'CHAR(18)', FALSE, 'Material number.'),
    ('MAKT', 'SPRAS', 2, 'LANG(1)', FALSE, 'Language key.'),
    ('MAKT', 'MAKTX', 3, 'CHAR(40)', TRUE, 'Material description.'),
    ('LFA1', 'LIFNR', 1, 'CHAR(10)', FALSE, 'Vendor number.'),
    ('LFA1', 'NAME1', 2, 'CHAR(35)', TRUE, 'Vendor name.'),
    ('LFA1', 'LAND1', 3, 'CHAR(3)', TRUE, 'Country key.'),
    ('LFA1', 'ORT01', 4, 'CHAR(35)', TRUE, 'City.'),
    ('EKKO', 'EBELN', 1, 'CHAR(10)', FALSE, 'Purchase order number.'),
    ('EKKO', 'BSART', 2, 'CHAR(4)', TRUE, 'Purchase order type.'),
    ('EKKO', 'LIFNR', 3, 'CHAR(10)', TRUE, 'Vendor number.'),
    ('EKKO', 'BEDAT', 4, 'DATS', TRUE, 'Purchase order date.'),
    ('EKKO', 'WAERS', 5, 'CUKY(5)', TRUE, 'Currency.'),
    ('EKPO', 'EBELN', 1, 'CHAR(10)', FALSE, 'Purchase order number.'),
    ('EKPO', 'EBELP', 2, 'NUMC(5)', FALSE, 'Item number.'),
    ('EKPO', 'MATNR', 3, 'CHAR(18)', TRUE, 'Material number.'),
    ('EKPO', 'MENGE', 4, 'QUAN(13,3)', TRUE, 'Ordered quantity.'),
    ('EKPO', 'NETPR', 5, 'CURR(11,2)', TRUE, 'Net price.'),
    ('EKPO', 'WERKS', 6, 'CHAR(4)', TRUE, 'Plant.'),
    ('ZOLD_ORDERS', 'ORDER_NO', 1, 'CHAR(10)', FALSE, 'Order number.'),
    ('ZOLD_ORDERS', 'CUSTOMER', 2, 'CHAR(10)', TRUE, 'Customer number.')
  ) AS a (table_name, name, position, data_type, nullable, description)
  JOIN core.connection AS c ON c.connection_code = 'sap_erp'
  JOIN core.object AS o ON o.connection_id = c.connection_id AND o.object_schema = 'sap' AND o.object_name = a.table_name;
