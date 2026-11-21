-- 01_access.sql (demo only, see README.md)
-- Tenants, demo users and their roles, and the demo project.

INSERT INTO core.lane (lane_code, lane_name, lane_description)
VALUES ('DEMO', 'Demo', 'Demo lane for local testing.');

INSERT INTO core.tenant (lane_id, tenant_code, tenant_name, tenant_description, tenant_catalog, gds_admin_catalog,
                         tenant_visibility, is_data_lake)
SELECT lane_id, t.code, t.name, t.description, t.catalog, 'gds_admin', t.visibility, t.data_lake
  FROM core.lane
 CROSS JOIN (VALUES
    ('ACME', 'Acme Retail', 'Demo company with three source systems: SAP ERP, Salesforce CRM, Workday HR.',
     'acme', 'private', FALSE),
    ('GDS', 'GDS', 'Demo data lake tenant, global: every signed-in user can read it.', 'gds', 'global', TRUE)
 ) AS t (code, name, description, catalog, visibility, data_lake)
 WHERE lane_code = 'DEMO';

-- Made-up Microsoft object IDs, so the local MCP server can sign in as a demo user (GDS_LOCAL_PRINCIPAL_OBJECT_ID).
-- The last digit is the user's number: Sam 1, Asha 2, Ben 3, Cara 4.
INSERT INTO security.principal (principal_email, principal_display_name, is_super_admin, entra_object_id)
VALUES ('sam@demo.local', 'Sam (Super Admin)', TRUE, '00000000-0000-4000-8000-000000000001'),
       ('asha@demo.local', 'Asha (Viewer)', FALSE, '00000000-0000-4000-8000-000000000002'),
       ('ben@demo.local', 'Ben (Developer)', FALSE, '00000000-0000-4000-8000-000000000003'),
       ('cara@demo.local', 'Cara (Tenant Admin)', FALSE, '00000000-0000-4000-8000-000000000004');

INSERT INTO security.tenant_principal_access (tenant_id, principal_id, tenant_role, mcp_access_enabled,
                                              granted_by_principal_id)
SELECT t.tenant_id, p.principal_id, m.role, TRUE, sam.principal_id
  FROM (VALUES ('asha@demo.local', 'viewer'),
               ('ben@demo.local', 'developer'),
               ('cara@demo.local', 'tenant_admin')) AS m (email, role)
  JOIN security.principal AS p ON p.principal_email = m.email
  JOIN core.tenant AS t ON t.tenant_code = 'ACME'
  JOIN security.principal AS sam ON sam.principal_email = 'sam@demo.local';

INSERT INTO project.project (tenant_id, project_name, project_description)
SELECT tenant_id, 'Sales', 'Demo project: one view of customers and their orders across SAP and Salesforce.'
  FROM core.tenant
 WHERE tenant_code = 'ACME';
