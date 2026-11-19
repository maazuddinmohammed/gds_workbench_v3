-- 03_operational_entity_type.sql
-- Seed: kinds of operational entity, the same 14 as v2 (v2 had no name column; the name here is the code in words).
-- Safe to run again: MERGE adds new types and updates names and descriptions.

MERGE INTO reference.operational_entity_type AS t
USING (VALUES
    ('core',             'Core',             'A main business thing with its own identity, such as Customer or Product.'),
    ('reference',        'Reference',        'A short list of codes and their meanings, such as Country or OrderStatus.'),
    ('transaction',      'Transaction',      'A business document or exchange, such as SalesOrder or Invoice. Its lines are transaction_line.'),
    ('transaction_line', 'Transaction line', 'One line of a transaction, such as SalesOrderLine or InvoiceLine.'),
    ('event',            'Event',            'Something that happened at a point in time, such as a login or a shipment scan.'),
    ('association',      'Association',      'Links entities many-to-many, such as ProductCategory.'),
    ('history',          'History',          'Past versions of another entity''s values over time.'),
    ('snapshot',         'Snapshot',         'The state of something at regular points in time, such as month-end balances.'),
    ('agreement',        'Agreement',        'A lasting arrangement with a start and end, such as a Contract, Subscription or Policy.'),
    ('plan',             'Plan',             'Planned or target values, such as a Budget, Forecast or SalesQuota.'),
    ('hierarchy',        'Hierarchy',        'A parent-child or level structure, such as an org chart or account tree.'),
    ('subtype',          'Subtype',          'A specialization that shares another entity''s identity, such as IndividualCustomer of Customer.'),
    ('list',             'List',             'A named, curated set of other entities, such as a Watchlist, MailingList or PriceList.'),
    ('other',            'Other',            'None of the listed types fits; the entity definition says what it is.')
) AS s (operational_entity_type_code, operational_entity_type_name, operational_entity_type_description)
ON lower(btrim(t.operational_entity_type_code)) = lower(btrim(s.operational_entity_type_code))
WHEN MATCHED THEN UPDATE SET
    operational_entity_type_name        = s.operational_entity_type_name,
    operational_entity_type_description = s.operational_entity_type_description,
    updated_time                        = CURRENT_TIMESTAMP,
    updated_by                          = CURRENT_USER
WHEN NOT MATCHED THEN INSERT (operational_entity_type_code, operational_entity_type_name, operational_entity_type_description)
    VALUES (s.operational_entity_type_code, s.operational_entity_type_name, s.operational_entity_type_description);
