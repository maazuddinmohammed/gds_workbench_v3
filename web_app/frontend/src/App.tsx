// The web app's frame, in the layout of the prototype (Nov 22): a sidebar for the tenant's pages, a top bar with the
// tenant, project and who is signed in, and for a project a header with its lock and a ribbon of the workflow steps.
// Pages are picked by the address after # (for example #/step/enrichment), so the browser's back button works.
// All rules are checked by the backend; the pages only show what it answers.

import { useEffect, useState } from "react";
import { api, ApiError, DEMO_USERS, demoUser, IS_LOCAL, setDemoUser } from "./api";
import type { Project, ProjectDetail, Tenant, User } from "./api";
import { LockBar } from "./LockBar";
import { ChangeSetsPage, OverviewPage, ProjectsPage, ReviewPage, RunPage } from "./Pages";
import { NotesPage } from "./NotesPage";
import { PromptsPage } from "./PromptsPage";
import { ScopePage } from "./ScopePage";
import { STEPS, StepPage } from "./StepPage";

export type Ctx = {
  user: User;
  tenant: Tenant;
  project: ProjectDetail | null;
  projectId: number | null;
  canChange: boolean;
  go: (hash: string) => void;
  refresh: () => void; // read the project again, after an Apply
  showError: (e: unknown) => void;
};

function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/overview");
  useEffect(() => {
    const changed = () => setHash(window.location.hash || "#/overview");
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return hash.slice(2).split("/");
}

const PROJECT_PAGES = [["overview", "Overview"], ["scope", "Scope"], ["notes", "Notes"], ...Object.entries(STEPS).map(([key, s]) => [`step/${key}`, s.title])];

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState<number | null>(Number(localStorage.getItem("gds.tenant")) || null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(Number(localStorage.getItem("gds.project")) || null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [saved, setSaved] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [page, ...args] = useHash();

  function showError(e: unknown) {
    setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
  }

  useEffect(() => {
    api<{ user: User; tenants: Tenant[] }>("GET", "/api/me")
      .then((me) => {
        setUser(me.user);
        setTenants(me.tenants);
        setTenantId((now) => (me.tenants.some((t) => t.tenant_id === now) ? now : (me.tenants[0]?.tenant_id ?? null)));
      })
      .catch(showError);
  }, []);

  useEffect(() => {
    if (tenantId === null) return;
    localStorage.setItem("gds.tenant", String(tenantId));
    api<Project[]>("GET", `/api/tenants/${tenantId}/projects`)
      .then((list) => {
        setProjects(list);
        setProjectId((now) => (list.some((p) => p.project_id === now) ? now : (list[0]?.project_id ?? null)));
      })
      .catch(showError);
  }, [tenantId]);

  useEffect(() => {
    setProject(null);
    if (projectId === null) return;
    localStorage.setItem("gds.project", String(projectId));
    api<ProjectDetail>("GET", `/api/projects/${projectId}`).then(setProject).catch(showError);
  }, [projectId, saved]);

  const tenant = tenants.find((t) => t.tenant_id === tenantId);
  if (!user || !tenant) return <div className="loading">{error ?? "Loading…"}</div>;
  const ctx: Ctx = {
    user,
    tenant,
    project,
    projectId,
    canChange: tenant.permissions.includes("CHANGE"),
    go: (hash) => (window.location.hash = hash),
    refresh: () => setSaved((n) => n + 1),
    showError,
  };
  const inProject = !["home", "projects", "change-sets", "change-set", "prompts"].includes(page);
  const current = page === "step" ? `step/${args[0]}` : page;

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">GDS Workbench</div>
        {[["projects", "Projects"], ["change-sets", "Change sets"], ["prompts", "Prompts"]].map(([key, label]) => (
          <a key={key} href={`#/${key}`} className={page === key ? "on" : ""}>
            {label}
          </a>
        ))}
        {project && (
          <div className="open-project">
            <div className="muted-light">Open project</div>
            <a href="#/overview" className={inProject ? "on" : ""}>
              {project.project_name}
            </a>
          </div>
        )}
      </nav>
      <div className="main">
        <header className="topbar">
          <label>
            <span className="small">Tenant</span>
            <select value={tenant.tenant_id} onChange={(e) => setTenantId(Number(e.target.value))}>
              {tenants.map((t) => (
                <option key={t.tenant_id} value={t.tenant_id}>
                  {t.tenant_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="small">Project</span>
            <select value={projectId ?? ""} onChange={(e) => setProjectId(Number(e.target.value))}>
              {projects.length === 0 && <option value="">No projects</option>}
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.project_name}
                </option>
              ))}
            </select>
          </label>
          <span className="spacer" />
          <LockBar key={tenant.tenant_id} tenant={tenant} user={user} onChange={() => setError(null)} onError={showError} />
          {IS_LOCAL ? (
            <select
              value={demoUser()}
              onChange={(e) => {
                setDemoUser(e.target.value);
                window.location.reload();
              }}
            >
              {DEMO_USERS.map((u) => (
                <option key={u.email} value={u.email}>
                  {u.label}
                </option>
              ))}
            </select>
          ) : (
            <span>{user.display_name}</span>
          )}
        </header>
        {inProject && project && (
          <section className="project-head">
            <div>
              <h1>{project.project_name}</h1>
              <div className="muted">{project.project_description}</div>
            </div>
            <span className="pill">Version {project.project_version}</span>
            {project.is_locked && <span className="pill warn">Project locked</span>}
          </section>
        )}
        {inProject && (
          <nav className="ribbon">
            {PROJECT_PAGES.map(([key, label]) => (
              <a key={key} href={`#/${key}`} className={current === key ? "on" : ""}>
                {label}
              </a>
            ))}
          </nav>
        )}
        {error && (
          <p className="error" onClick={() => setError(null)}>
            {error}
          </p>
        )}
        <main className="content">
          {page === "projects" && <ProjectsPage ctx={ctx} projects={projects} onOpen={setProjectId} />}
          {page === "change-sets" && <ChangeSetsPage ctx={ctx} />}
          {page === "change-set" && <ReviewPage ctx={ctx} changeSetId={Number(args[0])} />}
          {page === "prompts" && <PromptsPage ctx={ctx} />}
          {inProject && projectId === null && <p className="muted">This tenant has no projects.</p>}
          {inProject && projectId !== null && (
            <>
              {page === "overview" && <OverviewPage ctx={ctx} />}
              {page === "scope" && <ScopePage ctx={ctx} />}
              {page === "notes" && <NotesPage ctx={ctx} />}
              {page === "run" && <RunPage ctx={ctx} runId={Number(args[0])} />}
              {page === "step" && STEPS[args[0]] && <StepPage key={args[0]} ctx={ctx} stepKey={args[0]} detail={args[1]} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
