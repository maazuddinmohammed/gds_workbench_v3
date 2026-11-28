# Demo data

Made-up data for trying the apps locally. Everything demo lives in this folder, apart from the real install
(`database/install/`) and seed (`database/seed/`). It never goes to Azure: `scripts/local_db.py` loads it into the
local database `gds_local`, and `scripts/db_install.py` (step 5) never reads this folder. The test database is
built without it; `tests/test_demo_data.py` loads it inside each test.

It describes metadata only (tables and columns), not the data in them.

| File | What it adds |
|---|---|
| `01_access.sql` | Tenants ACME (private, a retail company) and GDS (global, the data lake); Asha (Viewer), Ben (Developer) and Cara (Tenant Admin) in ACME with MCP access, Sam (Super Admin), each with a made-up Microsoft object ID for the local MCP server; project Sales in ACME with nothing in scope |
| `02_systems.sql` | The reference rows the catalog needs, and the four systems and their connections |
| `03_sap_erp.sql` | SAP-style ERP, Source zone: customers, sales orders, deliveries, billing, materials, vendors, purchase orders (12 tables, and one switched off) |
| `04_salesforce_crm.sql` | Salesforce-style CRM, Source zone: accounts, contacts, opportunities, leads, cases, users (6 tables) |
| `05_workday_hr.sql` | Workday-style HR, Source zone: workers, positions, organizations, job profiles (4 tables) |
| `06_data_lake.sql` | On the data lake connection gds_us: Bronze copies of four ACME tables with their ingestion lineage (table and columns), one Silver table, and GDS's own calendar and currency tables |

The systems overlap on purpose, as real ones do: a Salesforce account carries its SAP customer number
(`SAP_Customer_Number__c` = `KNA1.KUNNR`), and a Salesforce user carries its Workday worker ID
(`EmployeeNumber` = `Worker_ID`). Table and column names follow each product's public naming; the descriptions are
written for this demo.

Files run in name order, once, on a freshly built database.
