// The scope page (step 4a4): pick a tenant and a project, take the tenant lock, add and take out tables, make a
// draft, review it and Apply. All rules are checked by the backend; the page only shows what it answers.

import { useEffect, useState } from "react";
import { api, ApiError, DEMO_USERS, demoUser, IS_LOCAL, setDemoUser } from "./api";
import type { Project, Role, ScopeTable, Tenant, User } from "./api";
import { Changes } from "./Changes";
import { LockBar } from "./LockBar";
import { Review } from "./Review";
import { addTable, removeTable } from "./scopeChanges";
import type { Pending } from "./scopeChanges";
import { ScopeList } from "./ScopeList";
import { TableList } from "./TableList";

const ROLE_NAMES: Record<Role, string> = { viewer: "Viewer", developer: "Developer", tenant_admin: "Tenant Admin" };

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState<number | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [scope, setScope] = useState<ScopeTable[] | null>(null); // rows taken out included
  const [pending, setPending] = useState<Pending>(new Map());
  const [draftId, setDraftId] = useState<number | null>(null);
  const [saved, setSaved] = useState(0); // goes up after each Apply, to read the project and its scope again
  const [message, setMessage] = useState<string | null>(null);
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
    if (tenantId === null) return;
    api<Project[]>("GET", `/api/tenants/${tenantId}/projects`)
      .then((list) => {
        setProjects(list);
        setProjectId((now) => (list.some((p) => p.project_id === now) ? now : (list[0]?.project_id ?? null)));
      })
      .catch(showError);
  }, [tenantId, saved]);

  useEffect(() => {
    setScope(null);
    if (projectId === null) return;
    api<ScopeTable[]>("GET", `/api/projects/${projectId}/scope?include_switched_off=true`)
      .then(setScope)
      .catch(showError);
  }, [projectId, saved]);

  useEffect(() => {
    setPending(new Map());
    setDraftId(null);
  }, [projectId]);

  function showError(e: unknown) {
    setMessage(null);
    setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
  }

  function switchUser(email: string) {
    setDemoUser(email);
    window.location.reload(); // start over as the new user, like signing in again
  }

  function makeDraft(title: string) {
    setError(null);
    api<{ change_set_id: number }>("POST", `/api/projects/${projectId}/scope-drafts`, {
      title,
      records: [...pending.values()],
    })
      .then((r) => setDraftId(r.change_set_id))
      .catch(showError);
  }

  function reviewed(applied: boolean) {
    setDraftId(null);
    setError(null);
    if (applied) {
      setPending(new Map());
      setSaved((n) => n + 1);
      setMessage("Applied. The scope is saved.");
    } else {
      setMessage("Draft rejected. Your changes are still listed, so you can fix them and make a new draft.");
    }
  }

  const tenant = tenants.find((t) => t.tenant_id === tenantId);
  const project = projects.find((p) => p.project_id === projectId);
  const canChange = tenant?.permissions.includes("CHANGE") ?? false;

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

      <section className="choose">
        <label>
          Tenant{" "}
          <select
            value={tenantId ?? ""}
            onChange={(e) => {
              setProjects([]);
              setProjectId(null);
              setTenantId(Number(e.target.value));
            }}
          >
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

      {tenant && user && (
        <LockBar key={`lock-${tenant.tenant_id}`} tenant={tenant} user={user} onChange={() => setError(null)} onError={showError} />
      )}

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      {draftId !== null && (
        <Review
          key={`draft-${draftId}`}
          changeSetId={draftId}
          canChange={canChange}
          onDone={reviewed}
          onClose={() => setDraftId(null)}
          onError={showError}
        />
      )}

      {tenant && (
        <div className="columns">
          <TableList
            tenantId={tenant.tenant_id}
            scope={scope}
            pending={pending}
            canChange={canChange && draftId === null}
            onAdd={(t) => scope && setPending(addTable(pending, scope, t))}
            onError={showError}
          />
          <div>
            {scope && (
              <ScopeList
                scope={scope}
                pending={pending}
                canChange={canChange && draftId === null}
                onRemove={(row) => setPending(removeTable(pending, scope, row))}
              />
            )}
            {canChange && draftId === null && <Changes pending={pending} onChange={setPending} onMakeDraft={makeDraft} />}
          </div>
        </div>
      )}
    </div>
  );
}
