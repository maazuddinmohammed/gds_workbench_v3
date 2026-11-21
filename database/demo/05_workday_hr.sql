-- 05_workday_hr.sql (demo only, see README.md)
-- Workday-style HR on connection workday_hr, Source zone, schema workday. Names follow Workday's public report
-- field naming.

INSERT INTO core.object (connection_id, source_tenant_id, object_type_id, zone_id, object_schema, object_name,
                         object_description)
SELECT c.connection_id, c.tenant_id, ot.object_type_id, z.zone_id, 'workday', o.name, o.description
  FROM (VALUES
    ('Worker', 'Employees and contractors.'),
    ('Position', 'Positions in the organization, filled or open.'),
    ('Supervisory_Organization', 'Teams and departments, each with a manager and a parent organization.'),
    ('Job_Profile', 'Job profiles (for example Account Executive).')
  ) AS o (name, description)
  JOIN core.connection AS c ON c.connection_code = 'workday_hr'
  JOIN reference.zone AS z ON z.zone_code = 'source'
  JOIN reference.object_type AS ot ON ot.object_type_code = 'TABLE';

INSERT INTO core.attribute (object_id, attribute_name, attribute_ordinal_position, attribute_data_type,
                            attribute_nullability, attribute_description)
SELECT o.object_id, a.name, a.position, a.data_type, a.nullable, a.description
  FROM (VALUES
    ('Worker', 'Worker_ID', 1, 'TEXT', FALSE, 'Worker ID.'),
    ('Worker', 'Legal_First_Name', 2, 'TEXT', TRUE, 'Legal first name.'),
    ('Worker', 'Legal_Last_Name', 3, 'TEXT', FALSE, 'Legal last name.'),
    ('Worker', 'Email_Address', 4, 'TEXT', TRUE, 'Work email address.'),
    ('Worker', 'Hire_Date', 5, 'DATE', FALSE, 'Hire date.'),
    ('Worker', 'Position_ID', 6, 'TEXT', TRUE, 'Position the worker fills.'),
    ('Worker', 'Worker_Status', 7, 'TEXT', FALSE, 'Active, On Leave or Terminated.'),
    ('Position', 'Position_ID', 1, 'TEXT', FALSE, 'Position ID.'),
    ('Position', 'Job_Profile_ID', 2, 'TEXT', TRUE, 'Job profile of the position.'),
    ('Position', 'Supervisory_Organization_ID', 3, 'TEXT', FALSE, 'Organization the position is in.'),
    ('Position', 'Is_Filled', 4, 'BOOLEAN', FALSE, 'A worker fills the position.'),
    ('Supervisory_Organization', 'Organization_ID', 1, 'TEXT', FALSE, 'Organization ID.'),
    ('Supervisory_Organization', 'Organization_Name', 2, 'TEXT', FALSE, 'Organization name.'),
    ('Supervisory_Organization', 'Manager_Worker_ID', 3, 'TEXT', TRUE, 'Worker ID of the manager.'),
    ('Supervisory_Organization', 'Superior_Organization_ID', 4, 'TEXT', TRUE, 'Parent organization.'),
    ('Job_Profile', 'Job_Profile_ID', 1, 'TEXT', FALSE, 'Job profile ID.'),
    ('Job_Profile', 'Job_Profile_Name', 2, 'TEXT', FALSE, 'Job profile name.'),
    ('Job_Profile', 'Job_Family', 3, 'TEXT', TRUE, 'Job family (for example Sales).')
  ) AS a (table_name, name, position, data_type, nullable, description)
  JOIN core.connection AS c ON c.connection_code = 'workday_hr'
  JOIN core.object AS o ON o.connection_id = c.connection_id AND o.object_schema = 'workday'
                       AND o.object_name = a.table_name;
