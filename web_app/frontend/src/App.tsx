// The scope page (step 4a4): pick a tenant and a project, see the tables you can scope and what is in scope now,
// take the tenant lock, and (4a4c) change the scope, review the draft and Apply. All rules are checked by the backend; the page only shows what it answers.

import { useEffect, useState } from "react";
import { api, ApiError, DEMO_USERS, demoUser, IS_LOCAL, setDemoUser } from "./api";
import type { Project, Role, Tenant, User } from "./api";
import { LockBar } from "./LockBar";
import { ScopeList } from "./ScopeList";
import { TableList } from "./TableList";

const ROLE_NAMES: Record<Role, string> = { viewer: "Viewer", developer: "Developer", tenant_admin: "Tenant Admin" };

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState<number | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ user: User; tenants: Tenant[] }>("GET", "/api/me")
      .then((me) => {
        setUser(me.user);
        setTenants(me.tenants);
        setTenantId(me.tenants[0]?.tenant_id ?? null);
      })
      .catch(showError);
  }, []);

  useEffect(() => {
    setProjects([]);
    setProjectId(null);
    if (tenantId === null) return;
    api<Project[]>("GET", `/api/tenants/${tenantId}/projects`)
      .then((list) => {
        setProjects(list);
        setProjectId(list[0]?.project_id ?? null);
      })
      .catch(showError);
  }, [tenantId]);

  function showError(e: unknown) {
    setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
  }

  function switchUser(email: string) {
    setDemoUser(email);
    window.location.reload(); // start over as the new user, like signing in again
  }

  const tenant = tenants.find((t) => t.tenant_id === tenantId);
  const project = projects.find((p) => p.project_id === projectId);

  return (
    <div className="page">
      <header className="top">
        <strong>GDS Workbench</strong>
        <span className="spacer" />
        {IS_LOCAL ? (
          <label>
            Signed in as{" "}
            <select value={demoUser()} onChange={(e) => switchUser(e.target.value)}>
              {DEMO_USERS.map((u) => (
                <option key={u.email} value={u.email}>
                  {u.label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          user && <span>{user.display_name}</span>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      <section className="choose">
        <label>
          Tenant{" "}
          <select value={tenantId ?? ""} onChange={(e) => setTenantId(Number(e.target.value))}>
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.tenant_name}
                {t.tenant_visibility === "global" ? " (global)" : ""}
              </option>
            ))}
          </select>
        </label>
        {tenant && <span className="muted">You are {ROLE_NAMES[tenant.role]} here.</span>}
        <label>
          Project{" "}
          <select value={projectId ?? ""} onChange={(e) => setProjectId(Number(e.target.value))}>
            {projects.length === 0 && <option value="">No projects</option>}
            {projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.project_name}
              </option>
            ))}
          </select>
        </label>
        {project && (
          <span className="muted">
            Version {project.project_version}
            {project.is_locked ? " · locked" : ""}
          </span>
        )}
      </section>

      {project?.project_description && <p>{project.project_description}</p>}

      {tenant && user && <LockBar key={tenant.tenant_id} tenant={tenant} user={user} onChange={() => setError(null)} onError={showError} />}

      {tenant && (
        <div className="columns">
          <TableList tenantId={tenant.tenant_id} onError={showError} />
          {project && <ScopeList projectId={project.project_id} version={project.project_version} onError={showError} />}
        </div>
      )}
    </div>
  );
}
