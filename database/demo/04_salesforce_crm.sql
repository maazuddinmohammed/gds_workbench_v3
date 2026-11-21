-- 04_salesforce_crm.sql (demo only, see README.md)
-- Salesforce-style CRM on connection salesforce_crm, Source zone, schema salesforce. Object and field names follow
-- Salesforce's public naming; fields ending in __c are Acme's own custom fields.

INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema, object_name,
                         object_description)
SELECT c.connection_id, c.tenant_id, ot.object_type_id, z.zone_id, 'salesforce', o.name, o.description
  FROM (VALUES
    ('Account', 'Companies Acme sells to. Carries the SAP customer number when the account is a customer in SAP.'),
    ('Contact', 'People at an account.'),
    ('Opportunity', 'Deals in the sales pipeline.'),
    ('Lead', 'Prospects not yet turned into an account and contact.'),
    ('Case', 'Customer service cases.'),
    ('User', 'Salesforce users: Acme''s sales and service staff. Carries the Workday worker ID.')
  ) AS o (name, description)
  JOIN core.connection AS c ON c.connection_code = 'salesforce_crm'
  JOIN reference.zone AS z ON z.zone_code = 'source'
  JOIN reference.object_type AS ot ON ot.object_type_code = 'TABLE';

INSERT INTO core.attribute (object_id, attribute_name, attribute_ordinal_position, attribute_data_type,
                            attribute_nullability, attribute_description)
SELECT o.object_id, a.name, a.position, a.data_type, a.nullable, a.description
  FROM (VALUES
    ('Account', 'Id', 1, 'ID(18)', FALSE, 'Account ID.'),
    ('Account', 'Name', 2, 'TEXT(255)', FALSE, 'Account name.'),
    ('Account', 'Type', 3, 'PICKLIST', TRUE, 'Customer, Prospect or Partner.'),
    ('Account', 'Industry', 4, 'PICKLIST', TRUE, 'Industry.'),
    ('Account', 'BillingCountry', 5, 'TEXT(80)', TRUE, 'Billing country.'),
    ('Account', 'SAP_Customer_Number__c', 6, 'TEXT(10)', TRUE, 'SAP customer number (KNA1.KUNNR), filled once the account is a customer.'),
    ('Account', 'OwnerId', 7, 'LOOKUP(User)', FALSE, 'Account owner.'),
    ('Account', 'CreatedDate', 8, 'DATETIME', FALSE, 'When the account was created.'),
    ('Contact', 'Id', 1, 'ID(18)', FALSE, 'Contact ID.'),
    ('Contact', 'AccountId', 2, 'LOOKUP(Account)', TRUE, 'Account the contact works at.'),
    ('Contact', 'FirstName', 3, 'TEXT(40)', TRUE, 'First name.'),
    ('Contact', 'LastName', 4, 'TEXT(80)', FALSE, 'Last name.'),
    ('Contact', 'Email', 5, 'EMAIL', TRUE, 'Email address.'),
    ('Contact', 'Phone', 6, 'PHONE', TRUE, 'Phone number.'),
    ('Opportunity', 'Id', 1, 'ID(18)', FALSE, 'Opportunity ID.'),
    ('Opportunity', 'AccountId', 2, 'LOOKUP(Account)', TRUE, 'Account the deal is with.'),
    ('Opportunity', 'Name', 3, 'TEXT(120)', FALSE, 'Opportunity name.'),
    ('Opportunity', 'StageName', 4, 'PICKLIST', FALSE, 'Sales stage.'),
    ('Opportunity', 'Amount', 5, 'CURRENCY(16,2)', TRUE, 'Expected deal value.'),
    ('Opportunity', 'CloseDate', 6, 'DATE', FALSE, 'Expected or actual close date.'),
    ('Opportunity', 'OwnerId', 7, 'LOOKUP(User)', FALSE, 'Opportunity owner.'),
    ('Lead', 'Id', 1, 'ID(18)', FALSE, 'Lead ID.'),
    ('Lead', 'FirstName', 2, 'TEXT(40)', TRUE, 'First name.'),
    ('Lead', 'LastName', 3, 'TEXT(80)', FALSE, 'Last name.'),
    ('Lead', 'Company', 4, 'TEXT(255)', FALSE, 'Company name.'),
    ('Lead', 'Status', 5, 'PICKLIST', FALSE, 'Lead status.'),
    ('Lead', 'Email', 6, 'EMAIL', TRUE, 'Email address.'),
    ('Lead', 'ConvertedAccountId', 7, 'LOOKUP(Account)', TRUE, 'Account the lead became, once converted.'),
    ('Case', 'Id', 1, 'ID(18)', FALSE, 'Case ID.'),
    ('Case', 'AccountId', 2, 'LOOKUP(Account)', TRUE, 'Account the case is for.'),
    ('Case', 'ContactId', 3, 'LOOKUP(Contact)', TRUE, 'Contact who raised the case.'),
    ('Case', 'Subject', 4, 'TEXT(255)', TRUE, 'Subject.'),
    ('Case', 'Status', 5, 'PICKLIST', FALSE, 'Case status.'),
    ('Case', 'Priority', 6, 'PICKLIST', TRUE, 'Priority.'),
    ('Case', 'CreatedDate', 7, 'DATETIME', FALSE, 'When the case was opened.'),
    ('User', 'Id', 1, 'ID(18)', FALSE, 'User ID.'),
    ('User', 'Name', 2, 'TEXT(121)', FALSE, 'Full name.'),
    ('User', 'Email', 3, 'EMAIL', FALSE, 'Email address.'),
    ('User', 'EmployeeNumber', 4, 'TEXT(20)', TRUE, 'Workday worker ID (Worker.Worker_ID).'),
    ('User', 'IsActive', 5, 'CHECKBOX', FALSE, 'The user can sign in.')
  ) AS a (table_name, name, position, data_type, nullable, description)
  JOIN core.connection AS c ON c.connection_code = 'salesforce_crm'
  JOIN core.object AS o ON o.connection_id = c.connection_id AND o.object_schema = 'salesforce'
                       AND o.object_name = a.table_name;
