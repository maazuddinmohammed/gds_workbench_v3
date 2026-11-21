-- 03_security.sql
-- Schema security: who can use GDS Workbench, and what they can do in each tenant.
-- Tables, keys and simple checks only. All logic (who may do what) lives in the core/ Python folder.
-- Naming, keys and audit columns follow the patterns at the top of 01_reference.sql.

CREATE SCHEMA security;

-- One person who can sign in (v2 name kept; 'user' is a reserved word in Postgres).
-- Found by email (web app) or Microsoft object ID (MCP server).
CREATE TABLE security.principal (
    principal_id           BIGINT GENERATED ALWAYS AS IDENTITY,
    principal_email        VARCHAR(320) NOT NULL,            -- stored lower case
    principal_display_name VARCHAR(200) NOT NULL,
    entra_object_id        UUID,                             -- filled at first Microsoft sign-in
    is_super_admin         BOOLEAN NOT NULL DEFAULT FALSE,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by             VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_principal PRIMARY KEY (principal_id),
    CONSTRAINT uq_principal_email UNIQUE (principal_email),
    CONSTRAINT uq_principal_entra_object_id UNIQUE (entra_object_id),
    CONSTRAINT ck_principal_email CHECK (principal_email = lower(btrim(principal_email)) AND position('@' IN principal_email) > 1),
    CONSTRAINT ck_principal_display_name CHECK (btrim(principal_display_name) <> '')
);

-- A person's role in one tenant. Remove access by deleting the row. No end date: access lasts until removed.
CREATE TABLE security.tenant_principal_access (
    tenant_principal_access_id BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                  BIGINT NOT NULL,
    principal_id               BIGINT NOT NULL,
    tenant_role                VARCHAR(30) NOT NULL,
    mcp_access_enabled         BOOLEAN NOT NULL DEFAULT FALSE, -- needed for MCP and the Bridge, for every role; Super Admins always have it
    granted_by_principal_id    BIGINT NOT NULL,
    granted_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                 VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_tenant_principal_access PRIMARY KEY (tenant_principal_access_id),
    CONSTRAINT fk_tenant_principal_access_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_tenant_principal_access_principal FOREIGN KEY (principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT fk_tenant_principal_access_granted_by_principal FOREIGN KEY (granted_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT uq_tenant_principal_access_tenant_principal UNIQUE (tenant_id, principal_id),
    CONSTRAINT ck_tenant_principal_access_tenant_role CHECK (tenant_role IN ('viewer', 'developer', 'tenant_admin'))
);
CREATE INDEX ix_tenant_principal_access_principal_id ON security.tenant_principal_access (principal_id);
CREATE INDEX ix_tenant_principal_access_granted_by_principal_id ON security.tenant_principal_access (granted_by_principal_id);

-- At most one lock per tenant, up to 4 hours. Changing drafts and Apply need the lock.
-- An expired row counts as free; core/ replaces it when someone takes the lock.
CREATE TABLE security.tenant_lock (
    tenant_lock_id            BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id                 BIGINT NOT NULL,
    locked_by_principal_id    BIGINT NOT NULL,
    tenant_lock_purpose       VARCHAR(500),
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_lock_expires_time  TIMESTAMPTZ NOT NULL,
    created_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by                VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT pk_tenant_lock PRIMARY KEY (tenant_lock_id),
    CONSTRAINT fk_tenant_lock_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id),
    CONSTRAINT fk_tenant_lock_locked_by_principal FOREIGN KEY (locked_by_principal_id)
        REFERENCES security.principal (principal_id),
    CONSTRAINT uq_tenant_lock_tenant UNIQUE (tenant_id),
    CONSTRAINT ck_tenant_lock_purpose CHECK (btrim(tenant_lock_purpose) <> ''),
    CONSTRAINT ck_tenant_lock_interval CHECK (tenant_lock_expires_time > tenant_lock_acquired_time AND tenant_lock_expires_time <= tenant_lock_acquired_time + INTERVAL '4 hours')
);
CREATE INDEX ix_tenant_lock_locked_by_principal_id ON security.tenant_lock (locked_by_principal_id);
